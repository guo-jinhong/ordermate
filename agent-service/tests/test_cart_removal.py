"""移除必须绑定购物车项、实际写入，并以读回结果确认成功。"""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.clients.ecommerce_client import EcommerceApiError
from app.config import Settings
from app.main import create_app


class CartBackend:
    def __init__(self, ineffective=False, readback_error=False):
        self.items = [
            {"cartId": 71, "productId": 8, "productName": "Spring Framework Guide", "quantity": 3, "price": 99},
            {"cartId": 72, "productId": 2, "productName": "Smartphone X", "quantity": 1, "price": 2999},
        ]
        self.removed = []
        self.ineffective = ineffective
        self.readback_error = readback_error

    async def get_current_user(self, token):
        return {"id": 1, "username": "outsider" if token == "other-jwt" else "isolated-test"}

    async def get_cart(self, token):
        if self.removed and self.readback_error:
            raise EcommerceApiError("read failed")
        return [dict(item) for item in self.items]

    async def remove_from_cart(self, cart_id, token):
        self.removed.append(cart_id)
        if not self.ineffective:
            self.items = [item for item in self.items if item["cartId"] != cart_id]

    async def clear_cart(self, token):
        self.items = []

    async def get_order_detail(self, order_id, token):
        return {"id": order_id, "orderNo": "ORD-100", "status": 0, "finalAmount": 99}

    async def cancel_order(self, order_id, token):
        self.cancelled = order_id
        return {"id": order_id, "orderNo": "ORD-100", "status": 4}

    async def close(self):
        pass


class MisleadingModel:
    """即使模型自报已删除，也不能把它当业务事实。"""
    def __init__(self):
        self.responses = self

    async def create(self, **kwargs):
        if any(getattr(item, "type", None) == "function_call" for item in kwargs["input"]):
            return SimpleNamespace(output=[], output_text="已移除所有商品。")
        call = SimpleNamespace(type="function_call", name="get_cart", arguments=json.dumps({}), call_id="cart")
        return SimpleNamespace(output=[call], output_text="")

    async def close(self):
        pass


def application(backend, mode="live", readonly=False, public=False):
    settings = Settings(openai_api_key="test" if mode == "live" else None, openai_model="test",
        openai_base_url=None, ecommerce_api_base_url="http://isolated.test/api", request_timeout_seconds=1,
        max_tool_rounds=3, agent_mode=mode, public_readonly=readonly, public_demo=public,
        demo_allowed_users=["isolated-test"])
    return create_app(settings, ecommerce_client=backend, model_client=MisleadingModel() if mode == "live" else None)


def chat(client, message):
    response = client.post("/chat", json={"message": message, "session_id": "remove-test", "access_token": "isolated-jwt"})
    assert response.status_code == 200, response.text
    return response.json()


def confirm(client, prepared, approved=True):
    return client.post("/confirm", json={"session_id": "remove-test", "access_token": "isolated-jwt",
        "confirmation_token": prepared["confirmation"]["token"], "approved": approved})


@pytest.mark.parametrize("mode", ["live", "demo"])
@pytest.mark.parametrize("message", ["移除购物车项 71", "把购物车里的 Spring Framework Guide 删掉", "从购物车移除「Spring Framework Guide」"])
def test_remove_then_query_and_repeat_uses_correct_cart_row(mode, message):
    backend = CartBackend()
    with TestClient(application(backend, mode)) as client:
        result = chat(client, message)
        assert result["confirmation"] is None
        assert result["tool_calls"][-1]["outcome"] == "success"
        assert "已从购物车移除" in result["answer"]
        assert [item["cartId"] for item in result["data"]] == [72]
        assert backend.removed == [71]
        assert [item["cartId"] for item in chat(client, "查看我的购物车")["data"]] == [72]
        repeated = chat(client, "移除购物车项 71")
        assert repeated["confirmation"] is None
        assert "已不存在" in repeated["answer"]
        assert backend.removed == [71]



@pytest.mark.parametrize("mode", ["live", "demo"])
def test_ambiguous_or_unknown_item_never_claims_deleted(mode):
    backend = CartBackend()
    with TestClient(application(backend, mode)) as client:
        for message in ["把它移除", "从购物车移除「不存在的商品」"]:
            result = chat(client, message)
            assert result["confirmation"] is None
            assert "已移除" not in result["answer"]
        assert backend.removed == []


@pytest.mark.parametrize("failure", ["ineffective", "readback_error"])
def test_delete_acknowledgement_alone_is_not_success(failure):
    backend = CartBackend(**{failure: True})
    with TestClient(application(backend)) as client:
        result = chat(client, "移除购物车项 71")
        assert result["tool_calls"][-1]["outcome"] == "error"
        assert result["confirmation"] is None
        assert "已从购物车移除" not in result["answer"]
        assert ("未生效" if failure == "ineffective" else "无法核实") in result["answer"]
        assert backend.removed == [71]



@pytest.mark.parametrize("mode", ["live", "demo"])
def test_readonly_removal_truthfully_refused(mode):
    backend = CartBackend()
    with TestClient(application(backend, mode, readonly=True)) as client:
        result = chat(client, "移除购物车项 71")
        assert result["confirmation"] is None
        assert result["tool_calls"][-1]["outcome"] == "error"
        assert "已移除" not in result["answer"]
        assert backend.removed == []


def test_clear_cart_requires_text_confirmation():
    backend = CartBackend()
    with TestClient(application(backend)) as client:
        prepared = chat(client, "清空购物车")
        assert prepared["confirmation"]["action"] == "clear_cart"
        assert len(backend.items) == 2
        result = chat(client, "确认")
        assert "已清空" in result["answer"]
        assert backend.items == []


def test_reject_does_not_delete():
    backend = CartBackend()
    with TestClient(application(backend)) as client:
        result = confirm(client, chat(client, "清空购物车"), False)
        assert result.json()["status"] == "cancelled"
        assert backend.removed == []


@pytest.mark.parametrize("mode", ["live", "demo"])
@pytest.mark.parametrize("message", ["不要把购物车里的 Spring Framework Guide 删掉", "不用删去购物车项 71"])
def test_negative_removal_does_not_prepare_or_execute(mode, message):
    backend = CartBackend()
    with TestClient(application(backend, mode)) as client:
        result = chat(client, message)
        assert result["confirmation"] is None
        assert backend.removed == []
        assert len(backend.items) == 2


@pytest.mark.parametrize("text_confirmation", [False, True])
def test_public_demo_has_normal_user_permissions(text_confirmation):
    backend = CartBackend()
    with TestClient(application(backend, public=True)) as client:
        result = chat(client, "移除购物车项 71")
        assert result["confirmation"] is None
        assert [item["cartId"] for item in result["data"]] == [72]
        prepared = chat(client, "取消订单 100")
        assert prepared["confirmation"]["action"] == "cancel_order"
        assert not hasattr(backend, "cancelled")
        if text_confirmation:
            result = chat(client, "确认")
            assert "已成功取消" in result["answer"]
        else:
            response = confirm(client, prepared)
            assert response.status_code == 200
            assert response.json()["status"] == "executed"
        assert backend.cancelled == 100


def test_public_cart_permission_keeps_account_and_item_ownership_checks():
    backend = CartBackend()
    with TestClient(application(backend, public=True)) as client:
        anonymous = client.post("/chat", json={"message": "移除购物车项 71", "session_id": "remove-test"})
        assert anonymous.status_code == 200
        body = anonymous.json()
        assert '登录' in body['answer']
        assert body['tool_calls'][-1]['outcome'] == 'error'
        assert body['data'] is None
        assert body['confirmation'] is None
        assert backend.removed == []
        assert len(backend.items) == 2
        foreign = client.post("/chat", json={"message": "移除购物车项 71", "session_id": "remove-test", "access_token": "other-jwt"})
        assert foreign.status_code == 403
        stale = chat(client, "移除购物车项 999")
        assert stale["confirmation"] is None
        assert backend.removed == []


@pytest.mark.asyncio
async def test_normal_demo_policy_does_not_block_business_writes():
    from app.tools.registry import ToolRegistry
    from app.tools.confirmation import ConfirmationStore
    registry = ToolRegistry(CartBackend(), ConfirmationStore())
    for name in registry._WRITE_TOOLS:
        assert not registry.is_write_disabled(name)
