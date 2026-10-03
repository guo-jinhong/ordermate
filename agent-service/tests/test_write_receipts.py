"""丢失写回执只能查询核实，批量参数、地址和确认期限必须一致。"""
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app.clients.ecommerce_client import EcommerceApiError, EcommerceClient
from app.config import Settings
from app.main import _execute_confirmed_action, create_app
from app.tools.confirmation import ConfirmationStore
from app.tools.registry import ToolRegistry


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", [("POST", "/shopping-cart/add"), ("POST", "/orders"),
    ("POST", "/orders/8/pay"), ("PUT", "/shopping-cart/71"), ("DELETE", "/shopping-cart/71")])
@pytest.mark.parametrize("failure", ["timeout", "5xx", "bad_receipt"])
async def test_writes_never_retry_after_backend_may_have_committed(method, path, failure):
    writes = []
    def handler(request):
        writes.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("ack lost after commit", request=request)
        if failure == "bad_receipt":
            return httpx.Response(200, text="broken ack")
        return httpx.Response(503)
    client = EcommerceClient("http://isolated.test", max_retries=3, backoff_seconds=[0.001])
    await client.close()
    client._client = httpx.AsyncClient(base_url="http://isolated.test", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(EcommerceApiError) as error:
            await client._request(method, path)
        assert error.value.result_unknown
        assert not error.value.retryable
        assert "勿重复提交" in str(error.value)
        assert len(writes) == 1
    finally:
        await client.close()


class Backend:
    def __init__(self):
        self.items = [{"cartId": 71, "productId": 8, "productName": "框架指南", "quantity": 3}]
        self.writes = 0
        self.addresses = [{"id": 41, "isDefault": 0, "name": "甲", "address": "A路"},
                          {"id": 42, "isDefault": 1, "name": "乙", "province": "广东省", "city": "深圳市", "address": "B路"}]
        self.order = {"id": 8, "orderNo": "ORD-8", "status": 0, "paymentStatus": 0}

    async def get_current_user(self, token): return {"id": 1, "username": "testuser"}
    async def get_product_detail(self, product_id): return {"id": product_id, "name": "框架指南", "stock": 99}
    async def get_cart(self, token): return [dict(item) for item in self.items]
    async def get_addresses(self, token): return self.addresses
    async def get_my_orders(self, token): return [dict(self.order)]
    async def get_order_detail(self, order_id, token): return dict(self.order)
    async def close(self): pass
    async def update_cart_items(self, items, token): self.writes += 1
    async def add_to_cart(self, product_id, quantity, token):
        self.writes += 1
        self.items[0]["quantity"] += quantity
        raise EcommerceApiError("ack lost", retryable=True, result_unknown=True)
    async def remove_from_cart(self, cart_id, token):
        self.writes += 1
        self.items = []
        raise EcommerceApiError("ack lost", result_unknown=True)
    async def create_order(self, *args, **kwargs):
        self.writes += 1
        raise EcommerceApiError("ack lost", result_unknown=True)
    async def cancel_order(self, order_id, token):
        self.writes += 1
        self.order["status"] = 4
        raise EcommerceApiError("ack lost", result_unknown=True)


def registry(backend, confirmations=None):
    return ToolRegistry(backend, confirmations or ConfirmationStore(), knowledge_base=object())


def settings():
    return Settings(openai_api_key=None, openai_model="test", openai_base_url=None,
                    ecommerce_api_base_url="http://isolated.test", request_timeout_seconds=1,
                    max_tool_rounds=3, agent_mode="demo")


@pytest.mark.asyncio
async def test_batch_conflicting_quantities_rejected_before_write():
    backend = Backend()
    result = await registry(backend).execute("update_cart_items", {"quantity": 1, "items": [{"cart_id": 71, "quantity": 2}]}, session_id="batch", access_token="owner")
    assert result.outcome == "error"
    assert "数量不一致" in result.output["error"]
    assert backend.writes == 0
    assert backend.items[0]["quantity"] == 3


@pytest.mark.asyncio
async def test_add_unknown_receipt_reads_cart_but_never_repeats_or_claims_success():
    backend = Backend()
    result = await registry(backend).execute("add_to_cart", {"product_id": 8, "quantity": 1}, session_id="add", access_token="owner")
    assert result.outcome == "error"
    assert "有 4 件" in result.output["error"]
    assert "勿重复提交" in result.output["error"]
    assert backend.writes == 1


@pytest.mark.asyncio
async def test_model_cannot_repeat_write_after_unknown_result(monkeypatch):
    from types import SimpleNamespace
    from app.agent import AgentService
    import app.agent as agent_module
    monkeypatch.setattr(agent_module, "_direct_add_to_cart_arguments", lambda *args: None)
    class RepeatingModel:
        def __init__(self): self.responses = self; self.calls = 0
        async def create(self, **kwargs):
            self.calls += 1
            return SimpleNamespace(output_text="", output=[SimpleNamespace(type="function_call", name="add_to_cart",
                arguments='{"product_id":8,"quantity":1}', call_id="repeat")])
    backend = Backend()
    model = RepeatingModel()
    result = await AgentService(model, registry(backend), model="test").chat(
        "把商品 8 加入购物车，数量 1 件", session_id="model-repeat", access_token="owner")
    assert "无法确认" in result.answer
    assert backend.writes == model.calls == 1


@pytest.mark.asyncio
async def test_remove_unknown_receipt_verifies_absent_item_without_repeating():
    backend = Backend()
    result = await registry(backend).execute("remove_from_cart", {"cart_id": 71}, session_id="remove", access_token="owner")
    assert result.outcome == "success"
    assert result.output["cart_snapshot"] == []
    assert backend.writes == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["default", "first", "empty"])
async def test_create_order_uses_owned_address_and_exposes_expiry(case):
    backend = Backend()
    if case == "first":
        backend.addresses[1]["isDefault"] = 0
    elif case == "empty":
        backend.addresses = []
    result = await registry(backend).execute("create_order", {"product_id": 8, "quantity": 1}, session_id="address", access_token="owner")
    if case == "empty":
        assert result.outcome == "error"
        assert "没有收货地址" in result.output["error"]
        assert result.confirmation is None
    else:
        selected = backend.addresses[1 if case == "default" else 0]
        assert result.confirmation.arguments["address_id"] == selected["id"]
        assert selected["address"] in result.confirmation.arguments["address_summary"]
        assert result.confirmation.expires_at > datetime.now(UTC)
    assert backend.writes == 0


@pytest.mark.asyncio
async def test_cancel_unknown_receipt_reports_verified_order_state():
    backend = Backend()
    data, message = await _execute_confirmed_action(backend, registry(backend), "cancel", "cancel_order", {"order_id": 8}, "owner")
    assert data["status"] == 4
    assert "已确认" in message
    assert backend.writes == 1


def test_uncertain_creation_uses_unknown_ui_status_and_blocks_immediate_duplicate():
    backend = Backend()
    app = create_app(settings(), ecommerce_client=backend)
    with TestClient(app) as client:
        body = {"session_id": "create", "access_token": "owner"}
        prepared = client.post("/chat", json={**body, "message": "购买商品 8，数量 1 件"}).json()
        response = client.post("/confirm", json={**body, "confirmation_token": prepared["confirmation"]["token"], "approved": True})
        assert response.status_code == 200
        assert response.json()["status"] == "unknown"
        assert "勿重复下单" in response.json()["message"]
        assert backend.writes == 1
        duplicate = client.post("/chat", json={**body, "message": "购买商品 8，数量 1 件"}).json()
        assert "核实" in duplicate["answer"]
        assert duplicate["confirmation"] is None


def test_expired_confirmation_is_chinese_and_never_writes():
    backend = Backend()
    app = create_app(settings(), ecommerce_client=backend)
    with TestClient(app) as client:
        app.state.confirmations.delegate._ttl = timedelta(seconds=0)
        body = {"session_id": "expired", "access_token": "owner"}
        prepared = client.post("/chat", json={**body, "message": "清空购物车"}).json()
        response = client.post("/confirm", json={**body, "confirmation_token": prepared["confirmation"]["token"], "approved": True})
        assert response.status_code == 404
        assert "过期" in response.json()["detail"]
        assert backend.writes == 0
