from __future__ import annotations

import json

import pytest

from app.redis_stores import RedisConfirmationStore, RedisConversationMemoryStore


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int):
        self.values[key] = value

    async def expire(self, key: str, seconds: int):
        return key in self.values

    async def delete(self, *keys: str):
        deleted = sum(key in self.values for key in keys)
        for key in keys:
            self.values.pop(key, None)
        return deleted

    async def scan_iter(self, *, match: str):
        prefix = match[:-1]
        for key in list(self.values):
            if key.startswith(prefix):
                yield key

    async def eval(self, script: str, numkeys: int, key: str, raw: str):
        if self.values.get(key) != raw:
            return 0
        return await self.delete(key)


@pytest.mark.asyncio
async def test_redis_memory_keeps_identity_isolation_and_clears_session():
    store = RedisConversationMemoryStore(FakeRedis(), max_messages=4, ttl_seconds=60)
    await store.append_turn("session", "owner", "first", "one")
    await store.append_turn("session", "owner", "second", "two")
    await store.append_turn("session", "other", "private", "reply")

    assert [item["content"] for item in await store.get("session", "owner")] == [
        "first", "one", "second", "two"
    ]
    assert await store.get("session", None) == []
    assert await store.clear_session("session") == 2


@pytest.mark.asyncio
async def test_redis_confirmation_is_bound_and_single_use():
    store = RedisConfirmationStore(FakeRedis())
    pending = await store.issue("session", "cancel_order", {"order_id": 9}, "owner")

    assert await store.consume(pending.token, "other-session", "owner") is None
    consumed = await store.consume(pending.token, "session", "owner")
    assert consumed is not None
    assert consumed.arguments == {"order_id": 9}
    assert await store.consume(pending.token, "session", "owner") is None
