import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fakeredis.aioredis import FakeRedis
from fastapi.testclient import TestClient

from app.agent import _guard_tool_call
from app.business_fields import purchase_request, requests_repeat_purchase
from app.conversation_state import ConversationState
from app.main import create_app
from app.main import _execute_confirmed_action
from app.clients.ecommerce_client import EcommerceApiError
from app.operation_store import OperationStore, JournaledConfirmations
from app.tools.confirmation import ConfirmationStore, fingerprint_access_token
from app.tools.registry import ToolRegistry
from tests.test_api import FakeEcommerce
from tests.test_write_receipts import settings


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["pay_order", "cancel_order"])
async def test_immediate_recovery_requires_target_order_identity(action):
    class MissingIdentity(FakeEcommerce):
        async def get_order_detail(self, order_id, access_token):
            return {"status": 4, "paymentStatus": 1}
        async def pay_order(self, order_id, access_token):
            self.paid_orders.append(order_id)
            raise EcommerceApiError("lost receipt", result_unknown=True)
        async def cancel_order(self, order_id, access_token):
            self.cancelled.append(order_id)
            raise EcommerceApiError("lost receipt", result_unknown=True)
    business = MissingIdentity()
    registry = ToolRegistry(business, ConfirmationStore())
    with pytest.raises(EcommerceApiError) as failure:
        await _execute_confirmed_action(business, registry, "s", action, {"order_id": 8}, "jwt")
    assert failure.value.result_unknown
    assert len(business.paid_orders) + len(business.cancelled) == 1


@pytest.mark.asyncio
async def test_empty_cart_does_not_prove_unknown_clear_request_completed():
    class UnknownClear(FakeEcommerce):
        writes = 0
        async def clear_cart(self, access_token):
            self.writes += 1
            raise EcommerceApiError("lost receipt", result_unknown=True)
        async def get_cart(self, access_token):
            return []
    business = UnknownClear()
    with pytest.raises(EcommerceApiError) as failure:
        await _execute_confirmed_action(business, ToolRegistry(business, ConfirmationStore()), "s", "clear_cart", {}, "jwt")
    assert failure.value.result_unknown
    assert business.writes == 1


@pytest.mark.parametrize("message,authorized", [
    ("再买一单商品8，1件", True), ("重新购买商品8", True),
    ("不要再次购买商品8", False), ("再买一单有什么规则？", False),
    ("之前说过再买一单", False), ('他说“再买一单”', False),
])
def test_repeat_purchase_intent_requires_current_explicit_request(message, authorized):
    assert requests_repeat_purchase(message) is authorized


@pytest.mark.parametrize("tool,message,args", [
    ("cancel_order", "取消订单8有什么规则", {"order_id": 8}),
    ("pay_order", "如何支付订单8", {"order_id": 8}),
    ("create_order", "如果购买商品8会怎样", {"product_id": 8, "quantity": 1}),
    ("clear_cart", '我之前说过“清空购物车”', {}),
    ("add_to_cart", "不要加入购物车商品8", {"product_id": 8, "quantity": 1}),
    ("cancel_order", '“取消订单8”', {"order_id": 8}),
])
def test_wrong_write_tool_is_rejected_for_consultation_negation_or_quote(tool, message, args):
    assert _guard_tool_call(tool, args, message, ConversationState()) is not None


@pytest.mark.asyncio
async def test_registry_does_not_trust_model_repeat_flag_or_quoted_instruction():
    business = FakeEcommerce()
    registry = ToolRegistry(business, ConfirmationStore())
    await registry.record_created_order("s", "jwt", 8, 1)
    with purchase_request('他之前说过“再买商品8”'):
        result = await registry.execute("create_order", {"product_id": 8, "quantity": 1, "allow_repeat": True}, session_id="s", access_token="jwt")
    assert result.outcome == "error"
    assert result.confirmation is None
    assert not business.created_orders


@pytest.mark.asyncio
async def test_cleanup_cas_does_not_cancel_concurrently_accepted_intent(tmp_path):
    redis = FakeRedis(decode_responses=True)
    store = OperationStore(str(tmp_path / "ops.db"), redis)
    pending = await ConfirmationStore().issue("s", "create_order", {}, "jwt")
    await store.put(pending)
    original_eval = redis.eval
    raced = False
    async def race_eval(*args):
        nonlocal raced
        if not raced:
            raced = True
            await store.transition(pending.token, {"prepared"}, "accepted")
        return await original_eval(*args)
    redis.eval = race_eval
    await store.cleanup(now=datetime.now(UTC) + timedelta(days=1))
    assert (await store.get(pending.token))["status"] == "accepted"
    await redis.aclose()


@pytest.mark.asyncio
async def test_repeat_purchase_needs_new_confirmation_and_unknown_blocks_it(tmp_path):
    operations = OperationStore(str(tmp_path / "ops.db"))
    registry = ToolRegistry(FakeEcommerce(), JournaledConfirmations(ConfirmationStore(), operations))
    registry.operations = operations
    await registry.record_created_order("s", "jwt", 8, 1)
    args = {"product_id": 8, "quantity": 1}
    normal = await registry.execute("create_order", args, session_id="s", access_token="jwt")
    assert normal.outcome == "error"
    with purchase_request("再买一单商品8，1件"):
        prepared = await registry.execute("create_order", args, session_id="s", access_token="jwt")
    assert prepared.confirmation is not None
    assert not registry._ecommerce.created_orders
    assert 170 < (datetime.fromisoformat(prepared.confirmation.expires_at.isoformat()) - datetime.now(UTC)).total_seconds() <= 180
    assert await operations.transition(prepared.confirmation.token, {"prepared"}, "unknown")
    with purchase_request("再买一单商品8，1件"):
        blocked = await registry.execute("create_order", args, session_id="other-session", access_token="jwt")
    assert blocked.outcome == "error"
    assert "核实" in blocked.output["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize("shared", [False, True])
async def test_retention_keeps_unknown_processing_and_recent_terminals(tmp_path, shared):
    redis = FakeRedis(decode_responses=True) if shared else None
    store = OperationStore(str(tmp_path / "ops.db"), redis)
    confirmations = JournaledConfirmations(ConfirmationStore(), store)
    now = datetime.now(UTC)
    tokens = {}
    for status in ["executed", "failed", "cancelled", "unknown", "accepted", "processing", "prepared"]:
        pending = await confirmations.issue("s", "create_order", {}, "jwt")
        tokens[status] = pending.token
        if status != "prepared":
            await store.transition(pending.token, {"prepared"}, status)
    # 将维护时钟推进八天，只有终态可删，过期待确认先归档。
    assert await store.cleanup(now=now + timedelta(days=8)) == 3
    for status in ["executed", "failed", "cancelled"]:
        assert await store.get(tokens[status]) is None
    for status in ["unknown", "accepted", "processing"]:
        assert (await store.get(tokens[status]))["status"] == status
    assert (await store.get(tokens["prepared"]))["status"] == "cancelled"
    assert await confirmations.consume(tokens["prepared"], "s", "jwt") is None
    assert await store.cleanup(now=now + timedelta(days=9)) == 0
    if redis:
        await redis.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("shared", [False, True])
async def test_legacy_terminal_without_timestamp_gets_full_retention(tmp_path, shared):
    redis = FakeRedis(decode_responses=True) if shared else None
    store = OperationStore(str(tmp_path / "ops.db"), redis)
    pending = await ConfirmationStore().issue("s", "clear_cart", {}, "jwt")
    await store.put(pending)
    value = await store.get(pending.token)
    value.update(status="executed")
    value.pop("updated_at")
    raw = json.dumps(value)
    if redis:
        await redis.set("agent:operation:" + pending.token, raw)
    else:
        with store._connect() as db:
            db.execute("UPDATE agent_operations SET record=? WHERE token=?", (raw, pending.token))
    now = datetime.now(UTC)
    assert await store.cleanup(now=now) == 0
    assert await store.cleanup(now=now + timedelta(days=6)) == 0
    assert await store.cleanup(now=now + timedelta(days=8)) == 1
    if redis:
        await redis.aclose()


@pytest.mark.parametrize("action,field,value", [("pay_order", "paymentStatus", 1), ("cancel_order", "status", 4)])
def test_manual_verification_recovers_state_without_write(tmp_path, action, field, value):
    class ReadBusiness(FakeEcommerce):
        async def get_order_detail(self, order_id, access_token):
            return {"id": order_id, field: value}
    business = ReadBusiness()
    path = str(tmp_path / "ops.db")
    async def prepare():
        store = OperationStore(path)
        pending = await ConfirmationStore().issue("s", action, {"order_id": 8}, fingerprint_access_token("jwt"))
        await store.put(pending)
        await store.transition(pending.token, {"prepared"}, "unknown")
        return pending.token
    token = asyncio.run(prepare())
    with TestClient(create_app(replace(settings(), operation_db_path=path), ecommerce_client=business)) as client:
        route = f"/operations/{token}?session_id=s"
        assert client.get(route, headers={"Authorization": "Bearer other"}).status_code == 404
        result = client.get(route, headers={"Authorization": "Bearer jwt"})
        assert result.json()["status"] == "executed"
        assert client.get(route, headers={"Authorization": "Bearer jwt"}).json()["status"] == "executed"
    assert business.cancelled == business.paid_orders == business.created_orders == []
