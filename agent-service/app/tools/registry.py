from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.clients.ecommerce_client import EcommerceApiError
from app.knowledge_base import KnowledgeBase
from app.product_terms import translate_product_keyword
from app.schemas import Confirmation
from app.tools.confirmation import ConfirmationStore, fingerprint_access_token


logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = [1.0, 2.0, 4.0]

_RETRYABLE_ERROR_MESSAGES = (
    "unavailable",
    "timeout",
    "connection",
    "503",
    "502",
    "500",
    "temporarily",
    "暂时",
    "超时",
    "服务不可用",
)

_NON_RETRYABLE_ERROR_MESSAGES = (
    "参数",
    "参数不完整",
    "必须是",
    "必须为",
    "待支付",
    "不存在",
    "登录",
    "库存不足",
    "重复",
    "auth",
    "认证",
    "权限",
)


@dataclass
class ToolExecution:
    output: dict[str, Any]
    outcome: str
    confirmation: Confirmation | None = None


class RecentOrderTracker:
    def __init__(self) -> None:
        self._orders: dict[str, datetime] = {}
        self._lock = asyncio.Lock()

    async def is_recent_order(self, key: str) -> bool:
        async with self._lock:
            now = datetime.now(UTC)
            self._purge_expired(now)
            return key in self._orders

    async def record_order(self, key: str) -> None:
        async with self._lock:
            now = datetime.now(UTC)
            self._purge_expired(now)
            self._orders[key] = now

    def _purge_expired(self, now: datetime) -> None:
        expired_threshold = now - timedelta(minutes=5)
        expired = [key for key, timestamp in self._orders.items() if timestamp < expired_threshold]
        for key in expired:
            self._orders.pop(key, None)


class ToolRegistry:
    def __init__(self, ecommerce_client: Any, confirmations: ConfirmationStore, knowledge_base: KnowledgeBase | None = None) -> None:
        self._ecommerce = ecommerce_client
        self._confirmations = confirmations
        self._knowledge_base = knowledge_base or KnowledgeBase()
        self._recent_orders = RecentOrderTracker()

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        session_id: str,
        access_token: str | None,
    ) -> ToolExecution:
        last_result: ToolExecution | None = None
        for attempt in range(MAX_RETRIES + 1):
            result = await self._execute_once(
                name,
                arguments,
                session_id=session_id,
                access_token=access_token,
            )
            last_result = result
            if result.outcome != "error":
                return result
            if attempt >= MAX_RETRIES:
                break
            error_message = result.output.get("error", "")
            if not self._is_retryable_error_message(error_message):
                break
            delay = RETRY_DELAY_SECONDS[attempt]
            logger.warning(
                "Tool '%s' attempt %d failed (%s), retrying in %.1fs",
                name, attempt + 1, error_message, delay,
            )
            await asyncio.sleep(delay)
        assert last_result is not None
        return last_result

    async def _execute_once(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        session_id: str,
        access_token: str | None,
    ) -> ToolExecution:
        try:
            if name == "search_knowledge_base":
                data = self._knowledge_base.search(self._string_arg(arguments, "query"))
            elif name == "search_products":
                keyword = translate_product_keyword(self._string_arg(arguments, "keyword"))
                min_price = self._optional_float_arg(arguments, "min_price")
                max_price = self._optional_float_arg(arguments, "max_price")
                in_stock = self._optional_bool_arg(arguments, "in_stock")
                created_after = self._optional_iso_datetime_arg(arguments, "created_after")
                data = await self._ecommerce.search_products(
                    keyword, min_price, max_price, in_stock, created_after
                )
            elif name == "get_product_detail":
                data = await self._ecommerce.get_product_detail(
                    self._positive_int_arg(arguments, "product_id")
                )
            elif name == "get_cart":
                self._require_auth(access_token)
                data = await self._ecommerce.get_cart(access_token)
            elif name == "add_to_cart":
                self._require_auth(access_token)
                product_id = self._positive_int_arg(arguments, "product_id")
                quantity = self._positive_int_arg(arguments, "quantity")
                await self._check_stock(product_id, quantity)
                self._check_quantity_limit(quantity)
                data = await self._ecommerce.add_to_cart(product_id, quantity, access_token)
            elif name in {
                "update_cart",
                "remove_from_cart",
                "clear_cart",
                "update_cart_items",
                "create_order",
                "pay_order",
            }:
                self._require_auth(access_token)
                if name == "update_cart":
                    quantity = self._positive_int_arg(arguments, "quantity")
                    self._check_quantity_limit(quantity)
                elif name == "update_cart_items":
                    items = self._cart_update_items_arg(arguments)
                    for item in items:
                        self._check_quantity_limit(item["quantity"])
                elif name == "create_order":
                    product_id = self._positive_int_arg(arguments, "product_id")
                    quantity = self._positive_int_arg(arguments, "quantity")
                    await self._check_stock(product_id, quantity)
                    await self._check_duplicate_order(session_id, product_id, quantity, access_token)
                return await self._prepare_confirmation(session_id, name, arguments, access_token)
            elif name == "get_my_orders":
                self._require_auth(access_token)
                data = await self._ecommerce.get_my_orders(access_token)
            elif name == "get_order_detail":
                self._require_auth(access_token)
                data = await self._ecommerce.get_order_detail(
                    self._positive_int_arg(arguments, "order_id"), access_token
                )
            elif name == "cancel_order":
                self._require_auth(access_token)
                return await self._prepare_cancellation(session_id, arguments, access_token)
            else:
                return ToolExecution(
                    output={"ok": False, "error": f"未知工具: {name}"},
                    outcome="error",
                )
            return ToolExecution(output={"ok": True, "data": data}, outcome="success")
        except (EcommerceApiError, KeyError, TypeError, ValueError) as exc:
            return ToolExecution(
                output={"ok": False, "error": self._friendly_error(exc)},
                outcome="error",
            )

    @staticmethod
    def _is_retryable_error_message(message: str) -> bool:
        lowered = message.lower()
        if any(kw.lower() in lowered for kw in _NON_RETRYABLE_ERROR_MESSAGES):
            return False
        return any(kw.lower() in lowered for kw in _RETRYABLE_ERROR_MESSAGES)

    async def _check_stock(self, product_id: int, quantity: int) -> None:
        product = await self._ecommerce.get_product_detail(product_id)
        if not isinstance(product, dict):
            raise EcommerceApiError("商品信息获取失败。")
        stock = product.get("stock")
        if stock is None:
            raise EcommerceApiError("无法获取商品库存信息。")
        if int(stock) < quantity:
            raise EcommerceApiError(f"库存不足，当前库存为 {stock} 件，无法购买 {quantity} 件。")

    @staticmethod
    def _check_quantity_limit(quantity: int) -> None:
        if quantity > 99:
            raise ValueError("单个商品最多购买99件。")

    async def _check_duplicate_order(
        self, session_id: str, product_id: int, quantity: int, access_token: str | None
    ) -> None:
        order_key = f"{session_id}:{access_token}:{product_id}:{quantity}"
        if await self._recent_orders.is_recent_order(order_key):
            raise EcommerceApiError("5分钟内已提交过相同的订单，请稍后再试。")

    async def _prepare_cancellation(
        self,
        session_id: str,
        arguments: dict[str, Any],
        access_token: str,
    ) -> ToolExecution:
        order_id = self._positive_int_arg(arguments, "order_id")

        order = await self._ecommerce.get_order_detail(order_id, access_token)
        if not isinstance(order, dict):
            raise EcommerceApiError("订单接口返回了无法识别的数据。")
        if order.get("status") != 0:
            raise EcommerceApiError("只有待支付订单可以取消。")

        order_no = order.get("orderNo") or f"#{order_id}"
        final_amount = order.get("finalAmount")
        pending = await self._confirmations.issue(
            session_id=session_id,
            action="cancel_order",
            arguments={"order_id": order_id},
            authorization_fingerprint=fingerprint_access_token(access_token),
        )
        amount_text = (
            f"，金额 ¥{final_amount}" if final_amount is not None else ""
        )
        confirmation = Confirmation(
            token=pending.token,
            action=pending.action,
            description=f"取消订单 {order_no}{amount_text}",
            arguments={
                "order_id": order_id,
                "order_no": order_no,
                "final_amount": final_amount,
                "status": order.get("status"),
            },
        )
        return ToolExecution(
            output={
                "ok": False,
                "confirmation_required": True,
                "message": "订单已校验，等待用户明确确认后执行取消。",
                "data": order,
            },
            outcome="confirmation_required",
            confirmation=confirmation,
        )

    async def _prepare_confirmation(
        self,
        session_id: str,
        action: str,
        arguments: dict[str, Any],
        access_token: str,
    ) -> ToolExecution:
        normalized = self._normalize_pending_arguments(action, arguments)
        description = await self._confirmation_description(action, normalized, access_token)
        pending = await self._confirmations.issue(
            session_id=session_id,
            action=action,
            arguments=normalized,
            authorization_fingerprint=fingerprint_access_token(access_token),
        )
        if action == "create_order":
            order_key = f"{session_id}:{access_token}:{normalized['product_id']}:{normalized['quantity']}"
            await self._recent_orders.record_order(order_key)
        return ToolExecution(
            output={
                "ok": False,
                "confirmation_required": True,
                "message": "操作已准备好，等待用户明确确认后执行。",
                "data": normalized,
            },
            outcome="confirmation_required",
            confirmation=Confirmation(
                token=pending.token,
                action=pending.action,
                description=description,
                arguments=normalized,
            ),
        )

    def _normalize_pending_arguments(
        self, action: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        if action == "update_cart":
            return {
                "cart_id": self._positive_int_arg(arguments, "cart_id"),
                "quantity": self._positive_int_arg(arguments, "quantity"),
            }
        if action == "remove_from_cart":
            return {"cart_id": self._positive_int_arg(arguments, "cart_id")}
        if action == "clear_cart":
            return {}
        if action == "update_cart_items":
            return {
                "items": self._cart_update_items_arg(arguments),
                "quantity": self._positive_int_arg(arguments, "quantity"),
            }
        if action == "create_order":
            return {
                "product_id": self._positive_int_arg(arguments, "product_id"),
                "quantity": self._positive_int_arg(arguments, "quantity"),
                "address_id": int(arguments.get("address_id") or 1),
                "payment_method": str(arguments.get("payment_method") or "DEMO"),
            }
        if action == "pay_order":
            return {"order_id": self._positive_int_arg(arguments, "order_id")}
        raise ValueError(f"不支持的操作: {action}")

    async def _confirmation_description(
        self, action: str, arguments: dict[str, Any], access_token: str
    ) -> str:
        if action == "update_cart":
            return f"将购物车项 #{arguments['cart_id']} 数量修改为 {arguments['quantity']}"
        if action == "remove_from_cart":
            return f"删除购物车项 #{arguments['cart_id']}"
        if action == "clear_cart":
            return "清空当前购物车"
        if action == "update_cart_items":
            items = arguments["items"]
            quantity = arguments["quantity"]
            cart_ids = "、".join(f"#{item['cart_id']}" for item in items)
            return f"将购物车项 {cart_ids} 的数量都修改为 {quantity}"
        if action == "create_order":
            product = await self._ecommerce.get_product_detail(arguments["product_id"])
            name = product.get("name") if isinstance(product, dict) else None
            product_text = name or f"商品 #{arguments['product_id']}"
            return (
                f"使用默认演示地址 #{arguments['address_id']} 和 "
                f"{arguments['payment_method']} 支付方式，为 {product_text} x "
                f"{arguments['quantity']} 创建订单"
            )
        if action == "pay_order":
            order = await self._ecommerce.get_order_detail(arguments["order_id"], access_token)
            order_no = order.get("orderNo") if isinstance(order, dict) else None
            return f"支付订单 {order_no or '#' + str(arguments['order_id'])}"
        raise ValueError(f"不支持的操作: {action}")

    @staticmethod
    def _require_auth(access_token: str | None) -> None:
        if not access_token:
            raise EcommerceApiError("请先登录后再使用购物车或订单工具。")

    @staticmethod
    def _string_arg(arguments: dict[str, Any], name: str) -> str:
        value = arguments.get(name)
        if not isinstance(value, str):
            raise ValueError(f"工具参数 {name} 必须是文本。")
        return value.strip()

    @staticmethod
    def _positive_int_arg(arguments: dict[str, Any], name: str) -> int:
        try:
            value = int(arguments.get(name))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"工具参数 {name} 必须是正整数。") from exc
        if value < 1:
            raise ValueError(f"工具参数 {name} 必须是正整数。")
        return value

    @staticmethod
    def _optional_float_arg(arguments: dict[str, Any], name: str) -> float | None:
        value = arguments.get(name)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"工具参数 {name} 必须是数字。") from exc

    @staticmethod
    def _optional_bool_arg(arguments: dict[str, Any], name: str) -> bool | None:
        value = arguments.get(name)
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            if value.lower() in ("true", "1", "yes"):
                return True
            if value.lower() in ("false", "0", "no"):
                return False
        raise ValueError(f"工具参数 {name} 必须是布尔值。")

    @staticmethod
    def _optional_iso_datetime_arg(arguments: dict[str, Any], name: str) -> str | None:
        value = arguments.get(name)
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"工具参数 {name} 必须是 ISO 日期或时间。")
        normalized = value.strip()
        if not normalized:
            return None
        try:
            if len(normalized) == 10:
                datetime.strptime(normalized, "%Y-%m-%d")
            else:
                datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(
                f"工具参数 {name} 必须是 ISO 日期或时间，例如 2026-07-01。"
            ) from exc
        return normalized

    def _cart_update_items_arg(self, arguments: dict[str, Any]) -> list[dict[str, int]]:
        raw_items = arguments.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            raise ValueError("工具参数 items 必须是非空列表。")
        normalized: list[dict[str, int]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                raise ValueError("工具参数 items 中的每一项必须是对象。")
            normalized.append(
                {
                    "cart_id": self._positive_int_arg(item, "cart_id"),
                    "quantity": self._positive_int_arg(item, "quantity"),
                }
            )
        return normalized

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        message = str(exc)
        if not message or message.startswith("'"):
            return "工具参数不完整或格式不正确。"
        return message
