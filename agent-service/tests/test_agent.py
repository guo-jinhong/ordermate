from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.agent import AgentService
from app.tools.confirmation import ConfirmationStore, fingerprint_access_token
from app.tools.registry import ToolRegistry


class FakeEcommerce:
    def __init__(self) -> None:
        self.cancelled: list[int] = []
        self.search_keywords: list[str] = []
        self.order_status = 0

    async def search_products(
        self,
        keyword: str,
        min_price: float | None = None,
        max_price: float | None = None,
        in_stock: bool | None = None,
        created_after: str | None = None,
    ):
        self.search_keywords.append(keyword)
        return [{"id": 1, "name": f"{keyword} Phone", "price": 2999}]

    async def get_order_detail(self, order_id: int, access_token: str | None):
        return {
            "id": order_id,
            "orderNo": f"ORD-{order_id}",
            "status": self.order_status,
            "finalAmount": 99,
        }

    async def cancel_order(self, order_id: int, access_token: str | None):
        self.cancelled.append(order_id)
        return {"id": order_id, "status": 4}


class FakeResponses:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.requests = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        return next(self._responses)


class FakeToolRegistry:
    async def execute(
        self,
        name: str,
        arguments: dict,
        *,
        session_id: str,
        access_token: str | None,
    ):
        return SimpleNamespace(
            output={
                "ok": True,
                "data": [{"id": 2, "name": "Smartphone X", "price": 2999, "stock": 30}],
            },
            outcome="success",
            confirmation=None,
        )


class ContextAwareFakeToolRegistry:
    def __init__(self) -> None:
        self.calls = []

    async def execute(
        self,
        name: str,
        arguments: dict,
        *,
        session_id: str,
        access_token: str | None,
    ):
        self.calls.append((name, dict(arguments)))
        if name == "search_products":
            return SimpleNamespace(
                output={
                    "ok": True,
                    "data": [
                        {"id": 104, "name": "OPPO Find X7", "price": 3999, "stock": 30},
                        {"id": 126, "name": "小米 Redmi 13C", "price": 799, "stock": 200},
                        {"id": 132, "name": "iQOO Neo9", "price": 2999, "stock": 40},
                    ],
                },
                outcome="success",
                confirmation=None,
            )
        if name == "add_to_cart":
            return SimpleNamespace(
                output={
                    "ok": True,
                    "data": {
                        "productId": arguments["product_id"],
                        "quantity": arguments["quantity"],
                    },
                },
                outcome="success",
                confirmation=None,
            )
        if name == "get_cart":
            return SimpleNamespace(
                output={
                    "ok": True,
                    "data": [
                        {
                            "cartId": 88,
                            "productId": 104,
                            "productName": "OPPO Find X7",
                            "quantity": 1,
                        }
                    ],
                },
                outcome="success",
                confirmation=None,
            )
        if name == "update_cart":
            from app.schemas import Confirmation

            return SimpleNamespace(
                output={
                    "ok": False,
                    "confirmation_required": True,
                    "data": dict(arguments),
                },
                outcome="confirmation_required",
                confirmation=Confirmation(
                    token="confirm-update-cart",
                    action="update_cart",
                    description="将购物车项 #88 数量修改为 2",
                    arguments=dict(arguments),
                ),
            )
        if name == "update_cart_items":
            from app.schemas import Confirmation

            return SimpleNamespace(
                output={
                    "ok": False,
                    "confirmation_required": True,
                    "data": dict(arguments),
                },
                outcome="confirmation_required",
                confirmation=Confirmation(
                    token="confirm-update-cart-items",
                    action="update_cart_items",
                    description="批量修改购物车数量",
                    arguments=dict(arguments),
                ),
            )
        return SimpleNamespace(output={"ok": True, "data": None}, outcome="success", confirmation=None)


class CapturingEcommerce:
    def __init__(self) -> None:
        self.calls = []

    async def search_products(
        self,
        keyword: str,
        min_price: float | None = None,
        max_price: float | None = None,
        in_stock: bool | None = None,
        created_after: str | None = None,
    ):
        self.calls.append((keyword, min_price, max_price, in_stock, created_after))
        return []


@pytest.mark.asyncio
async def test_registry_passes_created_after_to_product_search():
    ecommerce = CapturingEcommerce()
    registry = ToolRegistry(ecommerce, ConfirmationStore())

    result = await registry.execute(
        "search_products",
        {
            "keyword": "耳机",
            "max_price": 3000,
            "in_stock": True,
            "created_after": "2026-07-01",
        },
        session_id="session-created-after",
        access_token=None,
    )

    assert result.outcome == "success"
    assert ecommerce.calls == [("耳机", None, 3000.0, True, "2026-07-01")]


@pytest.mark.asyncio
async def test_business_query_retries_when_model_skips_tool_call():
    skipped_tool = SimpleNamespace(output=[], output_text="Smartphone X costs 2999.")
    forced_tool = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                name="search_products",
                arguments=json.dumps({"keyword": "手机", "max_price": 4000}),
                call_id="call-1",
            )
        ],
        output_text="",
    )
    final_answer = SimpleNamespace(output=[], output_text="Smartphone X is 2999.")
    responses = FakeResponses([skipped_tool, forced_tool, final_answer])
    agent = AgentService(
        SimpleNamespace(responses=responses),
        FakeToolRegistry(),
        model="test-model",
    )

    result = await agent.chat(
        "推荐4000以内的手机",
        session_id="session-force-tool",
        access_token=None,
    )

    assert result.answer == "Smartphone X is 2999."
    assert result.tool_calls[0].name == "search_products"
    assert result.tool_calls[0].arguments == {"keyword": "手机", "max_price": 4000}
    retry_messages = [
        item.get("content", "")
        for item in responses.requests[1]["input"]
        if isinstance(item, dict)
    ]
    assert any("必须从这些工具中选择合适工具调用" in text for text in retry_messages)


@pytest.mark.asyncio
async def test_smalltalk_does_not_force_tool_call():
    responses = FakeResponses([SimpleNamespace(output=[], output_text="你好！")])
    agent = AgentService(
        SimpleNamespace(responses=responses),
        FakeToolRegistry(),
        model="test-model",
    )

    result = await agent.chat("你好", session_id="session-smalltalk", access_token=None)

    assert result.answer == "你好！"
    assert result.tool_calls == []
    assert len(responses.requests) == 1


@pytest.mark.asyncio
async def test_agent_executes_product_search():
    first = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                name="search_products",
                arguments=json.dumps({"keyword": "budget"}),
                call_id="call-1",
            )
        ],
        output_text="",
    )
    second = SimpleNamespace(
        output=[],
        output_text="I found a budget phone for 2999.",
    )
    responses = FakeResponses([first, second])
    registry = ToolRegistry(FakeEcommerce(), ConfirmationStore())
    agent = AgentService(
        SimpleNamespace(responses=responses),
        registry,
        model="test-model",
    )

    result = await agent.chat(
        "Find a budget phone",
        session_id="session-1",
        access_token=None,
    )

    assert result.answer == "I found a budget phone for 2999."
    assert result.tool_calls[0].name == "search_products"
    assert result.tool_calls[0].outcome == "success"
    tool_output = responses.requests[1]["input"][-1]
    assert tool_output["type"] == "function_call_output"
    assert '"price": 2999' in tool_output["output"]


@pytest.mark.asyncio
async def test_product_search_guard_allows_power_bank_price_query():
    first = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                name="search_products",
                arguments=json.dumps(
                    {"keyword": "充电宝", "min_price": 100, "max_price": 300},
                    ensure_ascii=False,
                ),
                call_id="call-power-bank",
            )
        ],
        output_text="",
    )
    second = SimpleNamespace(output=[], output_text="找到一款充电宝。")
    responses = FakeResponses([first, second])
    agent = AgentService(
        SimpleNamespace(responses=responses),
        FakeToolRegistry(),
        model="test-model",
    )

    result = await agent.chat(
        "价格100-300的充电宝",
        session_id="session-power-bank",
        access_token=None,
    )

    assert result.answer == "找到一款充电宝。"
    assert result.tool_calls[0].outcome == "success"


@pytest.mark.asyncio
async def test_add_to_cart_infers_recent_product_and_default_quantity():
    from app.conversation_state import ConversationStateStore

    search_call = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                name="search_products",
                arguments=json.dumps({"keyword": "手机", "max_price": 4000}, ensure_ascii=False),
                call_id="call-search",
            )
        ],
        output_text="",
    )
    search_answer = SimpleNamespace(output=[], output_text="找到红米手机。")
    add_call = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                name="add_to_cart",
                arguments=json.dumps({}, ensure_ascii=False),
                call_id="call-cart",
            )
        ],
        output_text="",
    )
    add_answer = SimpleNamespace(output=[], output_text="已加入购物车。")
    responses = FakeResponses([search_call, search_answer, add_call, add_answer])
    registry = ContextAwareFakeToolRegistry()
    state_store = ConversationStateStore(ttl_seconds=60)
    agent = AgentService(
        SimpleNamespace(responses=responses),
        registry,
        model="test-model",
        state_store=state_store,
    )

    await agent.chat("推荐4000以内手机", session_id="ctx-cart", access_token="jwt")
    result = await agent.chat("把刚刚的红米手机加入购物车", session_id="ctx-cart", access_token="jwt")

    assert result.tool_calls[0].name == "add_to_cart"
    assert result.tool_calls[0].arguments == {"product_id": 126, "quantity": 1}
    assert registry.calls[-1] == ("add_to_cart", {"product_id": 126, "quantity": 1})


@pytest.mark.asyncio
async def test_add_to_cart_infers_chinese_quantity():
    from app.conversation_state import ConversationStateStore

    state_store = ConversationStateStore(ttl_seconds=60)
    state = await state_store.get("ctx-qty", "jwt")
    state.record_product_search(
        "手机",
        product_id=126,
        product_name="小米 Redmi 13C",
        shown_product_ids=[126],
        shown_products=[{"id": 126, "name": "小米 Redmi 13C"}],
    )
    await state_store.save("ctx-qty", "jwt", state)
    add_call = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                name="add_to_cart",
                arguments=json.dumps({}, ensure_ascii=False),
                call_id="call-cart-qty",
            )
        ],
        output_text="",
    )
    add_answer = SimpleNamespace(output=[], output_text="已加入购物车。")
    responses = FakeResponses([add_call, add_answer])
    registry = ContextAwareFakeToolRegistry()
    agent = AgentService(
        SimpleNamespace(responses=responses),
        registry,
        model="test-model",
        state_store=state_store,
    )

    result = await agent.chat("把刚刚的红米手机加入购物车，两台", session_id="ctx-qty", access_token="jwt")

    assert result.tool_calls[0].arguments == {"product_id": 126, "quantity": 2}


@pytest.mark.asyncio
async def test_direct_add_to_cart_when_model_would_skip_tool_call():
    from app.conversation_state import ConversationStateStore

    state_store = ConversationStateStore(ttl_seconds=60)
    state = await state_store.get("ctx-direct-cart", "jwt")
    state.record_product_search(
        "手机",
        product_id=104,
        product_name="OPPO Find X7",
        shown_product_ids=[104, 126],
        shown_products=[
            {"id": 104, "name": "OPPO Find X7"},
            {"id": 126, "name": "小米 Redmi 13C"},
        ],
    )
    await state_store.save("ctx-direct-cart", "jwt", state)
    responses = FakeResponses([])
    registry = ContextAwareFakeToolRegistry()
    agent = AgentService(
        SimpleNamespace(responses=responses),
        registry,
        model="test-model",
        state_store=state_store,
    )

    result = await agent.chat(
        "把刚刚的红米手机加入购物车",
        session_id="ctx-direct-cart",
        access_token="jwt",
    )

    assert result.answer == "已把 小米 Redmi 13C x 1 加入购物车。"
    assert result.reference is not None
    assert result.reference.value == "126"
    assert result.tool_calls[0].arguments == {"product_id": 126, "quantity": 1}
    assert len(responses.requests) == 0


@pytest.mark.asyncio
async def test_update_cart_infers_cart_item_and_quantity():
    from app.conversation_state import ConversationStateStore

    state_store = ConversationStateStore(ttl_seconds=60)
    state = await state_store.get("ctx-update-cart", "jwt")
    state.record_cart_items(
        [
            {
                "cartId": 88,
                "productId": 104,
                "productName": "OPPO Find X7",
                "quantity": 1,
            }
        ]
    )
    await state_store.save("ctx-update-cart", "jwt", state)
    registry = ContextAwareFakeToolRegistry()
    agent = AgentService(
        SimpleNamespace(responses=FakeResponses([])),
        registry,
        model="test-model",
        state_store=state_store,
    )

    result = await agent.chat(
        "把购物车里的 OPPO Find X7 数量改为 2 件",
        session_id="ctx-update-cart",
        access_token="jwt",
    )

    assert result.confirmation is not None
    assert result.tool_calls[0].name == "update_cart"
    assert result.tool_calls[0].arguments == {"cart_id": 88, "quantity": 2}


@pytest.mark.asyncio
async def test_natural_language_confirmation_executes_pending_cart_update():
    from app.conversation_state import ConversationStateStore

    executed = []

    async def executor(action, arguments, access_token):
        executed.append((action, dict(arguments), access_token))
        return {"ok": True}, f"购物车项 {arguments['cart_id']} 数量已修改为 {arguments['quantity']}。"

    state_store = ConversationStateStore(ttl_seconds=60)
    state = await state_store.get("ctx-confirm-cart", "jwt")
    state.remember_confirmation(
        "token",
        "update_cart",
        {"cart_id": 88, "quantity": 2},
    )
    await state_store.save("ctx-confirm-cart", "jwt", state)
    agent = AgentService(
        SimpleNamespace(responses=FakeResponses([])),
        ContextAwareFakeToolRegistry(),
        model="test-model",
        state_store=state_store,
        confirmed_action_executor=executor,
    )

    result = await agent.chat("对", session_id="ctx-confirm-cart", access_token="jwt")

    assert result.answer == "购物车项 88 数量已修改为 2。"
    assert executed == [("update_cart", {"cart_id": 88, "quantity": 2}, "jwt")]


@pytest.mark.asyncio
async def test_update_cart_same_quantity_does_not_require_confirmation():
    from app.conversation_state import ConversationStateStore

    state_store = ConversationStateStore(ttl_seconds=60)
    state = await state_store.get("ctx-same-qty", "jwt")
    state.record_cart_items(
        [
            {
                "cartId": 88,
                "productId": 104,
                "productName": "OPPO Find X7",
                "quantity": 2,
            }
        ]
    )
    await state_store.save("ctx-same-qty", "jwt", state)
    registry = ContextAwareFakeToolRegistry()
    agent = AgentService(
        SimpleNamespace(responses=FakeResponses([])),
        registry,
        model="test-model",
        state_store=state_store,
    )

    result = await agent.chat(
        "把购物车里的 OPPO Find X7 数量改为 2 件",
        session_id="ctx-same-qty",
        access_token="jwt",
    )

    assert "已经是 2 件" in result.answer
    assert result.confirmation is None
    assert result.tool_calls == []
    assert registry.calls == []


@pytest.mark.asyncio
async def test_update_all_cart_items_to_same_quantity():
    from app.conversation_state import ConversationStateStore

    state_store = ConversationStateStore(ttl_seconds=60)
    state = await state_store.get("ctx-batch-qty", "jwt")
    state.record_cart_items(
        [
            {
                "cartId": 88,
                "productId": 104,
                "productName": "OPPO Find X7",
                "quantity": 2,
            },
            {
                "cartId": 89,
                "productId": 126,
                "productName": "小米 Redmi 13C",
                "quantity": 1,
            },
        ]
    )
    await state_store.save("ctx-batch-qty", "jwt", state)
    registry = ContextAwareFakeToolRegistry()
    agent = AgentService(
        SimpleNamespace(responses=FakeResponses([])),
        registry,
        model="test-model",
        state_store=state_store,
    )

    result = await agent.chat(
        "对 两件商品都改成3件",
        session_id="ctx-batch-qty",
        access_token="jwt",
    )

    assert result.confirmation is not None
    assert result.tool_calls[0].name == "update_cart_items"
    assert result.tool_calls[0].arguments == {
        "items": [
            {"cart_id": 88, "quantity": 3},
            {"cart_id": 89, "quantity": 3},
        ],
        "quantity": 3,
    }


def test_chat_messages_group_multiple_tool_calls():
    from app.agent import _chat_messages_from_responses_input

    items = [
        {"role": "user", "content": "改购物车"},
        SimpleNamespace(
            type="function_call",
            name="get_cart",
            arguments="{}",
            call_id="call-1",
        ),
        SimpleNamespace(
            type="function_call",
            name="update_cart",
            arguments='{"cart_id":88,"quantity":3}',
            call_id="call-2",
        ),
        {"type": "function_call_output", "call_id": "call-1", "output": '{"ok":true}'},
        {"type": "function_call_output", "call_id": "call-2", "output": '{"ok":true}'},
    ]

    messages = _chat_messages_from_responses_input("sys", items)

    assert messages[2]["role"] == "assistant"
    assert len(messages[2]["tool_calls"]) == 2
    assert messages[3]["role"] == "tool"
    assert messages[4]["role"] == "tool"


@pytest.mark.asyncio
async def test_cancel_tool_only_creates_confirmation():
    ecommerce = FakeEcommerce()
    registry = ToolRegistry(ecommerce, ConfirmationStore())

    result = await registry.execute(
        "cancel_order",
        {"order_id": 42},
        session_id="session-1",
        access_token="jwt",
    )

    assert result.outcome == "confirmation_required"
    assert result.confirmation is not None
    assert result.confirmation.arguments == {
        "order_id": 42,
        "order_no": "ORD-42",
        "final_amount": 99,
        "status": 0,
    }
    assert ecommerce.cancelled == []


@pytest.mark.asyncio
async def test_registry_translates_chinese_product_keyword():
    ecommerce = FakeEcommerce()
    registry = ToolRegistry(ecommerce, ConfirmationStore())

    result = await registry.execute(
        "search_products",
        {"keyword": "手机"},
        session_id="session-1",
        access_token=None,
    )

    assert result.outcome == "success"
    assert ecommerce.search_keywords == ["手机"]


@pytest.mark.asyncio
async def test_registry_returns_friendly_argument_error():
    registry = ToolRegistry(FakeEcommerce(), ConfirmationStore())

    result = await registry.execute(
        "search_products",
        {},
        session_id="session-1",
        access_token=None,
    )

    assert result.outcome == "error"
    assert "工具参数 keyword 必须是文本" in result.output["error"]


@pytest.mark.asyncio
async def test_cancel_tool_rejects_non_pending_order_before_confirmation():
    ecommerce = FakeEcommerce()
    ecommerce.order_status = 1
    registry = ToolRegistry(ecommerce, ConfirmationStore())

    result = await registry.execute(
        "cancel_order",
        {"order_id": 42},
        session_id="session-1",
        access_token="jwt",
    )

    assert result.outcome == "error"
    assert result.confirmation is None
    assert "待支付" in result.output["error"]
    assert ecommerce.cancelled == []


@pytest.mark.asyncio
async def test_confirmation_token_is_single_use():
    store = ConfirmationStore()
    fingerprint = fingerprint_access_token("jwt")
    pending = await store.issue(
        "session-1", "cancel_order", {"order_id": 42}, fingerprint
    )

    first = await store.consume(pending.token, "session-1", fingerprint)
    second = await store.consume(pending.token, "session-1", fingerprint)

    assert first is not None
    assert second is None


@pytest.mark.asyncio
async def test_wrong_session_does_not_consume_confirmation():
    store = ConfirmationStore()
    fingerprint = fingerprint_access_token("jwt")
    pending = await store.issue(
        "session-1", "cancel_order", {"order_id": 42}, fingerprint
    )

    wrong_session = await store.consume(pending.token, "session-2", fingerprint)
    correct_session = await store.consume(pending.token, "session-1", fingerprint)

    assert wrong_session is None
    assert correct_session is not None


@pytest.mark.asyncio
async def test_wrong_login_does_not_consume_confirmation():
    store = ConfirmationStore()
    owner_fingerprint = fingerprint_access_token("owner-jwt")
    pending = await store.issue(
        "session-1", "cancel_order", {"order_id": 42}, owner_fingerprint
    )

    wrong_login = await store.consume(
        pending.token,
        "session-1",
        fingerprint_access_token("other-jwt"),
    )
    owner = await store.consume(pending.token, "session-1", owner_fingerprint)

    assert wrong_login is None
    assert owner is not None

@pytest.mark.asyncio
async def test_agent_includes_prior_turns_for_same_identity():
    from app.conversation_memory import ConversationMemoryStore

    first_reply = SimpleNamespace(output=[], output_text="第一句是春风，第二句是落日。")
    second_reply = SimpleNamespace(output=[], output_text="第二句更安静。")
    responses = FakeResponses([first_reply, second_reply])
    memory = ConversationMemoryStore(max_messages=8, ttl_seconds=60)
    registry = ToolRegistry(FakeEcommerce(), ConfirmationStore())
    agent = AgentService(
        SimpleNamespace(responses=responses),
        registry,
        model="test-model",
        memory=memory,
    )

    await agent.chat("给我两句短句", session_id="session-1", access_token="jwt-1")
    await agent.chat("第二个怎么样？", session_id="session-1", access_token="jwt-1")

    second_input = responses.requests[1]["input"]
    assert second_input == [
        {"role": "user", "content": "给我两句短句"},
        {"role": "assistant", "content": "第一句是春风，第二句是落日。"},
        {"role": "user", "content": "第二个怎么样？"},
    ]


@pytest.mark.asyncio
async def test_agent_does_not_share_history_across_logins():
    from app.conversation_memory import ConversationMemoryStore

    responses = FakeResponses([
        SimpleNamespace(output=[], output_text="owner reply"),
        SimpleNamespace(output=[], output_text="other reply"),
    ])
    memory = ConversationMemoryStore(max_messages=8, ttl_seconds=60)
    registry = ToolRegistry(FakeEcommerce(), ConfirmationStore())
    agent = AgentService(
        SimpleNamespace(responses=responses), registry, model="test-model", memory=memory
    )

    await agent.chat("记住一句话：蓝色文件夹", session_id="same-session", access_token="owner-jwt")
    await agent.chat("刚才那个", session_id="same-session", access_token="other-jwt")

    assert responses.requests[1]["input"] == [
        {"role": "user", "content": "刚才那个"}
    ]


@pytest.mark.asyncio
async def test_agent_state_store_updates_on_product_search():
    from app.conversation_state import ConversationStateStore

    first = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                name="search_products",
                arguments=json.dumps({"keyword": "smartphone"}),
                call_id="call-1",
            )
        ],
        output_text="",
    )
    second = SimpleNamespace(
        output=[],
        output_text="Here are the smartphones.",
    )
    responses = FakeResponses([first, second])
    registry = ToolRegistry(FakeEcommerce(), ConfirmationStore())
    state_store = ConversationStateStore(ttl_seconds=60)
    agent = AgentService(
        SimpleNamespace(responses=responses),
        registry,
        model="test-model",
        state_store=state_store,
    )

    await agent.chat(
        "search for smartphones",
        session_id="session-state-1",
        access_token=None,
    )

    state = await state_store.get("session-state-1", None)
    assert state.last_product_keyword == "smartphone"
    assert state.last_topic == "product"
    assert state.turn_count > 0


@pytest.mark.asyncio
async def test_agent_state_injected_into_system_instructions():
    from app.conversation_state import ConversationStateStore

    first = SimpleNamespace(output=[], output_text="Hello!")
    responses = FakeResponses([first])
    registry = ToolRegistry(FakeEcommerce(), ConfirmationStore())
    state_store = ConversationStateStore(ttl_seconds=60)

    state = await state_store.get("session-state-2", None)
    state.record_order(42, "ORD-42")
    await state_store.save("session-state-2", None, state)

    agent = AgentService(
        SimpleNamespace(responses=responses),
        registry,
        model="test-model",
        state_store=state_store,
    )

    await agent.chat(
        "What about it?",
        session_id="session-state-2",
        access_token=None,
    )

    instructions = responses.requests[0]["instructions"]
    assert "Conversation context" in instructions
    assert "#42" in instructions
    assert "ORD-42" in instructions
    assert "last referenced order" in instructions.lower()


@pytest.mark.asyncio
async def test_agent_state_is_isolated_by_session():
    from app.conversation_state import ConversationStateStore

    first = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                name="search_products",
                arguments=json.dumps({"keyword": "laptop"}),
                call_id="call-1",
            )
        ],
        output_text="",
    )
    second = SimpleNamespace(output=[], output_text="Here are laptops.")
    responses = FakeResponses([first, second, first, second])
    registry = ToolRegistry(FakeEcommerce(), ConfirmationStore())
    state_store = ConversationStateStore(ttl_seconds=60)
    agent = AgentService(
        SimpleNamespace(responses=responses),
        registry,
        model="test-model",
        state_store=state_store,
    )

    await agent.chat("find laptops", session_id="sess-a", access_token=None)
    await agent.chat("find laptops", session_id="sess-b", access_token=None)

    state_a = await state_store.get("sess-a", None)
    state_b = await state_store.get("sess-b", None)
    assert state_a.last_product_keyword == "laptop"
    assert state_b.last_product_keyword == "laptop"
    assert state_a is not state_b


@pytest.mark.asyncio
async def test_agent_state_not_updated_on_tool_error():
    from app.conversation_state import ConversationStateStore

    first = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                name="cancel_order",
                arguments=json.dumps({"order_id": 999}),
                call_id="call-1",
            )
        ],
        output_text="",
    )
    second = SimpleNamespace(output=[], output_text="That order cannot be cancelled.")

    class ErrorEcommerce:
        async def get_order_detail(self, order_id, access_token):
            return {"id": order_id, "orderNo": f"ORD-{order_id}", "status": 1, "finalAmount": 99}

        async def cancel_order(self, order_id, access_token):
            raise Exception("not pending")

    responses = FakeResponses([first, second])
    registry = ToolRegistry(ErrorEcommerce(), ConfirmationStore())
    state_store = ConversationStateStore(ttl_seconds=60)
    agent = AgentService(
        SimpleNamespace(responses=responses),
        registry,
        model="test-model",
        state_store=state_store,
    )

    await agent.chat(
        "cancel order 999",
        session_id="session-error",
        access_token="jwt",
    )

    state = await state_store.get("session-error", "jwt")
    assert state.last_order_id is None
    assert state.last_topic is None


@pytest.mark.asyncio
async def test_agent_blocks_unrequested_cancel_tool_call():
    ecommerce = FakeEcommerce()
    first = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                name="cancel_order",
                arguments=json.dumps({"order_id": 8}),
                call_id="call-1",
            )
        ],
        output_text="",
    )
    second = SimpleNamespace(output=[], output_text="我不会取消订单。")
    responses = FakeResponses([first, second])
    registry = ToolRegistry(ecommerce, ConfirmationStore())
    agent = AgentService(
        SimpleNamespace(responses=responses),
        registry,
        model="test-model",
    )

    result = await agent.chat(
        "查询我的最近订单",
        session_id="session-guard",
        access_token="jwt",
    )

    assert result.tool_calls[0].name == "cancel_order"
    assert result.tool_calls[0].outcome == "error"
    assert ecommerce.cancelled == []
    tool_output = json.loads(responses.requests[1]["input"][-1]["output"])
    assert "没有明确要求取消订单" in tool_output["error"]


def test_detect_reference_for_order():
    from app.agent import _detect_reference
    from app.schemas import ToolCallRecord

    records = [ToolCallRecord(name="get_order_detail", arguments={"order_id": 5}, outcome="success")]
    ref = _detect_reference("看看它的详情", records, 5, None)
    assert ref is not None
    assert ref.type == "order"
    assert ref.value == "5"


def test_detect_reference_for_product():
    from app.agent import _detect_reference
    from app.schemas import ToolCallRecord

    records = [ToolCallRecord(name="search_products", arguments={"keyword": "手机"}, outcome="success")]
    ref = _detect_reference("再看看", records, None, "手机")
    assert ref is not None
    assert ref.type == "product"
    assert ref.value == "手机"


def test_detect_reference_returns_none_without_referral():
    from app.agent import _detect_reference
    from app.schemas import ToolCallRecord

    records = [ToolCallRecord(name="get_order_detail", arguments={"order_id": 5}, outcome="success")]
    ref = _detect_reference("查看订单 5", records, 5, None)
    assert ref is None


def test_detect_reference_returns_none_without_match():
    from app.agent import _detect_reference
    from app.schemas import ToolCallRecord

    records = [ToolCallRecord(name="get_order_detail", arguments={"order_id": 99}, outcome="success")]
    ref = _detect_reference("看看它的详情", records, 5, None)
    assert ref is None


def test_clarification_labels_are_clean_utf8():
    from app.agent import _generate_clarification
    from app.conversation_state import ConversationState

    clarification = _generate_clarification(
        "create_order",
        ["product_id", "quantity"],
        {},
        ConversationState(),
    )

    assert "商品 ID" in clarification
    assert "下单数量" in clarification
    assert "�" not in clarification
    assert "Ã" not in clarification


@pytest.mark.asyncio
async def test_clarification_when_missing_order_id():
    from app.agent import _check_missing_params, _generate_clarification
    from app.conversation_state import ConversationState

    missing = _check_missing_params("cancel_order", {})
    assert "order_id" in missing

    clarification = _generate_clarification(
        "cancel_order", missing, {}, ConversationState()
    )
    assert "订单 ID" in clarification or "请告诉我" in clarification


@pytest.mark.asyncio
async def test_infer_order_id_from_state():
    from app.agent import _check_missing_params, _infer_from_state, _generate_clarification
    from app.conversation_state import ConversationState

    state = ConversationState()
    state.last_order_id = 42

    missing = _check_missing_params("cancel_order", {})
    inferred = _infer_from_state("cancel_order", {}, state, missing)
    assert inferred.get("order_id") == 42

    clarification = _generate_clarification(
        "cancel_order", missing, {}, state
    )
    # No clarification needed since state has the id
    assert clarification == ""


@pytest.mark.asyncio
async def test_clarification_for_cart_operations():
    from app.agent import _check_missing_params, _generate_clarification
    from app.conversation_state import ConversationState

    missing = _check_missing_params("update_cart", {})
    assert "cart_id" in missing
    assert "quantity" in missing

    clarification = _generate_clarification(
        "update_cart", missing, {}, ConversationState()
    )
    assert "cartId" in clarification or "购物车" in clarification


@pytest.mark.asyncio
async def test_retry_on_timeout():
    from app.tools.registry import ToolRegistry
    from app.tools.confirmation import ConfirmationStore
    from app.clients.ecommerce_client import EcommerceApiError

    flaky = FlakyEcommerce(fail_count=2, fail_message="请求超时")
    registry = ToolRegistry(flaky, ConfirmationStore())

    result = await registry.execute(
        "search_products",
        {"keyword": "phone"},
        session_id="session-retry",
        access_token=None,
    )

    assert result.outcome == "success"
    assert flaky.call_count == 3  # 1 initial + 2 retries


@pytest.mark.asyncio
async def test_no_retry_on_non_retryable_error():
    from app.tools.registry import ToolRegistry
    from app.tools.confirmation import ConfirmationStore

    flaky = FlakyEcommerce(fail_count=5, fail_message="请先登录后再使用购物车")
    registry = ToolRegistry(flaky, ConfirmationStore())

    # Non-retryable error message: should not be retried
    # The error message contains "登录" which is in NON_RETRYABLE list
    # So after first failure it should stop
    result = await registry.execute(
        "search_products",
        {"keyword": "phone"},
        session_id="session-no-retry",
        access_token=None,
    )

    # With "登录" keyword, the error is non-retryable - should fail fast
    assert flaky.call_count == 1  # Should NOT retry beyond the first attempt


@pytest.mark.asyncio
async def test_retry_eventually_fails():
    from app.tools.registry import ToolRegistry
    from app.tools.confirmation import ConfirmationStore

    flaky = FlakyEcommerce(fail_count=10, fail_message="服务暂时不可用")
    registry = ToolRegistry(flaky, ConfirmationStore())

    result = await registry.execute(
        "search_products",
        {"keyword": "phone"},
        session_id="session-retry-fail",
        access_token=None,
    )

    assert result.outcome == "error"
    assert flaky.call_count <= 4  # 1 + MAX_RETRIES (3)


class FlakyEcommerce:
    def __init__(self, fail_count: int = 2, fail_message: str = "请求超时"):
        self.call_count = 0
        self._fail_count = fail_count
        self._fail_message = fail_message

    async def search_products(
        self,
        keyword: str,
        min_price: float | None = None,
        max_price: float | None = None,
        in_stock: bool | None = None,
        created_after: str | None = None,
    ):
        self.call_count += 1
        if self.call_count <= self._fail_count:
            from app.clients.ecommerce_client import EcommerceApiError
            raise EcommerceApiError(self._fail_message)
        return [{"id": 1, "name": f"{keyword} Phone", "price": 2999}]

    async def get_order_detail(self, order_id: int, access_token: str | None):
        return {"id": order_id, "orderNo": f"ORD-{order_id}", "status": 0, "finalAmount": 99}

    async def cancel_order(self, order_id: int, access_token: str | None):
        return {"id": order_id, "status": 4}
