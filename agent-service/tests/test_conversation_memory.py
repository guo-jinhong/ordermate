from __future__ import annotations

import pytest

from app.conversation_memory import ConversationMemoryStore, redact_sensitive_text


@pytest.mark.asyncio
async def test_memory_is_scoped_by_session_and_login_identity():
    store = ConversationMemoryStore(max_messages=6, ttl_seconds=60)
    await store.append_turn("s1", "owner-token", "我的订单", "订单 8 待支付")

    assert len(await store.get("s1", "owner-token")) == 2
    assert await store.get("s1", "other-token") == []
    assert await store.get("s2", "owner-token") == []
    assert await store.get("s1", None) == []


@pytest.mark.asyncio
async def test_memory_is_bounded_to_latest_messages():
    store = ConversationMemoryStore(max_messages=4, ttl_seconds=60)
    await store.append_turn("s1", None, "first", "one")
    await store.append_turn("s1", None, "second", "two")
    await store.append_turn("s1", None, "third", "three")

    history = await store.get("s1", None)
    assert [item["content"] for item in history] == ["second", "two", "third", "three"]


@pytest.mark.asyncio
async def test_memory_expires_after_ttl():
    now = [100.0]
    store = ConversationMemoryStore(
        max_messages=6, ttl_seconds=10, clock=lambda: now[0]
    )
    await store.append_turn("s1", None, "hello", "hi")
    now[0] = 111.0

    assert await store.get("s1", None) == []


@pytest.mark.asyncio
async def test_clear_session_removes_all_login_identities():
    store = ConversationMemoryStore(max_messages=6, ttl_seconds=60)
    await store.append_turn("s1", None, "anonymous", "ok")
    await store.append_turn("s1", "jwt", "logged in", "ok")

    assert await store.clear_session("s1") == 2
    assert await store.get("s1", None) == []
    assert await store.get("s1", "jwt") == []


def test_sensitive_values_are_redacted_before_storage():
    text = "password: secret123 access_token=eyJabc.def.ghi api_key: sk-abcdefghijklmnop"
    redacted = redact_sensitive_text(text)

    assert "secret123" not in redacted
    assert "eyJabc.def.ghi" not in redacted
    assert "sk-abcdefghijklmnop" not in redacted


@pytest.mark.asyncio
async def test_summarize_triggers_at_threshold():
    from app.conversation_memory import COMPRESS_THRESHOLD

    store = ConversationMemoryStore(max_messages=20, ttl_seconds=60)
    for i in range(COMPRESS_THRESHOLD):
        await store.append_turn("s1", None, f"user msg {i}", f"assistant reply {i}")

    summary_result = await store.summarize_and_compress("s1", None)
    assert summary_result is not None
    summary, _ = summary_result
    assert len(summary) > 0

    history = await store.get("s1", None)
    assert len(history) < COMPRESS_THRESHOLD
    assert any("[历史摘要]" in msg.get("content", "") for msg in history)


@pytest.mark.asyncio
async def test_summarize_preserves_recent_messages():
    from app.conversation_memory import COMPRESS_THRESHOLD, MAX_RAW_MESSAGES

    store = ConversationMemoryStore(max_messages=20, ttl_seconds=60)
    for i in range(COMPRESS_THRESHOLD):
        await store.append_turn("s1", None, f"user {i}", f"reply {i}")

    summary_result = await store.summarize_and_compress("s1", None)
    assert summary_result is not None

    history = await store.get("s1", None)
    # 1 summary message + MAX_RAW_MESSAGES raw messages
    expected_len = 1 + MAX_RAW_MESSAGES
    assert len(history) == expected_len

    # Recent messages should be preserved verbatim (not in summary)
    raw_messages = [m for m in history if "[历史摘要]" not in m.get("content", "")]
    assert len(raw_messages) == MAX_RAW_MESSAGES


@pytest.mark.asyncio
async def test_rule_based_summary_extracts_entities():
    from app.conversation_memory import ConversationMemoryStore, ConversationMessage

    messages = [
        ConversationMessage("user", "搜索商品 #123 和 #456"),
        ConversationMessage("assistant", "找到了商品 123 和 456。"),
        ConversationMessage("user", "订单 789 怎么了？"),
        ConversationMessage("assistant", "订单 789 可以取消。预算 3000 元以内。"),
        ConversationMessage("user", "帮我取消它"),
        ConversationMessage("assistant", "已准备取消订单。"),
    ]
    summary = ConversationMemoryStore._generate_rule_based_summary(messages)

    assert "123" in summary or "商品" in summary
    assert "789" in summary or "订单" in summary
    assert "cancelled_order" in summary


@pytest.mark.asyncio
async def test_summary_injected_into_context():
    from app.conversation_memory import ConversationMemoryStore
    from app.conversation_state import ConversationStateStore

    store = ConversationMemoryStore(max_messages=20, ttl_seconds=60)
    for i in range(12):
        await store.append_turn("s-inject", None, f"user {i}", f"reply {i}")

    summary_result = await store.summarize_and_compress("s-inject", None)
    assert summary_result is not None
    summary_text, _ = summary_result

    # Verify state can hold the summary
    state_store = ConversationStateStore(ttl_seconds=60)
    state = await state_store.get("s-inject", None)
    state.record_summary(summary_text)
    await state_store.save("s-inject", None, state)

    retrieved = await state_store.get("s-inject", None)
    assert retrieved.last_summary == summary_text
    assert retrieved.last_summary_time > 0


@pytest.mark.asyncio
async def test_long_conversation_reference_resolution():
    from app.conversation_memory import ConversationMemoryStore

    store = ConversationMemoryStore(max_messages=20, ttl_seconds=60)
    # Simulate 20 turns of conversation
    for i in range(20):
        await store.append_turn(
            "s-long",
            None,
            f"第{i}轮: 关于商品 #{(i % 5) + 1}的讨论",
            f"第{i}轮回复: 商品 {(i % 5) + 1} 库存充足",
        )

    # Should have compressed at least once
    summary_result = await store.summarize_and_compress("s-long", None)
    history = await store.get("s-long", None)

    # After compression, history should be bounded
    assert len(history) <= 20
    # Summary message should exist to preserve early context
    summaries = [m for m in history if "[历史摘要]" in m.get("content", "")]
    assert len(summaries) >= 1
