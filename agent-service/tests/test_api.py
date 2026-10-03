from __future__ import annotations

from fastapi.testclient import TestClient

from app.clients.ecommerce_client import EcommerceApiError
from app.config import Settings
from app.main import create_app


def test_button_confirmation_and_text_confirmation_share_single_use_state():
    from types import SimpleNamespace

    class CartBusiness(FakeEcommerce):
        def __init__(self):
            super().__init__()
            self.batch_writes = []
        async def get_cart(self, access_token):
            return [{'cartId': 71, 'productId': 8, 'productName': '框架指南', 'quantity': 3}]
        async def clear_cart(self, access_token):
            self.batch_writes.append("clear")

    async def create(**kwargs):
        return SimpleNamespace(output=[], output_text='当前没有待确认的操作。')

    for approved in [False, True]:
        business = CartBusiness()
        settings = Settings(agent_mode='live', openai_api_key='test', openai_model='test', openai_base_url=None, request_timeout_seconds=1, max_tool_rounds=3, ecommerce_api_base_url='http://backend.test/api')
        app = create_app(settings, ecommerce_client=business, model_client=SimpleNamespace(responses=SimpleNamespace(create=create)))
        with TestClient(app) as client:
            body = {'session_id': 'shared-token', 'access_token': 'owner-jwt'}
            prepared = client.post('/chat', json={**body, 'message': '清空购物车'})
            assert prepared.status_code == 200
            token = prepared.json()['confirmation']['token']
            confirmed = client.post('/confirm', json={**body, 'confirmation_token': token, 'approved': approved})
            assert confirmed.status_code == 200
            before = len(business.batch_writes)
            repeated = client.post('/chat', json={**body, 'message': '确认'})
            assert repeated.status_code == 200
            assert len(business.batch_writes) == before == int(approved)
            assert repeated.json()['confirmation'] is None


def test_text_confirmation_uses_same_approval_and_token_as_button():
    from types import SimpleNamespace

    async def create(**kwargs):
        return SimpleNamespace(output=[], output_text='当前没有待确认的操作。')
    business = FakeEcommerce()
    settings = Settings(agent_mode='live', openai_api_key='test', openai_model='test', openai_base_url=None, request_timeout_seconds=1, max_tool_rounds=3, ecommerce_api_base_url='http://backend.test/api')
    app = create_app(settings, ecommerce_client=business, model_client=SimpleNamespace(responses=SimpleNamespace(create=create)))
    with TestClient(app) as client:
        body = {'session_id': 'text-token', 'access_token': 'owner-jwt'}
        prepared = client.post('/chat', json={**body, 'message': '取消订单 8'})
        token = prepared.json()['confirmation']['token']
        confirmed = client.post('/chat', json={**body, 'message': '确认'})
        assert confirmed.status_code == 200
        assert business.cancelled == [8]
        replay = client.post('/confirm', json={**body, 'confirmation_token': token, 'approved': True})
        assert replay.status_code == 200
        assert replay.json()["status"] == "executed"
        assert business.cancelled == [8]


class FakeEcommerce:
    def __init__(self):
        self.cancelled: list[int] = []
        self.created_orders: list[dict] = []
        self.paid_orders: list[int] = []

    async def close(self):
        return None

    async def search_products(
        self,
        keyword: str,
        min_price: float | None = None,
        max_price: float | None = None,
        in_stock: bool | None = None,
        created_after: str | None = None,
    ):
        return [{"id": 2, "name": "Smartphone X", "price": 2999, "stock": 30}]

    async def login(self, username: str, password: str):
        if username == "testuser" and password == "password":
            return "test-jwt"
        raise RuntimeError("invalid credentials")

    async def get_current_user(self, access_token: str):
        # 模拟真实后端：非空 token 视为有效（签名校验通过），只有明确失效的抛错
        if access_token in {"expired-jwt", "invalid", ""}:
            raise EcommerceApiError("invalid token")
        if access_token:
            return {"id": 1, "username": "testuser"}
        raise EcommerceApiError("invalid token")

    async def get_order_detail(self, order_id: int, access_token: str | None):
        return {
            "id": order_id,
            "orderNo": f"ORD-{order_id}",
            "status": 0,
            "finalAmount": 99,
            "items": [],
        }

    async def get_product_detail(self, product_id: int):
        return {"id": product_id, "name": "Smartphone X", "price": 2999, "stock": 30}

    async def get_addresses(self, access_token: str | None):
        return [
            {"id": 41, "isDefault": 0},
            {"id": 42, "isDefault": 1},
        ]

    async def cancel_order(self, order_id: int, access_token: str | None):
        self.cancelled.append(order_id)
        return {"id": order_id, "orderNo": f"ORD-{order_id}", "status": 4}

    async def create_order(
        self,
        product_id: int,
        quantity: int,
        address_id: int,
        payment_method: str,
        access_token: str | None,
        idempotency_key: str | None = None,
    ):
        order = {
            "id": 99,
            "orderNo": "ORD-99",
            "status": 0,
            "items": [{"productId": product_id, "quantity": quantity}],
            "addressId": address_id,
            "paymentMethod": payment_method,
        }
        self.created_orders.append(order)
        return order

    async def pay_order(self, order_id: int, access_token: str | None):
        self.paid_orders.append(order_id)
        return {"id": order_id, "orderNo": f"ORD-{order_id}", "status": 1}

    async def get_cart(self, access_token: str | None):
        return []

    async def add_to_cart(self, product_id: int, quantity: int, access_token: str | None):
        return None

    async def update_cart(self, cart_id: int, quantity: int, access_token: str | None):
        return None

    async def remove_from_cart(self, cart_id: int, access_token: str | None):
        return None

    async def clear_cart(self, access_token: str | None):
        return None


def test_health_works_without_api_key():
    settings = Settings(
        openai_api_key=None,
        openai_model="test-model",
        openai_base_url=None,
        ecommerce_api_base_url="http://backend.test/api",
        request_timeout_seconds=1,
        max_tool_rounds=3,
        agent_mode="live",
    )
    app = create_app(settings, ecommerce_client=FakeEcommerce())

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "model_configured": False,
        "agent_mode": "live",
        "serving_mode": "live",
        "embedding_mode": "lexical",
        "backend_base_url": "http://backend.test/api",
        "public_demo": False,
        "chat_login_required": False,
    }


def test_auto_mode_does_not_replay_business_flow_when_live_model_fails():
    from types import SimpleNamespace

    class FailingResponses:
        async def create(self, **kwargs):
            raise ConnectionError("provider unavailable")

    settings = Settings(
        openai_api_key="configured",
        openai_model="test-model",
        openai_base_url=None,
        ecommerce_api_base_url="http://backend.test/api",
        request_timeout_seconds=1,
        max_tool_rounds=3,
        agent_mode="auto",
    )
    app = create_app(
        settings,
        model_client=SimpleNamespace(responses=FailingResponses()),
        ecommerce_client=FakeEcommerce(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "推荐手机", "session_id": "fallback-session"},
        )
        health = client.get("/health?deep=true")

    assert response.status_code == 500
    assert health.json()["status"] == "ok"
    assert health.json()["serving_mode"] == "live"
    assert health.json().get("fallback_reason") is None


def test_auth_session_validates_stored_token_and_returns_username():
    settings = Settings(
        openai_api_key=None,
        openai_model="test-model",
        openai_base_url=None,
        ecommerce_api_base_url="http://backend.test/api",
        request_timeout_seconds=1,
        max_tool_rounds=3,
        agent_mode="live",
    )
    app = create_app(settings, ecommerce_client=FakeEcommerce())

    with TestClient(app) as client:
        valid = client.post("/auth/session", json={"access_token": "test-jwt"})
        invalid = client.post("/auth/session", json={"access_token": "expired-jwt"})

    assert valid.status_code == 200
    assert valid.json() == {"authenticated": True, "username": "testuser"}
    assert invalid.status_code == 401
    assert invalid.json()["detail"] == "登录状态无效或已失效。"


def test_auth_session_accepts_authorization_header_without_token_body():
    settings = Settings(
        openai_api_key=None,
        openai_model="test-model",
        openai_base_url=None,
        ecommerce_api_base_url="http://backend.test/api",
        request_timeout_seconds=1,
        max_tool_rounds=3,
        agent_mode="live",
    )
    app = create_app(settings, ecommerce_client=FakeEcommerce())

    with TestClient(app) as client:
        response = client.post(
            "/auth/session",
            headers={"Authorization": "Bearer test-jwt"},
        )

    assert response.status_code == 200
    assert response.json() == {"authenticated": True, "username": "testuser"}


def test_chat_explains_missing_api_key():
    settings = Settings(
        openai_api_key=None,
        openai_model="test-model",
        openai_base_url=None,
        ecommerce_api_base_url="http://backend.test/api",
        request_timeout_seconds=1,
        max_tool_rounds=3,
        agent_mode="live",
    )
    app = create_app(settings, ecommerce_client=FakeEcommerce())

    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "hello", "session_id": "session-1"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "OPENAI_API_KEY is not configured."


def test_chat_stream_emits_timeline_and_result():
    settings = Settings(
        openai_api_key=None, openai_model="test-model", openai_base_url=None,
        ecommerce_api_base_url="http://backend.test/api", request_timeout_seconds=1,
        max_tool_rounds=3, agent_mode="demo",
    )
    app = create_app(settings, ecommerce_client=FakeEcommerce())
    with TestClient(app) as client:
        response = client.post(
            "/chat/stream",
            json={"message": "推荐手机", "session_id": "session-1"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: started" in response.text
    assert "event: tool" in response.text
    assert "event: result" in response.text


def test_chat_stream_rejects_invalid_token_with_http_401_before_stream():
    """失效 token 必须在 SSE 流开始前返回标准 HTTP 401，
    不能先返回 200 + started 再在流内退化为 error 事件，
    否则前端无法可靠触发重新登录。"""
    settings = Settings(
        openai_api_key=None, openai_model="test-model", openai_base_url=None,
        ecommerce_api_base_url="http://backend.test/api", request_timeout_seconds=1,
        max_tool_rounds=3, agent_mode="demo",
    )
    app = create_app(settings, ecommerce_client=FakeEcommerce())
    with TestClient(app) as client:
        response = client.post(
            "/chat/stream",
            json={"message": "推荐手机", "session_id": "session-1", "access_token": "expired-jwt"},
        )

    assert response.status_code == 401
    # 必须是普通 JSON 错误响应，不是 SSE 流
    assert not response.headers["content-type"].startswith("text/event-stream")
    assert "event: started" not in response.text
    assert "detail" in response.json()


def test_chat_stream_uses_authorization_header_before_legacy_body_token():
    """Vue 统一使用 Authorization；请求头优先，body token 只保留旧前端兼容。"""
    settings = Settings(
        openai_api_key=None, openai_model="test-model", openai_base_url=None,
        ecommerce_api_base_url="http://backend.test/api", request_timeout_seconds=1,
        max_tool_rounds=3, agent_mode="demo",
    )
    app = create_app(settings, ecommerce_client=FakeEcommerce())

    with TestClient(app) as client:
        valid_header = client.post(
            "/chat/stream",
            headers={"Authorization": "Bearer test-jwt"},
            json={
                "message": "推荐手机",
                "session_id": "session-header-valid",
                "access_token": "expired-jwt",
            },
        )
        invalid_header = client.post(
            "/chat/stream",
            headers={"Authorization": "Bearer expired-jwt"},
            json={"message": "推荐手机", "session_id": "session-header-invalid"},
        )

    assert valid_header.status_code == 200
    assert valid_header.headers["content-type"].startswith("text/event-stream")
    assert "event: result" in valid_header.text

    assert invalid_header.status_code == 401
    assert not invalid_header.headers["content-type"].startswith("text/event-stream")
    assert "event: started" not in invalid_header.text
    assert invalid_header.json()["detail"] == "登录状态无效或已失效，请重新登录。"


def test_index_serves_chat_interface():
    settings = Settings(
        openai_api_key=None,
        openai_model="test-model",
        openai_base_url=None,
        ecommerce_api_base_url="http://backend.test/api",
        request_timeout_seconds=1,
        max_tool_rounds=3,
        agent_mode="live",
    )
    app = create_app(settings, ecommerce_client=FakeEcommerce())

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "OrderMate" in response.text
    assert "/static/app.js" in response.text
    assert response.headers["cache-control"] == "no-cache, no-store, must-revalidate"


def test_static_assets_use_version_aware_cache_headers():
    settings = Settings(
        openai_api_key=None,
        openai_model="test-model",
        openai_base_url=None,
        ecommerce_api_base_url="http://backend.test/api",
        request_timeout_seconds=1,
        max_tool_rounds=3,
        agent_mode="live",
    )
    app = create_app(settings, ecommerce_client=FakeEcommerce())

    with TestClient(app) as client:
        versioned = client.get("/static/app.js?v=20260810.7")
        unversioned = client.get("/static/app.js")

    assert versioned.status_code == 200
    assert versioned.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert unversioned.status_code == 200
    assert unversioned.headers["cache-control"] == "no-cache, must-revalidate"


def test_auto_mode_uses_demo_agent_without_api_key():
    settings = Settings(
        openai_api_key=None,
        openai_model="test-model",
        openai_base_url=None,
        ecommerce_api_base_url="http://backend.test/api",
        request_timeout_seconds=1,
        max_tool_rounds=3,
        agent_mode="auto",
    )
    app = create_app(settings, ecommerce_client=FakeEcommerce())

    with TestClient(app) as client:
        health = client.get("/health")
        response = client.post(
            "/chat",
            json={
                "message": "推荐 3000 元以内的手机",
                "session_id": "session-1",
            },
        )

    assert health.json()["agent_mode"] == "demo"
    assert response.status_code == 200
    assert "Smartphone X" in response.json()["answer"]


def test_confirmation_is_bound_to_login_and_single_use():
    settings = Settings(
        openai_api_key=None,
        openai_model="test-model",
        openai_base_url=None,
        ecommerce_api_base_url="http://backend.test/api",
        request_timeout_seconds=1,
        max_tool_rounds=3,
        agent_mode="demo",
    )
    ecommerce = FakeEcommerce()
    app = create_app(settings, ecommerce_client=ecommerce)

    with TestClient(app) as client:
        prepared = client.post(
            "/chat",
            json={
                "message": "取消订单 8",
                "session_id": "session-1",
                "access_token": "owner-jwt",
            },
        )
        confirmation_token = prepared.json()["confirmation"]["token"]

        wrong_login = client.post(
            "/confirm",
            json={
                "session_id": "session-1",
                "confirmation_token": confirmation_token,
                "approved": True,
                "access_token": "other-jwt",
            },
        )
        executed = client.post(
            "/confirm",
            json={
                "session_id": "session-1",
                "confirmation_token": confirmation_token,
                "approved": True,
                "access_token": "owner-jwt",
            },
        )
        repeated = client.post(
            "/confirm",
            json={
                "session_id": "session-1",
                "confirmation_token": confirmation_token,
                "approved": True,
                "access_token": "owner-jwt",
            },
        )

    assert wrong_login.status_code == 404
    assert executed.status_code == 200
    assert executed.json()["data"]["status"] == 4
    assert repeated.status_code == 200
    assert repeated.json() == executed.json()
    assert ecommerce.cancelled == [8]


def test_create_order_confirmation_executes_once():
    settings = Settings(
        openai_api_key=None,
        openai_model="test-model",
        openai_base_url=None,
        ecommerce_api_base_url="http://backend.test/api",
        request_timeout_seconds=1,
        max_tool_rounds=3,
        agent_mode="demo",
    )
    ecommerce = FakeEcommerce()
    app = create_app(settings, ecommerce_client=ecommerce)

    with TestClient(app) as client:
        client.post(
            "/chat",
            json={
                "message": "推荐手机",
                "session_id": "session-order-create",
                "access_token": "owner-jwt",
            },
        )
        prepared = client.post(
            "/chat",
            json={
                "message": "买 1 个它",
                "session_id": "session-order-create",
                "access_token": "owner-jwt",
            },
        )
        confirmation_token = prepared.json()["confirmation"]["token"]
        executed = client.post(
            "/confirm",
            json={
                "session_id": "session-order-create",
                "confirmation_token": confirmation_token,
                "approved": True,
                "access_token": "owner-jwt",
            },
        )
        duplicate = client.post(
            "/chat",
            json={
                "message": "再买 1 个它",
                "session_id": "session-order-create",
                "access_token": "owner-jwt",
            },
        )

    assert executed.status_code == 200
    assert executed.json()["data"]["orderNo"] == "ORD-99"
    assert executed.json()["message"] == "下单成功，订单号：ORD-99。商品：「Smartphone X」× 1 件。"
    assert ecommerce.created_orders[0]["addressId"] == 42
    assert ecommerce.created_orders[0]["paymentMethod"] == "DEMO"
    # 明确“再买”是新意图，只准备新确认，不直接再执行。
    assert duplicate.json()["confirmation"] is not None
    assert duplicate.json()["confirmation"]["token"] != confirmation_token
    assert len(ecommerce.created_orders) == 1


def test_rejected_create_order_does_not_trigger_duplicate_guard():
    settings = Settings(
        openai_api_key=None,
        openai_model="test-model",
        openai_base_url=None,
        ecommerce_api_base_url="http://backend.test/api",
        request_timeout_seconds=1,
        max_tool_rounds=3,
        agent_mode="demo",
    )
    app = create_app(settings, ecommerce_client=FakeEcommerce())

    with TestClient(app) as client:
        client.post(
            "/chat",
            json={
                "message": "推荐手机",
                "session_id": "session-order-rejected",
                "access_token": "owner-jwt",
            },
        )
        prepared = client.post(
            "/chat",
            json={
                "message": "买 1 个它",
                "session_id": "session-order-rejected",
                "access_token": "owner-jwt",
            },
        )
        rejected = client.post(
            "/confirm",
            json={
                "session_id": "session-order-rejected",
                "confirmation_token": prepared.json()["confirmation"]["token"],
                "approved": False,
                "access_token": "owner-jwt",
            },
        )
        retried = client.post(
            "/chat",
            json={
                "message": "买 1 个它",
                "session_id": "session-order-rejected",
                "access_token": "owner-jwt",
            },
        )

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "cancelled"
    assert retried.status_code == 200
    assert retried.json()["confirmation"]["action"] == "create_order"


def test_pay_order_confirmation_executes_once():
    settings = Settings(
        openai_api_key=None,
        openai_model="test-model",
        openai_base_url=None,
        ecommerce_api_base_url="http://backend.test/api",
        request_timeout_seconds=1,
        max_tool_rounds=3,
        agent_mode="demo",
    )
    ecommerce = FakeEcommerce()
    app = create_app(settings, ecommerce_client=ecommerce)

    with TestClient(app) as client:
        prepared = client.post(
            "/chat",
            json={
                "message": "支付订单 8",
                "session_id": "session-pay",
                "access_token": "owner-jwt",
            },
        )
        confirmation_token = prepared.json()["confirmation"]["token"]
        executed = client.post(
            "/confirm",
            json={
                "session_id": "session-pay",
                "confirmation_token": confirmation_token,
                "approved": True,
                "access_token": "owner-jwt",
            },
        )

    assert executed.status_code == 200
    assert executed.json()["data"]["status"] == 1
    assert ecommerce.paid_orders == [8]


def test_clear_conversation_endpoint_clears_server_memory():
    from types import SimpleNamespace

    class FakeResponses:
        def __init__(self):
            self.requests = []

        async def create(self, **kwargs):
            self.requests.append(kwargs)
            return SimpleNamespace(output=[], output_text="ok")

    settings = Settings(
        openai_api_key="configured",
        openai_model="test-model",
        openai_base_url=None,
        ecommerce_api_base_url="http://backend.test/api",
        request_timeout_seconds=1,
        max_tool_rounds=3,
        agent_mode="live",
    )
    responses = FakeResponses()
    model_client = SimpleNamespace(responses=responses)
    app = create_app(
        settings, model_client=model_client, ecommerce_client=FakeEcommerce()
    )

    with TestClient(app) as client:
        client.post(
            "/chat",
            json={"message": "first", "session_id": "session-1"},
        )
        cleared = client.post(
            "/conversation/clear",
            json={"session_id": "session-1"},
        )
        client.post(
            "/chat",
            json={"message": "second", "session_id": "session-1"},
        )

    assert cleared.status_code == 200
    assert cleared.json() == {"status": "cleared", "cleared": True}
    assert responses.requests[1]["input"] == [
        {"role": "user", "content": "second"}
    ]
