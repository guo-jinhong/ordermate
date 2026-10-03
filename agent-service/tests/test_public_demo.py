from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import Settings
from app.clients.ecommerce_client import EcommerceApiError
from app.main import PublicDemoQuota, create_app
from app.schemas import ChatResponse
from app.tools.confirmation import ConfirmationStore
from app.tools.registry import ToolRegistry


class DemoBackend:
    async def close(self):
        return None

    async def get_current_user(self, token: str):
        if token == "legacy-token":
            return {"id": 2, "username": "testuser"}
        if token != "valid-token":
            raise EcommerceApiError("invalid token")
        return {"id": 1, "username": "interviewer"}

    async def login(self, username: str, password: str):
        if (username, password) == ("interviewer", "demo-password"):
            return "valid-token"
        raise ValueError("invalid credentials")

    async def get_cart(self, token: str):
        assert token == "valid-token"
        return [{"cartId": 71, "productId": 8, "quantity": 2}]


def demo_settings(**overrides) -> Settings:
    values = dict(
        openai_api_key="configured",
        openai_model="test-model",
        openai_base_url=None,
        ecommerce_api_base_url="http://127.0.0.1:8080/api",
        request_timeout_seconds=1,
        max_tool_rounds=3,
        agent_mode="live",
        public_demo=True,
        public_readonly=True,
        demo_chat_daily_limit=1,
        demo_chat_max_concurrent=1,
        demo_allowed_users=["interviewer"],
    )
    values.update(overrides)
    return Settings(**values)


def test_public_demo_serves_vue_and_blocks_internal_routes():
    app = create_app(demo_settings(), model_client=SimpleNamespace(), ecommerce_client=DemoBackend())
    with TestClient(app) as client:
        page = client.get("/")
        health = client.get("/health?deep=true")
        blocked = [client.get(path).status_code for path in (
            "/admin/config", "/metrics", "/docs", "/openapi.json", "/static/app.js",
        )]

    assert page.status_code == 200
    assert "/assets/" in page.text
    assert blocked == [404] * len(blocked)
    assert health.status_code == 200
    assert health.json()["backend_base_url"] == ""
    assert "llm_model" not in health.json()
    assert "checks" not in health.json()
    assert health.json()["public_demo"] is True
    assert health.json()["chat_login_required"] is False


def test_public_cart_snapshot_requires_valid_allowed_user_and_returns_full_cart():
    app = create_app(demo_settings(), model_client=SimpleNamespace(), ecommerce_client=DemoBackend())
    with TestClient(app) as client:
        assert client.get("/cart").status_code == 401
        assert client.get("/cart", headers={"Authorization": "Bearer invalid-token"}).status_code == 401
        assert client.get("/cart", headers={"Authorization": "Bearer legacy-token"}).status_code == 403
        response = client.get("/cart", headers={"Authorization": "Bearer valid-token"})
    assert response.status_code == 200
    assert response.json() == [{"cartId": 71, "productId": 8, "quantity": 2}]


def test_public_cart_snapshot_reports_read_failure_without_retrying_writes():
    class FailingBackend(DemoBackend):
        async def get_cart(self, token: str):
            raise EcommerceApiError("backend unavailable")

    app = create_app(demo_settings(), model_client=SimpleNamespace(), ecommerce_client=FailingBackend())
    with TestClient(app) as client:
        response = client.get("/cart", headers={"Authorization": "Bearer valid-token"})
    assert response.status_code == 502
    assert "backend unavailable" not in response.text


@pytest.mark.parametrize("path", ["/chat", "/chat/stream"])
@pytest.mark.parametrize("message", ["你好", "推荐手机", "介绍一下取消订单规则"])
def test_public_demo_allows_anonymous_chat_and_enforces_daily_chat_cap(path, message):
    app = create_app(demo_settings(demo_chat_daily_limit=2), model_client=SimpleNamespace(), ecommerce_client=DemoBackend())

    async def fake_chat(message: str, session_id: str, access_token: str | None):
        return ChatResponse(answer=f"live: {message}")

    app.state.agent.chat = fake_chat
    app.state.agent.collect_llm_trace = lambda: []
    payload = {"message": message, "session_id": "demo-session"}
    with TestClient(app) as client:
        unauthenticated = client.post(path, json=payload)
        legacy_login = client.post("/auth/login", json={"username": "testuser", "password": "password"})
        legacy_token = client.post(path, json=payload, headers={"Authorization": "Bearer legacy-token"})
        first = client.post(path, json=payload, headers={"Authorization": "Bearer valid-token"})
        second = client.post(path, json=payload, headers={"Authorization": "Bearer valid-token"})

    assert unauthenticated.status_code == 200
    assert f"live: {message}" in unauthenticated.text
    assert legacy_login.status_code == 403
    assert legacy_token.status_code == 403
    assert first.status_code == 200
    if path.endswith("/stream"):
        assert "event: result" in first.text
    assert f"live: {message}" in first.text
    assert second.status_code == 429


def test_public_demo_allows_normal_user_writes_and_requires_live_agent():
    create_app(demo_settings(public_readonly=False), model_client=SimpleNamespace(), ecommerce_client=DemoBackend())
    with pytest.raises(RuntimeError):
        create_app(demo_settings(agent_mode="demo"), model_client=SimpleNamespace(), ecommerce_client=DemoBackend())


def test_public_demo_quota_releases_concurrency_slot():
    async def check():
        quota = PublicDemoQuota(daily_limit=2, max_concurrent=1)
        await quota.reserve()
        with pytest.raises(HTTPException) as busy:
            await quota.reserve()
        assert busy.value.status_code == 429
        await quota.release()
        await quota.reserve()
        await quota.release()
        with pytest.raises(HTTPException) as spent:
            await quota.reserve()
        assert spent.value.status_code == 429

    asyncio.run(check())


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(ToolRegistry._WRITE_TOOLS - {"refund_order"}) + ["get_cart", "get_my_orders", "get_order_detail"])
async def test_personal_tools_reject_anonymous_access_before_backend_calls(name):
    # 后端不提供业务方法，确保未登录时在读写数据之前拦截。
    registry = ToolRegistry(SimpleNamespace(), ConfirmationStore())
    result = await registry.execute(name, {}, session_id="guest", access_token=None)
    assert result.outcome == "error"
    assert "登录" in result.output["error"]
    assert result.confirmation is None


@pytest.mark.parametrize("path", ["/chat", "/chat/stream", "/confirm"])
def test_public_demo_still_rejects_invalid_login_tokens(path):
    app = create_app(demo_settings(), model_client=SimpleNamespace(), ecommerce_client=DemoBackend())
    payload = {"message": "你好", "session_id": "guest"} if path != "/confirm" else {
        "confirmation_token": "confirmation", "session_id": "guest", "approved": True,
    }
    with TestClient(app) as client:
        response = client.post(path, json=payload, headers={"Authorization": "Bearer invalid-token"})
    assert response.status_code == 401
