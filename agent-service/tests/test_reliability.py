import asyncio
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from fakeredis.aioredis import FakeRedis

from app.clients.ecommerce_client import EcommerceClient, EcommerceApiError
from app.conversation_memory import ConversationMemoryStore
from app.main import create_app
from app.operation_store import OperationStore, JournaledConfirmations
from app.redis_stores import RedisConversationMemoryStore, RedisConversationStateStore
from app.conversation_state import ConversationState
from app.reliability import SessionCoordinator, RedisDemoQuota, request_budget, mark_write_attempt
from app.tools.confirmation import ConfirmationStore, fingerprint_access_token
from app.tools.registry import ToolRegistry
from tests.test_api import FakeEcommerce
from tests.test_write_receipts import settings


@pytest.mark.asyncio
async def test_read_retry_is_owned_by_http_client_and_limited_to_four_attempts():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(503, json={"message": "down"})
    client = EcommerceClient("http://business.test", backoff_seconds=[0, 0, 0])
    await client._client.aclose()
    client._client = httpx.AsyncClient(base_url="http://business.test", transport=httpx.MockTransport(handler))
    try:
        result = await ToolRegistry(client, ConfirmationStore()).execute("search_products", {"keyword": "phone"}, session_id="s", access_token=None)
        assert result.outcome == "error"
        assert len(calls) == 4
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_read_budget_cancels_slow_request_instead_of_restarting_it():
    calls = 0
    async def handler(request):
        nonlocal calls
        calls += 1
        await asyncio.sleep(1)
        return httpx.Response(200, json=[])
    client = EcommerceClient("http://business.test", retry_budget_seconds=0.03, backoff_seconds=[0, 0, 0])
    await client._client.aclose()
    client._client = httpx.AsyncClient(base_url="http://business.test", transport=httpx.MockTransport(handler))
    try:
        async with asyncio.timeout(0.5):
            with pytest.raises(EcommerceApiError):
                await client.get_cart("jwt")
        assert calls == 1
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
async def test_write_5xx_never_retries(method):
    calls = []
    client = EcommerceClient("http://business.test", backoff_seconds=[0, 0, 0])
    await client._client.aclose()
    def handler(request):
        calls.append(request)
        return httpx.Response(503, json={"message": "down"})
    client._client = httpx.AsyncClient(base_url="http://business.test", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(EcommerceApiError) as error:
            await client._request(method, "/write", access_token="jwt")
        assert error.value.result_unknown
        assert len(calls) == 1
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("write", [False, True])
async def test_total_budget_distinguishes_read_timeout_and_uncertain_write(write):
    with pytest.raises(HTTPException) as error:
        async with request_budget(0.01):
            if write:
                mark_write_attempt()
            await asyncio.sleep(1)
    assert error.value.status_code == 504
    assert ("不要重复提交" in error.value.detail) is write


@pytest.mark.asyncio
@pytest.mark.parametrize("shared", [False, True])
async def test_session_guard_rejects_overlap_and_releases_after_failure(shared):
    redis = FakeRedis(decode_responses=True) if shared else None
    first, second = SessionCoordinator(redis), SessionCoordinator(redis)
    if not shared:
        second = first
    async with first.hold("session", "jwt"):
        with pytest.raises(HTTPException) as error:
            async with second.hold("session", "jwt"):
                pytest.fail("overlapping request acquired the same session")
        assert error.value.status_code == 409
        async with second.hold("other-session", "jwt"):
            pass
    with pytest.raises(ValueError):
        async with first.hold("session", "jwt"):
            raise ValueError("failure")
    async with second.hold("session", "jwt"):
        pass
    if redis:
        await redis.aclose()


@pytest.mark.asyncio
async def test_shared_quota_is_atomic_across_instances_and_releases_exact_lease():
    redis = FakeRedis(decode_responses=True)
    first, second = RedisDemoQuota(redis, 3, 1), RedisDemoQuota(redis, 3, 1)
    lease = await first.reserve()
    with pytest.raises(HTTPException) as error:
        await second.reserve()
    assert error.value.status_code == 429
    await second.release("not-the-owner")
    with pytest.raises(HTTPException):
        await second.reserve()
    await first.release(lease)
    await second.release(await second.reserve())
    await first.release(await first.reserve())
    with pytest.raises(HTTPException) as exhausted:
        await second.reserve()
    assert "额度" in exhausted.value.detail
    await redis.aclose()


@pytest.mark.asyncio
async def test_redis_atomic_append_does_not_lose_parallel_turns():
    redis = FakeRedis(decode_responses=True)
    a, b = [RedisConversationMemoryStore(redis, max_messages=50, ttl_seconds=60) for _ in range(2)]
    await asyncio.gather(*(store.append_turn("s", "jwt", f"user-{i}", f"answer-{i}") for i, store in enumerate([a, b] * 10)))
    messages = await a.get("s", "jwt")
    assert len(messages) == 40
    assert len({m["content"] for m in messages}) == 40
    await redis.aclose()


@pytest.mark.asyncio
async def test_shared_state_preserves_confirmation_and_verified_summary_after_restart():
    redis = FakeRedis(decode_responses=True)
    state = ConversationState()
    state.remember_confirmation("intent", "create_order", {"product_id": 8})
    state.record_summary("操作记录: add_to_cart")
    state.cart_items = [{"cartId": 71, "quantity": 2}]
    await RedisConversationStateStore(redis, ttl_seconds=60).save("s", "jwt", state)
    restored = await RedisConversationStateStore(redis, ttl_seconds=60).get("s", "jwt")
    assert restored.pending_confirmation_token == "intent"
    assert restored.pending_confirmation_arguments == {"product_id": 8}
    assert restored.last_summary == state.last_summary
    assert restored.cart_items == state.cart_items
    assert (await RedisConversationStateStore(redis, ttl_seconds=60).get("s", "other")).pending_confirmation_token is None
    await redis.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("shared", [False, True])
async def test_operation_claim_survives_restart_and_has_one_winner(tmp_path, shared):
    redis = FakeRedis(decode_responses=True) if shared else None
    path = str(tmp_path / "operations.db")
    a, b = OperationStore(path, redis), OperationStore(path, redis)
    pending = await JournaledConfirmations(ConfirmationStore(), a).issue("s", "create_order", {"quantity": 1}, "owner")
    wrapper = JournaledConfirmations(ConfirmationStore(), b)
    assert await wrapper.consume(pending.token, "s", "other") is None
    consumed = await wrapper.consume(pending.token, "s", "owner")
    assert consumed.arguments["idempotency_key"] == pending.token
    winners = await asyncio.gather(a.transition(pending.token, {"accepted"}, "processing"), b.transition(pending.token, {"accepted"}, "processing"))
    assert sum(winners) == 1
    result = {"status": "executed", "message": "done", "data": {"id": 99}}
    await a.transition(pending.token, {"processing"}, "executed", result)
    assert (await OperationStore(path, redis).get(pending.token))["result"] == result
    if redis:
        await redis.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("shared", [False, True])
async def test_only_verified_operations_survive_repeated_summary_compression(shared):
    redis = FakeRedis(decode_responses=True) if shared else None
    store = RedisConversationMemoryStore(redis, max_messages=50, ttl_seconds=60) if shared else ConversationMemoryStore(max_messages=50, ttl_seconds=60)
    await store.append_turn("s", None, "如何取消订单？退款规则？", "可以咨询取消和支付规则。")
    await store.record_operations("s", None, ["add_to_cart"])
    for i in range(15):
        await store.append_turn("s", None, f"普通咨询{i}", "回答")
    first, _ = await store.summarize_and_compress("s", None)
    assert "add_to_cart" in first
    assert "cancel_order" not in first and "pay_order" not in first
    for i in range(15):
        await store.append_turn("s", None, f"后续咨询{i}", "回答")
    second, _ = await store.summarize_and_compress("s", None)
    assert "add_to_cart" in second
    assert all(set(m) == {"role", "content"} for m in await store.get("s", None))
    if redis:
        await redis.aclose()


def test_post_write_failure_never_calls_demo_fallback(tmp_path):
    business = FakeEcommerce()
    config = replace(settings(), agent_mode="auto", openai_api_key="test", operation_db_path=str(tmp_path / "ops.db"))
    app = create_app(config, ecommerce_client=business, model_client=SimpleNamespace())
    attempts = []
    async def fails_after_write(*args, **kwargs):
        attempts.append(1)
        mark_write_attempt()
        await business.cancel_order(8, "owner-jwt")
        raise RuntimeError("post-write failure")
    app.state.agent.chat = fails_after_write
    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "取消订单8", "session_id": "s", "access_token": "owner-jwt"})
    assert response.status_code == 502
    assert "不要重复提交" in response.json()["detail"]
    assert attempts == [1] and business.cancelled == [8]


def test_pending_and_completed_confirmation_survive_app_restart(tmp_path):
    business = FakeEcommerce()
    config = replace(settings(), operation_db_path=str(tmp_path / "ops.db"))
    body = {"session_id": "restart", "access_token": "owner-jwt"}
    with TestClient(create_app(config, ecommerce_client=business)) as client:
        prepared = client.post("/chat", json={**body, "message": "购买商品8，数量1件"}).json()
    token = prepared["confirmation"]["token"]
    with TestClient(create_app(config, ecommerce_client=business)) as client:
        executed = client.post("/confirm", json={**body, "confirmation_token": token, "approved": True})
        assert executed.status_code == 200
        assert executed.json()["status"] == "executed"
    with TestClient(create_app(config, ecommerce_client=business)) as client:
        replay = client.post("/confirm", json={**body, "confirmation_token": token, "approved": True})
        assert replay.json() == executed.json()
        queried = client.get(f"/operations/{token}?session_id=restart", headers={"Authorization": "Bearer owner-jwt"})
        assert queried.json() == executed.json()
        denied = client.get(f"/operations/{token}?session_id=restart", headers={"Authorization": "Bearer other-jwt"})
        assert denied.status_code == 404
    assert len(business.created_orders) == 1


def test_committed_order_with_timed_out_receipt_is_recovered_without_rewrite(tmp_path):
    class SlowReceipt(FakeEcommerce):
        def __init__(self):
            super().__init__()
            self.by_intent = {}
        async def create_order(self, *args, idempotency_key=None):
            data = await super().create_order(*args, idempotency_key=idempotency_key)
            self.by_intent[idempotency_key] = data
            await asyncio.sleep(1)  # 模拟业务提交成功，但回执迟迟未返回。
            return data
        async def get_order_by_intent(self, key, access_token):
            return self.by_intent[key]
    business = SlowReceipt()
    config = replace(settings(), chat_timeout_seconds=0.1, operation_db_path=str(tmp_path / "ops.db"))
    app = create_app(config, ecommerce_client=business)
    body = {"session_id": "timeout", "access_token": "owner-jwt"}
    with TestClient(app) as client:
        token = client.post("/chat", json={**body, "message": "购买商品8，数量1件"}).json()["confirmation"]["token"]
        failed = client.post("/confirm", json={**body, "confirmation_token": token, "approved": True})
        assert failed.status_code == 504
        assert "不要重复提交" in failed.json()["detail"]
        persisted = asyncio.run(app.state.operations.get(token))
        assert persisted["status"] == "unknown"
        recovered = client.get(f"/operations/{token}?session_id=timeout", headers={"Authorization": "Bearer owner-jwt"})
        assert recovered.json()["status"] == "executed"
        replay = client.post("/confirm", json={**body, "confirmation_token": token, "approved": True})
        assert replay.json() == recovered.json()
    assert len(business.created_orders) == 1


def test_crash_gap_after_business_commit_uses_exact_intent_to_recover(tmp_path):
    class IntentBackend(FakeEcommerce):
        async def get_order_by_intent(self, key, access_token):
            assert key == self.key
            return self.created_orders[0]
    business = IntentBackend()
    config = replace(settings(), operation_db_path=str(tmp_path / "ops.db"))
    app = create_app(config, ecommerce_client=business)
    body = {"session_id": "crash", "access_token": "owner-jwt"}
    with TestClient(app) as client:
        business.key = client.post("/chat", json={**body, "message": "购买商品8，数量1件"}).json()["confirmation"]["token"]
        async def crash_after_commit():
            await app.state.confirmations.consume(business.key, "crash", fingerprint_access_token("owner-jwt"))
            await app.state.operations.transition(business.key, {"accepted"}, "processing")
            await business.create_order(8, 1, 42, "DEMO", "owner-jwt", idempotency_key=business.key)
            # 不保存 executed，模拟业务提交和日志落盘之间进程退出。
        asyncio.run(crash_after_commit())
    with TestClient(create_app(config, ecommerce_client=business)) as client:
        recovered = client.post("/confirm", json={**body, "confirmation_token": business.key, "approved": True})
        assert recovered.json()["status"] == "executed"
        assert recovered.json()["data"]["id"] == 99
    assert len(business.created_orders) == 1
