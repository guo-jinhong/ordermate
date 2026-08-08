from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from app.conversation_memory import (
    ConversationMessage,
    conversation_identity,
    redact_sensitive_text,
)
from app.conversation_state import ConversationState
from app.tools.confirmation import PendingAction


class RedisConversationMemoryStore:
    """Redis-backed, identity-scoped history with the same contract as the local store."""

    def __init__(self, client: Any, *, max_messages: int, ttl_seconds: int) -> None:
        self._client = client
        self._max_messages = max_messages
        self._ttl_seconds = ttl_seconds

    async def get(self, session_id: str, access_token: str | None) -> list[dict[str, str]]:
        key = self._key(session_id, access_token)
        raw = await self._client.get(key)
        if raw is None:
            return []
        await self._client.expire(key, self._ttl_seconds)
        return json.loads(raw)

    async def append_turn(
        self,
        session_id: str,
        access_token: str | None,
        user_message: str,
        assistant_message: str,
    ) -> None:
        key = self._key(session_id, access_token)
        messages = await self.get(session_id, access_token)
        messages.extend(
            [
                ConversationMessage("user", redact_sensitive_text(user_message)).as_model_input(),
                ConversationMessage("assistant", redact_sensitive_text(assistant_message)).as_model_input(),
            ]
        )
        has_summary = bool(messages and messages[0].get("content", "").startswith("[历史摘要]"))
        if len(messages) > self._max_messages:
            if has_summary:
                excess = len(messages) - self._max_messages
                keep_from = max(1, excess + 1)
                messages = [messages[0]] + messages[keep_from:]
            else:
                messages = messages[-self._max_messages:]
        await self._client.set(key, json.dumps(messages, ensure_ascii=False), ex=self._ttl_seconds)

    async def summarize_and_compress(
        self, session_id: str, access_token: str | None
    ) -> tuple[str, int] | None:
        from app.conversation_memory import COMPRESS_THRESHOLD, MAX_RAW_MESSAGES

        key = self._key(session_id, access_token)
        raw = await self._client.get(key)
        if raw is None:
            return None
        messages = json.loads(raw)
        if len(messages) < COMPRESS_THRESHOLD:
            return None

        recent = messages[-MAX_RAW_MESSAGES:]
        older = messages[:-MAX_RAW_MESSAGES]
        if not older:
            return None

        summary = self._generate_rule_based_summary(older)
        summary_msg = {"role": "assistant", "content": f"[历史摘要] {summary}"}
        compressed_count = len(older)
        new_messages = [summary_msg] + recent
        await self._client.set(key, json.dumps(new_messages, ensure_ascii=False), ex=self._ttl_seconds)
        return summary, compressed_count

    @staticmethod
    def _generate_rule_based_summary(messages: list[dict[str, str]]) -> str:
        import re
        text = " ".join(m.get("content", "") for m in messages)
        product_ids = list(set(re.findall(r"商品\s*#?\s*(\d+)", text)))
        product_ids.extend(re.findall(r"product[_ ]?id\s*[:=]\s*(\d+)", text, re.IGNORECASE))
        product_ids = list(set(product_ids))
        order_ids = list(set(re.findall(r"订单\s*#?\s*(\d+)", text)))
        order_ids.extend(re.findall(r"order[_ ]?id\s*[:=]\s*(\d+)", text, re.IGNORECASE))
        order_ids = list(set(order_ids))
        price_match = re.findall(r"(?:预算|不超过|价格|¥|price)[^0-9]{0,10}(\d+(?:\.\d+)?)", text)
        budget = price_match[0] if price_match else None
        ops: list[str] = []
        if re.search(r"取消|cancel", text, re.IGNORECASE):
            ops.append("cancelled_order")
        if re.search(r"支付|付款|pay", text, re.IGNORECASE):
            ops.append("paid_order")
        if re.search(r"加入购物车|加购物车|add.?to.?cart", text, re.IGNORECASE):
            ops.append("added_to_cart")
        if re.search(r"下单|创建订单|create.?order", text, re.IGNORECASE):
            ops.append("created_order")
        parts: list[str] = []
        if product_ids:
            parts.append(f"涉及商品: {','.join(product_ids)}")
        if order_ids:
            parts.append(f"涉及订单: {','.join(order_ids)}")
        if budget:
            parts.append(f"预算上限: {budget}")
        if ops:
            parts.append(f"操作记录: {','.join(ops)}")
        if not parts:
            return "早前对话涉及商品浏览与一般性咨询。"
        return "; ".join(parts)

    async def clear(self, session_id: str, access_token: str | None) -> bool:
        return bool(await self._client.delete(self._key(session_id, access_token)))

    async def clear_session(self, session_id: str) -> int:
        pattern = f"agent:memory:{self._session_hash(session_id)}:*"
        keys = [key async for key in self._client.scan_iter(match=pattern)]
        return int(await self._client.delete(*keys)) if keys else 0

    def _key(self, session_id: str, access_token: str | None) -> str:
        return f"agent:memory:{self._session_hash(session_id)}:{conversation_identity(access_token)}"

    @staticmethod
    def _session_hash(session_id: str) -> str:
        return sha256(session_id.encode("utf-8")).hexdigest()


class RedisConfirmationStore:
    """Single-use confirmation tokens backed by Redis so restarts do not lose them."""

    def __init__(self, client: Any, ttl_minutes: int = 10) -> None:
        self._client = client
        self._ttl_seconds = int(timedelta(minutes=ttl_minutes).total_seconds())

    async def issue(
        self,
        session_id: str,
        action: str,
        arguments: dict[str, Any],
        authorization_fingerprint: str,
    ) -> PendingAction:
        from secrets import token_urlsafe

        pending = PendingAction(
            token=token_urlsafe(24),
            session_id=session_id,
            action=action,
            arguments=arguments,
            authorization_fingerprint=authorization_fingerprint,
            expires_at=datetime.now(UTC) + timedelta(seconds=self._ttl_seconds),
        )
        await self._client.set(self._key(pending.token), self._serialize(pending), ex=self._ttl_seconds)
        return pending

    async def consume(
        self, token: str, session_id: str, authorization_fingerprint: str
    ) -> PendingAction | None:
        key = self._key(token)
        raw = await self._client.get(key)
        if raw is None:
            return None
        pending = self._deserialize(raw)
        if pending.session_id != session_id or pending.authorization_fingerprint != authorization_fingerprint:
            return None
        deleted = await self._client.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end return 0",
            1,
            key,
            raw,
        )
        return pending if deleted else None

    @staticmethod
    def _key(token: str) -> str:
        return f"agent:confirmation:{token}"

    @staticmethod
    def _serialize(pending: PendingAction) -> str:
        return json.dumps(
            {
                "token": pending.token,
                "session_id": pending.session_id,
                "action": pending.action,
                "arguments": pending.arguments,
                "authorization_fingerprint": pending.authorization_fingerprint,
                "expires_at": pending.expires_at.isoformat(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    @staticmethod
    def _deserialize(raw: str) -> PendingAction:
        value = json.loads(raw)
        return PendingAction(
            token=value["token"],
            session_id=value["session_id"],
            action=value["action"],
            arguments=value["arguments"],
            authorization_fingerprint=value["authorization_fingerprint"],
            expires_at=datetime.fromisoformat(value["expires_at"]),
        )


class RedisConversationStateStore:
    """Redis-backed, identity-scoped structured conversation state."""

    def __init__(self, client: Any, *, ttl_seconds: int) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds

    async def get(
        self, session_id: str, access_token: str | None
    ) -> ConversationState:
        key = self._key(session_id, access_token)
        raw = await self._client.get(key)
        if raw is None:
            state = ConversationState()
            if access_token:
                anonymous = await self._load_state(self._key(session_id, None))
                if anonymous is not None and anonymous.has_product_context():
                    state.copy_product_context_from(anonymous)
            return state
        await self._client.expire(key, self._ttl_seconds)
        state = self._deserialize_state(raw)
        if access_token and not state.has_product_context():
            anonymous = await self._load_state(self._key(session_id, None))
            if anonymous is not None and anonymous.has_product_context():
                state.copy_product_context_from(anonymous)
        return state

    async def _load_state(self, key: str) -> ConversationState | None:
        raw = await self._client.get(key)
        if raw is None:
            return None
        await self._client.expire(key, self._ttl_seconds)
        return self._deserialize_state(raw)

    @staticmethod
    def _deserialize_state(raw: str) -> ConversationState:
        data = json.loads(raw)
        state = ConversationState()
        state.last_order_id = data.get("last_order_id")
        state.last_order_no = data.get("last_order_no")
        state.last_product_keyword = data.get("last_product_keyword")
        state.last_product_id = data.get("last_product_id")
        state.last_product_name = data.get("last_product_name")
        state.shown_product_ids = data.get("shown_product_ids", [])
        state.last_cart_viewed = data.get("last_cart_viewed", False)
        state.last_knowledge_topic = data.get("last_knowledge_topic")
        state.turn_count = data.get("turn_count", 0)
        state.last_topic = data.get("last_topic")
        return state

    async def save(
        self, session_id: str, access_token: str | None, state: ConversationState
    ) -> None:
        key = self._key(session_id, access_token)
        data = {
            "last_order_id": state.last_order_id,
            "last_order_no": state.last_order_no,
            "last_product_keyword": state.last_product_keyword,
            "last_product_id": state.last_product_id,
            "last_product_name": state.last_product_name,
            "shown_product_ids": state.shown_product_ids,
            "last_cart_viewed": state.last_cart_viewed,
            "last_knowledge_topic": state.last_knowledge_topic,
            "turn_count": state.turn_count,
            "last_topic": state.last_topic,
        }
        await self._client.set(
            key, json.dumps(data, ensure_ascii=False), ex=self._ttl_seconds
        )

    async def clear_session(self, session_id: str) -> int:
        pattern = f"agent:state:{self._session_hash(session_id)}:*"
        keys = [key async for key in self._client.scan_iter(match=pattern)]
        return int(await self._client.delete(*keys)) if keys else 0

    def _key(self, session_id: str, access_token: str | None) -> str:
        return f"agent:state:{self._session_hash(session_id)}:{conversation_identity(access_token)}"

    @staticmethod
    def _session_hash(session_id: str) -> str:
        return sha256(session_id.encode("utf-8")).hexdigest()
