from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Callable


_REDACTION_PATTERNS = (
    re.compile(r"(?i)(password|passwd|密码|api[_ -]?key|access[_ -]?token|jwt|bearer)\s*[:=：]\s*([^\s,;，；]+)"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    re.compile(r"\b(sk|ak)-[A-Za-z0-9_-]{12,}\b", re.IGNORECASE),
)


def redact_sensitive_text(value: str) -> str:
    """Remove common credential shapes before text enters short-term memory."""
    redacted = value
    redacted = _REDACTION_PATTERNS[0].sub(lambda match: f"{match.group(1)}: [REDACTED]", redacted)
    for pattern in _REDACTION_PATTERNS[1:]:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def conversation_identity(access_token: str | None) -> str:
    if not access_token:
        return "anonymous"
    return sha256(access_token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ConversationMessage:
    role: str
    content: str

    def as_model_input(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class _Conversation:
    messages: list[ConversationMessage]
    expires_at: float


MAX_RAW_MESSAGES = 6
COMPRESS_THRESHOLD = 10


class ConversationMemoryStore:
    """In-memory, identity-scoped conversation history with bounded size and TTL."""

    def __init__(
        self,
        *,
        max_messages: int = 12,
        ttl_seconds: int = 1800,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_messages < 2:
            raise ValueError("max_messages must be at least 2")
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be positive")
        self._max_messages = max_messages
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._items: dict[tuple[str, str], _Conversation] = {}
        self._lock = asyncio.Lock()

    async def get(
        self, session_id: str, access_token: str | None
    ) -> list[dict[str, str]]:
        key = self._key(session_id, access_token)
        async with self._lock:
            self._purge_expired_locked()
            conversation = self._items.get(key)
            if conversation is None:
                return []
            conversation.expires_at = self._clock() + self._ttl_seconds
            return [message.as_model_input() for message in conversation.messages]

    async def append_turn(
        self,
        session_id: str,
        access_token: str | None,
        user_message: str,
        assistant_message: str,
    ) -> None:
        key = self._key(session_id, access_token)
        messages = [
            ConversationMessage("user", redact_sensitive_text(user_message)),
            ConversationMessage("assistant", redact_sensitive_text(assistant_message)),
        ]
        async with self._lock:
            self._purge_expired_locked()
            conversation = self._items.get(key)
            if conversation is None:
                conversation = _Conversation(messages=[], expires_at=0)
                self._items[key] = conversation
            conversation.messages.extend(messages)

            if len(conversation.messages) > self._max_messages:
                has_summary = bool(
                    conversation.messages
                    and conversation.messages[0].content.startswith("[历史摘要]")
                )
                if has_summary:
                    excess = len(conversation.messages) - self._max_messages
                    keep_from = max(1, excess + 1)
                    conversation.messages = [conversation.messages[0]] + conversation.messages[keep_from:]
                else:
                    conversation.messages = conversation.messages[-self._max_messages :]

            conversation.expires_at = self._clock() + self._ttl_seconds

    async def clear(self, session_id: str, access_token: str | None) -> bool:
        key = self._key(session_id, access_token)
        async with self._lock:
            self._purge_expired_locked()
            return self._items.pop(key, None) is not None

    async def clear_session(self, session_id: str) -> int:
        """Delete all identities under a session, useful for explicit browser reset."""
        async with self._lock:
            self._purge_expired_locked()
            keys = [key for key in self._items if key[0] == session_id]
            for key in keys:
                del self._items[key]
            return len(keys)

    def _key(self, session_id: str, access_token: str | None) -> tuple[str, str]:
        return session_id, conversation_identity(access_token)

    def _purge_expired_locked(self) -> None:
        now = self._clock()
        expired = [key for key, value in self._items.items() if value.expires_at <= now]
        for key in expired:
            del self._items[key]

    async def summarize_and_compress(
        self, session_id: str, access_token: str | None
    ) -> tuple[str, int] | None:
        key = self._key(session_id, access_token)
        async with self._lock:
            conversation = self._items.get(key)
            if conversation is None:
                return None
            if len(conversation.messages) < COMPRESS_THRESHOLD:
                return None

            recent = conversation.messages[-MAX_RAW_MESSAGES:]
            older = conversation.messages[:-MAX_RAW_MESSAGES]
            if not older:
                return None

            summary = self._generate_rule_based_summary(older)
            summary_msg = ConversationMessage(
                "assistant",
                f"[历史摘要] {summary}",
            )
            compressed_count = len(older)
            conversation.messages = [summary_msg] + recent
            conversation.expires_at = self._clock() + self._ttl_seconds
            return summary, compressed_count

    @staticmethod
    def _generate_rule_based_summary(
        messages: list[ConversationMessage],
    ) -> str:
        text = " ".join(m.content for m in messages)
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

    def _replace_with_summary(
        self,
        session_id: str,
        access_token: str | None,
        summary: str,
    ) -> None:
        key = self._key(session_id, access_token)
        conversation = self._items.get(key)
        if conversation is None:
            return
        recent = conversation.messages[-MAX_RAW_MESSAGES:]
        summary_msg = ConversationMessage("assistant", f"[历史摘要] {summary}")
        conversation.messages = [summary_msg] + recent
        conversation.expires_at = self._clock() + self._ttl_seconds
