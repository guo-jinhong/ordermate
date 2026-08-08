from __future__ import annotations

import pytest

from app.conversation_state import (
    ConversationState,
    ConversationStateStore,
    conversation_identity,
)


def test_conversation_identity_anonymous():
    assert conversation_identity(None) == "anonymous"
    assert conversation_identity("") == "anonymous"


def test_conversation_identity_hashes_token():
    token = "some-jwt-token"
    identity1 = conversation_identity(token)
    identity2 = conversation_identity(token)
    assert identity1 == identity2
    assert identity1 != "anonymous"
    assert token not in identity1


class TestConversationState:
    def test_initial_state(self):
        state = ConversationState()
        assert state.last_order_id is None
        assert state.last_product_keyword is None
        assert state.last_topic is None
        assert state.turn_count == 0

    def test_record_product_search(self):
        state = ConversationState()
        state.record_product_search("smartphone")
        assert state.last_product_keyword == "smartphone"
        assert state.last_topic == "product"
        assert state.turn_count == 1

    def test_resolve_product_id_by_recent_product_name(self):
        state = ConversationState()
        state.record_product_search(
            "手机",
            product_id=104,
            product_name="OPPO Find X7",
            shown_product_ids=[104, 126, 132],
            shown_products=[
                {"id": 104, "name": "OPPO Find X7"},
                {"id": 126, "name": "小米 Redmi 13C"},
                {"id": 132, "name": "iQOO Neo9"},
            ],
        )

        assert state.resolve_product_id("把刚刚的红米手机加入购物车", None) == 126

    def test_record_order(self):
        state = ConversationState()
        state.record_order(123, "ORD-123")
        assert state.last_order_id == 123
        assert state.last_order_no == "ORD-123"
        assert state.last_topic == "order"
        assert state.turn_count == 1

    def test_resolve_order_id_explicit(self):
        state = ConversationState()
        state.record_order(100)
        assert state.resolve_order_id("取消订单 200", 200) == 200

    def test_resolve_order_id_by_reference(self):
        state = ConversationState()
        state.record_order(100)
        assert state.resolve_order_id("取消它", None) == 100

    def test_resolve_order_id_no_context(self):
        state = ConversationState()
        assert state.resolve_order_id("取消它", None) is None

    def test_resolve_product_keyword_explicit(self):
        state = ConversationState()
        state.record_product_search("laptop")
        assert state.resolve_product_keyword("搜索手机", "smartphone") == "smartphone"

    def test_resolve_product_keyword_by_reference(self):
        state = ConversationState()
        state.record_product_search("smartphone")
        assert state.resolve_product_keyword("它有库存吗", None) == "smartphone"

    def test_resolve_product_keyword_no_context(self):
        state = ConversationState()
        assert state.resolve_product_keyword("它有库存吗", None) is None


class TestConversationStateStore:
    @pytest.mark.asyncio
    async def test_get_creates_new_state(self):
        store = ConversationStateStore()
        state = await store.get("session-1", None)
        assert isinstance(state, ConversationState)
        assert state.turn_count == 0

    @pytest.mark.asyncio
    async def test_save_and_get_preserves_state(self):
        store = ConversationStateStore()
        state = await store.get("session-1", None)
        state.record_product_search("smartphone")
        await store.save("session-1", None, state)

        loaded = await store.get("session-1", None)
        assert loaded.last_product_keyword == "smartphone"
        assert loaded.last_topic == "product"

    @pytest.mark.asyncio
    async def test_different_sessions_are_isolated(self):
        store = ConversationStateStore()
        state1 = await store.get("session-1", None)
        state1.record_product_search("phone")
        await store.save("session-1", None, state1)

        state2 = await store.get("session-2", None)
        assert state2.last_product_keyword is None

    @pytest.mark.asyncio
    async def test_different_identities_are_isolated(self):
        store = ConversationStateStore()
        state1 = await store.get("session-1", "token-a")
        state1.record_order(1)
        await store.save("session-1", "token-a", state1)

        state2 = await store.get("session-1", "token-b")
        assert state2.last_order_id is None

    @pytest.mark.asyncio
    async def test_clear_session(self):
        store = ConversationStateStore()
        state = await store.get("session-1", None)
        state.record_order(100)
        await store.save("session-1", None, state)

        cleared = await store.clear_session("session-1")
        assert cleared >= 1

        reloaded = await store.get("session-1", None)
        assert reloaded.last_order_id is None

    @pytest.mark.asyncio
    async def test_clear_session_with_multiple_identities(self):
        store = ConversationStateStore()
        state1 = await store.get("session-1", "token-a")
        state1.record_order(1)
        await store.save("session-1", "token-a", state1)

        state2 = await store.get("session-1", "token-b")
        state2.record_order(2)
        await store.save("session-1", "token-b", state2)

        cleared = await store.clear_session("session-1")
        assert cleared >= 2

    @pytest.mark.asyncio
    async def test_ttl_expiry(self):
        fake_time = [0.0]
        store = ConversationStateStore(ttl_seconds=10, clock=lambda: fake_time[0])

        state = await store.get("s1", None)
        state.record_order(1)
        await store.save("s1", None, state)

        fake_time[0] = 5.0
        loaded = await store.get("s1", None)
        assert loaded.last_order_id == 1

        fake_time[0] = 15.0
        reloaded = await store.get("s1", None)
        assert reloaded.last_order_id is None
