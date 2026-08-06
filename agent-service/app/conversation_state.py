from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Callable


_REFERRAL_PATTERNS = {
    "order": [
        r"它", r"这个订单", r"那个订单", r"这笔订单", r"该订单", r"此订单",
        r"刚才的订单", r"刚刚的订单", r"上面的订单",
    ],
    "product": [
        r"它", r"这个商品", r"那个商品", r"这款", r"这款产品", r"该商品",
        r"刚才的商品", r"刚刚的商品",
    ],
}


def conversation_identity(access_token: str | None) -> str:
    if not access_token:
        return "anonymous"
    return sha256(access_token.encode("utf-8")).hexdigest()


@dataclass
class ConversationState:
    """Structured conversational state for the demo agent.

    Tracks the last-referenced domain entities so follow-up utterances like
    "cancel it" or "show me details" can be resolved without repeating the
    full entity reference.
    """

    last_order_id: int | None = None
    last_order_no: str | None = None
    last_product_keyword: str | None = None
    last_product_id: int | None = None
    last_product_name: str | None = None
    shown_product_ids: list[int] = field(default_factory=list)
    shown_products: list[dict[str, object]] = field(default_factory=list)
    last_cart_viewed: bool = False
    cart_items: list[dict[str, object]] = field(default_factory=list)
    pending_confirmation_token: str | None = None
    pending_confirmation_action: str | None = None
    pending_confirmation_arguments: dict[str, object] | None = None
    last_knowledge_topic: str | None = None
    turn_count: int = 0
    last_topic: str | None = None
    updated_at: float = field(default_factory=time.monotonic)
    compressed_turn_count: int = 0
    last_summary: str | None = None
    last_summary_time: float = 0.0

    def has_product_context(self) -> bool:
        return self.last_product_id is not None or bool(self.last_product_keyword)

    def copy_product_context_from(self, other: "ConversationState") -> None:
        self.last_product_keyword = other.last_product_keyword
        self.last_product_id = other.last_product_id
        self.last_product_name = other.last_product_name
        self.shown_product_ids = list(other.shown_product_ids)
        self.shown_products = [dict(item) for item in other.shown_products]
        if other.last_topic == "product":
            self.last_topic = "product"

    def record_order(self, order_id: int | None, order_no: str | None = None) -> None:
        self.last_order_id = order_id
        self.last_order_no = order_no
        self.last_topic = "order"
        self.turn_count += 1
        self.updated_at = time.monotonic()

    def record_product_search(
        self,
        keyword: str,
        product_id: int | None = None,
        product_name: str | None = None,
        shown_product_ids: list[int] | None = None,
        shown_products: list[dict[str, object]] | None = None,
    ) -> None:
        self.last_product_keyword = keyword
        if product_id is not None:
            self.last_product_id = product_id
        if product_name:
            self.last_product_name = product_name
        if shown_product_ids is not None:
            self.shown_product_ids = shown_product_ids
        if shown_products is not None:
            self.shown_products = shown_products
        self.last_topic = "product"
        self.turn_count += 1
        self.updated_at = time.monotonic()

    def record_product(self, product_id: int, product_name: str | None = None) -> None:
        resolved_name = product_name
        if resolved_name is None:
            for product in self.shown_products:
                if product.get("id") == product_id and product.get("name"):
                    resolved_name = str(product["name"])
                    break
        self.last_product_id = product_id
        if resolved_name:
            self.last_product_name = resolved_name
            if not any(item.get("id") == product_id for item in self.shown_products):
                self.shown_products.insert(0, {"id": product_id, "name": resolved_name})
        else:
            self.last_product_name = None
        self.last_topic = "product"
        self.turn_count += 1
        self.updated_at = time.monotonic()

    def resolve_product_id(self, message: str, explicit: int | None) -> int | None:
        if explicit is not None:
            return explicit
        matched = self.find_product_id_by_message(message)
        if matched is not None:
            return matched
        if self.last_topic == "product" and self._matches_any(
            message, [r"加入购物车", r"加购物车", r"放购物车", r"添加购物车", r"购买", r"买", r"下单"]
        ):
            return self.last_product_id
        if self._matches_any(message, _REFERRAL_PATTERNS["product"]):
            return self.last_product_id
        return None

    def find_product_id_by_message(self, message: str) -> int | None:
        normalized_message = _normalize_product_text(message)
        if not normalized_message:
            return None
        for product in self.shown_products:
            product_id = product.get("id")
            name = product.get("name")
            if product_id is None or not name:
                continue
            normalized_name = _normalize_product_text(str(name))
            if normalized_name and normalized_name in normalized_message:
                return int(product_id)
            for token in _product_name_tokens(str(name)):
                if token in normalized_message:
                    return int(product_id)
        return None

    def product_name_for_id(self, product_id: int | None) -> str | None:
        if product_id is None:
            return None
        if self.last_product_id == product_id and self.last_product_name:
            return self.last_product_name
        for product in self.shown_products:
            if product.get("id") == product_id and product.get("name"):
                return str(product["name"])
        return None

    def record_cart_view(self) -> None:
        self.last_cart_viewed = True
        self.last_topic = "cart"
        self.turn_count += 1
        self.updated_at = time.monotonic()

    def record_cart_items(self, items: list[dict[str, object]]) -> None:
        normalized_items: list[dict[str, object]] = []
        for item in items:
            cart_id = item.get("cartId") or item.get("cart_id") or item.get("id")
            product_id = item.get("productId") or item.get("product_id")
            product_name = item.get("productName") or item.get("product_name") or item.get("name")
            quantity = item.get("quantity")
            if cart_id is None:
                continue
            normalized_items.append(
                {
                    "cartId": int(cart_id),
                    "productId": int(product_id) if product_id is not None else None,
                    "productName": str(product_name) if product_name else "",
                    "quantity": int(quantity) if quantity is not None else None,
                }
            )
        self.cart_items = normalized_items
        self.record_cart_view()

    def resolve_cart_id(self, message: str, explicit: int | None) -> int | None:
        if explicit is not None:
            return explicit
        if not self.cart_items:
            return None
        normalized_message = _normalize_product_text(message)
        for item in self.cart_items:
            cart_id = item.get("cartId")
            product_name = item.get("productName")
            if cart_id is None or not product_name:
                continue
            normalized_name = _normalize_product_text(str(product_name))
            if normalized_name and normalized_name in normalized_message:
                return int(cart_id)
            for token in _product_name_tokens(str(product_name)):
                if token in normalized_message:
                    return int(cart_id)
        if len(self.cart_items) == 1 and self._matches_any(
            message, [r"它", r"这个", r"那个", r"刚刚", r"刚才", r"购物车", r"数量", r"改", r"修改"]
        ):
            cart_id = self.cart_items[0].get("cartId")
            return int(cart_id) if cart_id is not None else None
        return None

    def cart_quantity_for_id(self, cart_id: int | None) -> int | None:
        if cart_id is None:
            return None
        for item in self.cart_items:
            if item.get("cartId") == cart_id:
                quantity = item.get("quantity")
                return int(quantity) if quantity is not None else None
        return None

    def remember_confirmation(self, token: str, action: str, arguments: dict[str, object]) -> None:
        self.pending_confirmation_token = token
        self.pending_confirmation_action = action
        self.pending_confirmation_arguments = dict(arguments)
        self.updated_at = time.monotonic()

    def clear_confirmation(self) -> None:
        self.pending_confirmation_token = None
        self.pending_confirmation_action = None
        self.pending_confirmation_arguments = None
        self.updated_at = time.monotonic()

    def record_knowledge_topic(self, topic: str) -> None:
        self.last_knowledge_topic = topic
        self.last_topic = "knowledge"
        self.turn_count += 1
        self.updated_at = time.monotonic()

    def resolve_order_id(self, message: str, explicit: int | None) -> int | None:
        if explicit is not None:
            return explicit
        if self._matches_any(message, _REFERRAL_PATTERNS["order"]):
            return self.last_order_id
        return None

    def record_summary(self, summary: str, compressed_turns: int = 0) -> None:
        self.last_summary = summary
        self.last_summary_time = time.monotonic()
        self.compressed_turn_count += compressed_turns

    def resolve_product_keyword(self, message: str, explicit: str | None) -> str | None:
        if explicit:
            return explicit
        if self.last_topic == "product" and self._matches_any(
            message, [r"有哪些", r"列表", r"这些", r"推荐", r"搜索", r"还有", r"更多"]
        ):
            return self.last_product_keyword
        if self._matches_any(message, _REFERRAL_PATTERNS["product"]):
            return self.last_product_keyword
        return None

    @staticmethod
    def _matches_any(message: str, patterns: list[str]) -> bool:
        return any(re.search(pattern, message) for pattern in patterns)


def _normalize_product_text(text: str) -> str:
    normalized = text.lower()
    normalized = normalized.replace("redmi", "红米")
    normalized = normalized.replace("小米", "xiaomi")
    normalized = normalized.replace(" ", "")
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", normalized)


def _product_name_tokens(name: str) -> list[str]:
    normalized = _normalize_product_text(name)
    tokens = {normalized}
    if "红米" in normalized:
        tokens.add("红米")
    if "xiaomi" in normalized or "红米" in normalized:
        tokens.add("小米")
    for part in re.split(r"[\s\-_/]+", name.lower()):
        part = _normalize_product_text(part)
        if len(part) >= 2:
            tokens.add(part)
    return sorted(tokens, key=len, reverse=True)


class ConversationStateStore:
    """In-memory store for structured conversation state.

    Keyed by (session_id, identity) so switching login identities under the
    same browser session does not leak state between users.
    """

    def __init__(
        self,
        *,
        ttl_seconds: int = 1800,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be positive")
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._states: dict[tuple[str, str], ConversationState] = {}
        self._lock = asyncio.Lock()

    async def get(
        self, session_id: str, access_token: str | None
    ) -> ConversationState:
        key = self._key(session_id, access_token)
        async with self._lock:
            self._purge_expired_locked()
            state = self._states.get(key)
            if state is None:
                state = ConversationState()
                self._states[key] = state
            if access_token and not state.has_product_context():
                anonymous = self._states.get((session_id, "anonymous"))
                if anonymous is not None and anonymous.has_product_context():
                    state.copy_product_context_from(anonymous)
            return state

    async def save(
        self, session_id: str, access_token: str | None, state: ConversationState
    ) -> None:
        key = self._key(session_id, access_token)
        async with self._lock:
            self._purge_expired_locked()
            state.updated_at = self._clock()
            self._states[key] = state

    async def clear_session(self, session_id: str) -> int:
        async with self._lock:
            self._purge_expired_locked()
            keys = [key for key in self._states if key[0] == session_id]
            for key in keys:
                del self._states[key]
            return len(keys)

    def _key(self, session_id: str, access_token: str | None) -> tuple[str, str]:
        return session_id, conversation_identity(access_token)

    def _purge_expired_locked(self) -> None:
        now = self._clock()
        expired = [
            key
            for key, state in self._states.items()
            if now - state.updated_at >= self._ttl_seconds
        ]
        for key in expired:
            del self._states[key]
