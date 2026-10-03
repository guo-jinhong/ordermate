import asyncio
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from fakeredis.aioredis import FakeRedis

from app.clients.ecommerce_client import EcommerceClient, EcommerceApiError
from app.main import create_app, _execute_confirmed_action
from app.operation_store import OperationStore, JournaledConfirmations
from app.reliability import RedisDemoQuota
from app.tools.confirmation import ConfirmationStore, fingerprint_access_token
from app.tools.registry import ToolRegistry
from tests.test_api import FakeEcommerce
from tests.test_public_demo import demo_settings, DemoBackend
from tests.test_write_receipts import settings


@pytest.mark.asyncio
@pytest.mark.parametrize("method,business_code,unknown", [("GET", 400, False), ("POST", 409, False), ("POST", 500, True)])
async def test_http_success_with_business_failure_is_never_reported_as_success(method, business_code, unknown):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"code": business_code, "message": "business rejected", "data": None})
    client = EcommerceClient("http://business.test", backoff_seconds=[0, 0, 0])
    await client._client.aclose()
    client._client = httpx.AsyncClient(base_url="http://business.test", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(EcommerceApiError) as failure:
            await client._request(method, "/operation", access_token="jwt")
        assert failure.value.code == f"ECOMMERCE_BACKEND_BUSINESS_{business_code}"
        assert failure.value.result_unknown is unknown
        assert failure.value.retryable is False
        assert len(calls) == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_invalid_success_code_after_write_is_an_unknown_receipt():
    client = EcommerceClient("http://business.test")
    await client._client.aclose()
    client._client = httpx.AsyncClient(base_url="http://business.test", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"code": 200.5, "message": "invalid"})))
    try:
        with pytest.raises(EcommerceApiError) as failure:
            await client._request("POST", "/write")
        assert failure.value.result_unknown is True
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_quota_release_outage_does_not_replace_a_completed_result():
    class BrokenRelease:
        async def zrem(self, *args):
            raise ConnectionError("cleanup outage")
    quota = RedisDemoQuota(BrokenRelease(), 3, 1)
    await quota.release("owner")


@pytest.mark.asyncio
@pytest.mark.parametrize("action,empty", [("create_order", True), ("cancel_order", False), ("pay_order", False), ("cancel_order", True), ("pay_order", True)])
async def test_missing_or_mismatched_order_receipt_is_not_marked_success(action, empty):
    class InvalidReceipt(FakeEcommerce):
        async def create_order(self, *args, **kwargs):
            await super().create_order(*args, **kwargs)
            return None
        async def cancel_order(self, order_id, access_token):
            self.cancelled.append(order_id)
            return None if empty else {"id": 999, "status": 4}
        async def pay_order(self, order_id, access_token):
            self.paid_orders.append(order_id)
            return None if empty else {"id": 999, "paymentStatus": 1}
    business = InvalidReceipt()
    registry = ToolRegistry(business, ConfirmationStore())
    args = {"order_id": 8, "product_id": 8, "quantity": 1, "address_id": 42}
    with pytest.raises(EcommerceApiError) as failure:
        await _execute_confirmed_action(business, registry, "s", action, args, "owner-jwt")
    assert failure.value.result_unknown is True
    assert len(business.created_orders) + len(business.cancelled) + len(business.paid_orders) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("shared", [False, True])
async def test_clear_invalidates_all_pending_intents_for_only_current_identity(tmp_path, shared):
    redis = FakeRedis(decode_responses=True) if shared else None
    operations = OperationStore(str(tmp_path / "ops.db"), redis)
    confirmations = JournaledConfirmations(ConfirmationStore(), operations)
    pending = await confirmations.issue("s", "create_order", {}, "owner")
    second = await confirmations.issue("s", "cancel_order", {}, "owner")
    other_user = await confirmations.issue("s", "create_order", {}, "other")
    other_session = await confirmations.issue("different", "create_order", {}, "owner")
    processing = await confirmations.issue("s", "create_order", {}, "owner")
    await operations.transition(processing.token, {"prepared"}, "processing")
    assert await operations.cancel_prepared("s", "owner") == 2
    assert await confirmations.consume(pending.token, "s", "owner") is None
    assert (await operations.get(second.token))["status"] == "cancelled"
    assert (await operations.get(other_user.token))["status"] == "prepared"
    assert (await operations.get(other_session.token))["status"] == "prepared"
    assert (await operations.get(processing.token))["status"] == "processing"
    if redis:
        await redis.aclose()


def test_cleared_confirmation_card_cannot_execute_and_anonymous_clear_still_works(tmp_path):
    business = FakeEcommerce()
    app = create_app(replace(settings(), operation_db_path=str(tmp_path / "ops.db")), ecommerce_client=business)
    body = {"session_id": "clear", "access_token": "owner-jwt"}
    with TestClient(app) as client:
        token = client.post("/chat", json={**body, "message": "取消订单8"}).json()["confirmation"]["token"]
        assert client.post("/conversation/clear", json=body).json()["cleared"] is True
        response = client.post("/confirm", json={**body, "confirmation_token": token, "approved": True})
        assert response.json()["status"] == "cancelled"
        assert client.post("/conversation/clear", json={"session_id": "anonymous"}).status_code == 200
    assert business.cancelled == []


@pytest.mark.asyncio
async def test_readonly_rejection_closes_operation_instead_of_leaving_accepted(tmp_path):
    business = FakeEcommerce()
    operations = OperationStore(str(tmp_path / "ops.db"))
    confirmations = JournaledConfirmations(ConfirmationStore(), operations)
    pending = await confirmations.issue("s", "cancel_order", {"order_id": 8}, fingerprint_access_token("owner-jwt"))
    registry = ToolRegistry(business, confirmations, public_readonly=True)
    registry.operations = operations
    with pytest.raises(EcommerceApiError, match="只读"):
        await registry.consume_confirmation(pending.token, "s", "owner-jwt")
    assert (await operations.get(pending.token))["status"] == "failed"
    with pytest.raises(EcommerceApiError, match="只读"):
        await _execute_confirmed_action(business, registry, "s", "cancel_order", pending.arguments, "owner-jwt")
    assert business.cancelled == []


@pytest.mark.asyncio
async def test_disconnecting_after_first_stream_event_returns_local_demo_slot(tmp_path):
    app = create_app(replace(demo_settings(), operation_db_path=str(tmp_path / "ops.db")), model_client=SimpleNamespace(), ecommerce_client=DemoBackend())
    route = next(route for route in app.routes if getattr(route, "path", None) == "/chat/stream")
    from app.schemas import ChatRequest
    # 直接调用未装饰的路由，准确停在第一个 yield 而不预读取整个 SSE。
    response = await route.endpoint.__wrapped__(None, ChatRequest(message="你好", session_id="s"), None)
    assert app.state.demo_quota.active == 1
    await anext(response.body_iterator)
    await response.body_iterator.aclose()
    assert app.state.demo_quota.active == 0
