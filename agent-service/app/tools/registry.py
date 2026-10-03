from __future__ import annotations

from app.cart_operations import execute_cart_mutation
from app.business_fields import repeat_purchase_authorized, current_mutation_is_consultation
from app.reliability import mark_write_attempt

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.clients.ecommerce_client import EcommerceApiError
from app.business_feedback import REFUND_UNAVAILABLE, customer_error_reply
from app.tracing import get_trace_id
from app.knowledge_base import KnowledgeBase
from app.product_terms import translate_product_keyword
from app.schemas import Confirmation
from app.metrics import tool_calls_total
from app.security_guard import strip_injection_markers
from app.tools.confirmation import ConfirmationStore, fingerprint_access_token


logger = logging.getLogger(__name__)

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
    # 公网只读模式下禁用的写操作工具
    _WRITE_TOOLS = frozenset({
        "add_to_cart", "update_cart", "remove_from_cart", "clear_cart",
        "update_cart_items", "create_order", "pay_order", "cancel_order",
        "refund_order",
    })
    def is_write_disabled(self, name: str) -> bool:
        return self._public_readonly and name in self._WRITE_TOOLS

    def write_restriction_message(self) -> str:
        return "当前入口已配置为只读，不能修改购物车或订单。"

    async def consume_confirmation(self, token: str, session_id: str, access_token: str):
        self._require_auth(access_token)
        pending = await self._confirmations.consume(token, session_id, fingerprint_access_token(access_token))
        if pending is None:
            raise EcommerceApiError('这次确认已失效、已取消或已处理，请重新发起操作。')
        if self.is_write_disabled(pending.action):
            operations = getattr(self, "operations", None)
            if operations:
                await operations.transition(pending.token, {"accepted"}, "failed", {"status": "failed", "message": self.write_restriction_message()})
            raise EcommerceApiError(self.write_restriction_message())
        return pending

    def __init__(
        self,
        ecommerce_client: Any,
        confirmations: ConfirmationStore,
        knowledge_base: KnowledgeBase | None = None,
        *,
        rule_knowledge_base: KnowledgeBase | None = None,
        product_knowledge_base: KnowledgeBase | None = None,
        public_readonly: bool = False,
    ) -> None:
        """知识库分库注入：
        - 新式调用传 rule_knowledge_base / product_knowledge_base（分库隔离）；
        - 旧式调用传 knowledge_base（单库，两个路由共用，保持兼容）；
        - 都不传时默认分库构建。
        """
        self._ecommerce = ecommerce_client
        self._confirmations = confirmations
        if rule_knowledge_base is None:
            rule_knowledge_base = (
                knowledge_base if knowledge_base is not None else KnowledgeBase(doc_type="rule")
            )
        if product_knowledge_base is None:
            product_knowledge_base = (
                knowledge_base if knowledge_base is not None else KnowledgeBase(doc_type="product")
            )
        self._rule_knowledge_base = rule_knowledge_base
        self._product_knowledge_base = product_knowledge_base
        self._knowledge_base = rule_knowledge_base  # 兼容旧属性引用
        self._recent_orders = RecentOrderTracker()
        self._public_readonly = public_readonly

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        session_id: str,
        access_token: str | None,
    ) -> ToolExecution:
        if name in self._WRITE_TOOLS and current_mutation_is_consultation():
            return ToolExecution(output={"ok": False, "error": "您是在咨询或引用操作，本次未操作。请明确要进行的操作。"}, outcome="error")
        # 公网只读模式：拦截所有写操作工具
        if self.is_write_disabled(name):
            return ToolExecution(
                output={
                    "ok": False,
                    "error": self.write_restriction_message(),
                },
                outcome="error",
            )
        # HTTP 客户端统一负责读重试；工具层不重放业务执行。
        if name == "add_to_cart":
            mark_write_attempt()
        result = await self._execute_once(name, arguments, session_id=session_id, access_token=access_token)
        tool_calls_total.labels(tool_name=name, outcome=result.outcome).inc()
        memory = getattr(self, "memory", None)
        if memory and name in self._WRITE_TOOLS and result.outcome == "success" and not result.output.get("unchanged"):
            await memory.record_operations(session_id, access_token, [name])
        return result

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
                kb_name = str(arguments.get("kb") or "rule")
                knowledge_base = (
                    self._product_knowledge_base
                    if kb_name == "product"
                    else self._rule_knowledge_base
                )
                raw = await knowledge_base.asearch(self._string_arg(arguments, "query"))
                # 注入防护第三层：检索结果可能被构造为指令载体，逐个 chunk 检测并替换
                data = []
                for chunk in raw:
                    content = chunk.get("content") if isinstance(chunk, dict) else None
                    if isinstance(content, str):
                        filtered = strip_injection_markers(content)
                        chunk = {**chunk, "content": filtered}
                    data.append(chunk)
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
                self._verify_entity_id(data, arguments["product_id"], "商品")
            elif name == "get_cart":
                self._require_auth(access_token)
                data = await self._ecommerce.get_cart(access_token)
            elif name == "add_to_cart":
                self._require_auth(access_token)
                product_id = self._positive_int_arg(arguments, "product_id")
                quantity = self._positive_int_arg(arguments, "quantity")
                product = await self._check_stock(product_id, quantity)
                self._check_quantity_limit(quantity)
                try:
                    data = await self._ecommerce.add_to_cart(product_id, quantity, access_token)
                except EcommerceApiError as exc:
                    if not exc.result_unknown:
                        raise
                    # 累加型写入无法仅凭最终数量证明本次执行；只报告读回事实。
                    try:
                        cart = await self._ecommerce.get_cart(access_token)
                        current = sum(self._positive_int_arg(item, "quantity") for item in cart
                                      if str(item.get("productId")) == str(product_id))
                        detail = f"当前购物车中「{self._product_name(product) or '该商品'}」有 {current} 件。"
                    except Exception:
                        detail = "暂时也无法读取购物车。"
                    raise EcommerceApiError(f"本次加购结果暂时无法确认。{detail}请先查看购物车，勿重复提交。", result_unknown=True) from exc
                product_name = self._product_name(product)
                # 写入成功后单独核对；核对失败不能把写入判为失败并再次加购。
                cart_snapshot = None
                cart_quantity = None
                cart_subtotal = None
                try:
                    reader = getattr(self._ecommerce, "get_cart", None)
                    cart = await reader(access_token) if reader else None
                    if isinstance(cart, list):
                        # 只有字段完整的快照进入会话，异常字段不会使已成功的写入重新执行。
                        valid_snapshot = all(isinstance(item, dict) and self._cart_id(item) is not None and isinstance(item.get("quantity"), int) and not isinstance(item.get("quantity"), bool) and item["quantity"] > 0 and str(item.get("productId", item.get("product_id", ""))).isdigit() for item in cart)
                        cart_snapshot = cart if valid_snapshot else None
                        matched = [item for item in cart if isinstance(item, dict) and str(item.get("productId", item.get("product_id"))) == str(product_id)]
                        if matched:
                            quantities = [self._positive_int_arg(item, "quantity") for item in matched]
                            cart_quantity = sum(quantities)
                            from decimal import Decimal
                            if all(item.get("price") is not None for item in matched):
                                cart_subtotal = str(sum(Decimal(str(item["price"])) * count for item, count in zip(matched, quantities)))
                except Exception as exc:
                    # 请求已成功，后续只读异常不会触发外层工具重试。
                    logger.warning("Cart verification after add unavailable: %s", type(exc).__name__)
                return ToolExecution(
                    output={
                        "ok": True,
                        "data": data,
                        "cart_snapshot": cart_snapshot,
                        "display": {
                            "product_name": product_name or "该商品",
                            "quantity": quantity,
                            "added_quantity": quantity,
                            "cart_quantity": cart_quantity,
                            "cart_subtotal": cart_subtotal,
                        },
                    },
                    outcome="success",
                )
            elif name in {"update_cart", "update_cart_items", "remove_from_cart"}:
                self._require_auth(access_token)
                normalized = self._normalize_pending_arguments(name, arguments)
                if name == "update_cart":
                    self._check_quantity_limit(normalized["quantity"])
                elif name == "update_cart_items":
                    for item in normalized["items"]:
                        self._check_quantity_limit(item["quantity"])
                await self._enrich_pending_arguments(name, normalized, access_token)
                unchanged = name == "update_cart" and normalized.get("previous_quantity") == normalized["quantity"]
                if name == "update_cart_items":
                    unchanged = all(item.get("previous_quantity") == item["quantity"] for item in normalized["items"])
                if unchanged:
                    return ToolExecution(output={"ok": True, "unchanged": True, "data": normalized}, outcome="success")
                data, message = await execute_cart_mutation(self._ecommerce, name, normalized, access_token)
                return ToolExecution(output={"ok": True, "data": data, "cart_snapshot": data, "message": message}, outcome="success")
            elif name in {"clear_cart", "create_order", "pay_order"}:
                self._require_auth(access_token)
                if name == "create_order":
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
                self._verify_entity_id(data, arguments["order_id"], "订单")
            elif name == "refund_order":
                return ToolExecution(output={"ok": False, "error": REFUND_UNAVAILABLE}, outcome="error")
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
                # 只使用结构化错误标记，不根据客户文案猜测重试。
                output={"ok": False, "error": self._friendly_error(exc),
                        "retryable": name not in self._WRITE_TOOLS and isinstance(exc, EcommerceApiError) and exc.retryable,
                        "result_unknown": isinstance(exc, EcommerceApiError) and exc.result_unknown},
                outcome="error",
            )

    async def _check_stock(self, product_id: int, quantity: int) -> dict[str, Any]:
        product = await self._ecommerce.get_product_detail(product_id)
        if not isinstance(product, dict):
            raise EcommerceApiError("商品信息获取失败。")
        self._verify_entity_id(product, product_id, "商品")
        stock = product.get("stock")
        if stock is None:
            raise EcommerceApiError("无法获取商品库存信息。")
        if int(stock) < quantity:
            raise EcommerceApiError(f"库存不足，当前库存为 {stock} 件，无法购买 {quantity} 件。")
        return product

    @staticmethod
    def _verify_entity_id(data: Any, requested_id: int, label: str) -> None:
        if isinstance(data, dict) and data.get("id") is not None and str(data["id"]) != str(requested_id):
            raise EcommerceApiError(f"{label}详情编号与请求编号不一致，操作已停止。")

    @staticmethod
    def _check_quantity_limit(quantity: int) -> None:
        if quantity > 99:
            raise ValueError("单个商品最多购买99件。")

    async def _check_duplicate_order(
        self, session_id: str, product_id: int, quantity: int, access_token: str | None
    ) -> None:
        operations = getattr(self, "operations", None)
        if operations and await operations.has_unresolved_purchase(
            fingerprint_access_token(access_token), product_id, quantity
        ):
            raise EcommerceApiError("您有相同商品的订单结果待核实，请先核实原操作，暂时不要再次下单。")
        order_key = self._order_key(session_id, access_token, product_id, quantity)
        if not repeat_purchase_authorized() and await self._recent_orders.is_recent_order(order_key):
            raise EcommerceApiError("5分钟内已提交过相同的订单，请先查看订单状态，勿重复下单。")

    async def record_created_order(
        self,
        session_id: str,
        access_token: str,
        product_id: int,
        quantity: int,
    ) -> None:
        """订单已创建或提交结果待核实时记录防重；用户拒绝确认不记录。"""
        order_key = self._order_key(session_id, access_token, product_id, quantity)
        await self._recent_orders.record_order(order_key)

    @staticmethod
    def _order_key(
        session_id: str,
        access_token: str | None,
        product_id: int,
        quantity: int,
    ) -> str:
        return (
            f"{session_id}:{fingerprint_access_token(access_token)}:"
            f"{product_id}:{quantity}"
        )

    async def _resolve_order_address(self, access_token: str) -> dict[str, Any]:
        addresses = await self._ecommerce.get_addresses(access_token)
        if not isinstance(addresses, list) or not addresses:
            raise EcommerceApiError("当前账号还没有收货地址，请先添加收货地址后再下单。")
        selected = next(
            (
                address
                for address in addresses
                if isinstance(address, dict)
                and address.get("isDefault") in (1, True)
            ),
            addresses[0],
        )
        if not isinstance(selected, dict):
            raise EcommerceApiError("收货地址数据无法识别，请在地址管理中重新保存。")
        address_id = self._positive_int_arg(selected, "id")
        summary = " ".join(str(selected.get(key) or "").strip() for key in
                           ("name", "province", "city", "district", "address")).strip()
        return {"address_id": address_id, "address_summary": summary or "当前账号的收货地址"}

    async def _prepare_cancellation(
        self,
        session_id: str,
        arguments: dict[str, Any],
        access_token: str,
    ) -> ToolExecution:
        order_id = self._positive_int_arg(arguments, "order_id")

        order = await self._ecommerce.get_order_detail(order_id, access_token)
        self._verify_entity_id(order, order_id, "订单")
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
            expires_at=pending.expires_at,
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

    async def _prepare_refund(
        self,
        session_id: str,
        arguments: dict[str, Any],
        access_token: str,
    ) -> ToolExecution:
        order_id = self._positive_int_arg(arguments, "order_id")
        reason = self._string_arg(arguments, "reason") or None

        order = await self._ecommerce.get_order_detail(order_id, access_token)
        self._verify_entity_id(order, order_id, "订单")
        if not isinstance(order, dict):
            raise EcommerceApiError("订单接口返回了无法识别的数据。")
        # 状态 0=待支付 1=已支付 2=已发货 3=已完成 4=已取消
        status = order.get("status")
        if status in (0, 4):
            raise EcommerceApiError("待支付或已取消的订单不能申请退款。")

        order_no = order.get("orderNo") or f"#{order_id}"
        final_amount = order.get("finalAmount")
        refund_args = {"order_id": order_id}
        if reason:
            refund_args["reason"] = reason
        pending = await self._confirmations.issue(
            session_id=session_id,
            action="refund_order",
            arguments=refund_args,
            authorization_fingerprint=fingerprint_access_token(access_token),
        )
        amount_text = f"，金额 ¥{final_amount}" if final_amount is not None else ""
        confirmation = Confirmation(
            token=pending.token,
            expires_at=pending.expires_at,
            action=pending.action,
            description=f"申请订单 {order_no} 退款{amount_text}",
            arguments={
                "order_id": order_id,
                "order_no": order_no,
                "final_amount": final_amount,
                "reason": reason,
            },
        )
        return ToolExecution(
            output={
                "ok": False,
                "confirmation_required": True,
                "message": "订单已校验，等待用户明确确认后提交退款申请。",
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
        if action == "create_order" and "address_id" not in normalized:
            normalized.update(await self._resolve_order_address(access_token))
        await self._enrich_pending_arguments(action, normalized, access_token)
        unchanged = action == "update_cart" and normalized.get("previous_quantity") == normalized["quantity"]
        if action == "update_cart_items":
            unchanged = all(item.get("previous_quantity") == item["quantity"] for item in normalized["items"])
        if unchanged:
            return ToolExecution(output={"ok": True, "unchanged": True, "data": normalized}, outcome="success")
        description = await self._confirmation_description(action, normalized, access_token)
        pending = await self._confirmations.issue(
            session_id=session_id,
            action=action,
            arguments=normalized,
            authorization_fingerprint=fingerprint_access_token(access_token),
        )
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
                expires_at=pending.expires_at,
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
            quantity = self._positive_int_arg(arguments, "quantity")
            items = self._cart_update_items_arg(arguments)
            if any(item["quantity"] != quantity for item in items):
                raise ValueError("批量修改的各项数量与统一目标数量不一致，未执行修改。")
            if len({item["cart_id"] for item in items}) != len(items):
                raise ValueError("批量修改包含重复的购物车项，未执行修改。")
            return {
                "items": items,
                "quantity": quantity,
            }
        if action == "create_order":
            normalized = {
                "product_id": self._positive_int_arg(arguments, "product_id"),
                "quantity": self._positive_int_arg(arguments, "quantity"),
                "payment_method": str(arguments.get("payment_method") or "DEMO"),
            }
            if arguments.get("address_id") is not None:
                normalized["address_id"] = self._positive_int_arg(arguments, "address_id")
            return normalized
        if action == "pay_order":
            return {"order_id": self._positive_int_arg(arguments, "order_id")}
        raise ValueError(f"不支持的操作: {action}")

    async def _enrich_pending_arguments(
        self,
        action: str,
        arguments: dict[str, Any],
        access_token: str,
    ) -> None:
        if action == "create_order":
            product = await self._ecommerce.get_product_detail(arguments["product_id"])
            self._verify_entity_id(product, arguments["product_id"], "商品")
            product_name = self._product_name(product)
            if product_name:
                arguments["product_name"] = product_name
            return

        if action in {"update_cart", "remove_from_cart", "update_cart_items"}:
            cart = await self._ecommerce.get_cart(access_token)
            cart_items = cart if isinstance(cart, list) else []
            by_id = {
                self._cart_id(item): item
                for item in cart_items
                if isinstance(item, dict) and self._cart_id(item) is not None
            }
            if action == "update_cart_items":
                for item in arguments["items"]:
                    current = by_id.get(item["cart_id"])
                    if current is None:
                        raise EcommerceApiError("购物车项已不存在，请刷新购物车后重试。")
                    product_name = self._cart_product_name(current)
                    if current.get("quantity") is not None:
                        item["previous_quantity"] = self._positive_int_arg(current, "quantity")
                    if product_name:
                        item["product_name"] = product_name
            else:
                current = by_id.get(arguments["cart_id"])
                if current is None:
                    raise EcommerceApiError("购物车项已不存在，请刷新购物车后重试。")
                product_name = self._cart_product_name(current)
                if current.get("quantity") is not None:
                    arguments["previous_quantity"] = self._positive_int_arg(current, "quantity")
                if product_name:
                    arguments["product_name"] = product_name
            return

        if action == "pay_order":
            order = await self._ecommerce.get_order_detail(arguments["order_id"], access_token)
            self._verify_entity_id(order, arguments["order_id"], "订单")
            order_no = self._order_no(order)
            if order_no:
                arguments["order_no"] = order_no

    async def _confirmation_description(
        self, action: str, arguments: dict[str, Any], access_token: str
    ) -> str:
        if action == "update_cart":
            product_name = arguments.get("product_name") or "该商品"
            previous = arguments.get("previous_quantity")
            change = f"从 {previous} 件改为" if previous is not None else "改为"
            return f"将「{product_name}」的购物车数量{change} {arguments['quantity']} 件"
        if action == "remove_from_cart":
            product_name = arguments.get("product_name") or "该商品"
            return f"从购物车移除「{product_name}」"
        if action == "clear_cart":
            return "清空当前购物车"
        if action == "update_cart_items":
            items = arguments["items"]
            quantity = arguments["quantity"]
            names = [str(item["product_name"]) for item in items if item.get("product_name")]
            target = "、".join(f"「{name}」" for name in names) if names else f"{len(items)} 件商品"
            return f"将{target}的数量都修改为 {quantity} 件"
        if action == "create_order":
            product_text = arguments.get("product_name") or "该商品"
            return (
                "使用当前账号的收货地址和 "
                f"{arguments['payment_method']} 支付方式，购买「{product_text}」× "
                f"{arguments['quantity']} 件"
            )
        if action == "pay_order":
            return f"支付订单 {arguments.get('order_no') or '当前订单'}"
        raise ValueError(f"不支持的操作: {action}")

    @staticmethod
    def _product_name(product: Any) -> str | None:
        if not isinstance(product, dict):
            return None
        name = product.get("name") or product.get("productName") or product.get("product_name")
        return str(name).strip() if name else None

    @staticmethod
    def _cart_id(item: dict[str, Any]) -> int | None:
        value = item.get("cartId") or item.get("cart_id") or item.get("id")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _cart_product_name(cls, item: Any) -> str | None:
        return cls._product_name(item)

    @staticmethod
    def _order_no(order: Any) -> str | None:
        if not isinstance(order, dict):
            return None
        value = order.get("orderNo") or order.get("order_no")
        return str(value).strip() if value else None

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
        raw = arguments.get(name)
        if isinstance(raw, bool) or (isinstance(raw, float) and raw != value) or value < 1:
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
        if isinstance(exc, EcommerceApiError) and exc.retryable:
            trace_id = get_trace_id()
            suffix = f"（追踪号：{trace_id}）" if trace_id and trace_id != "-" else ""
            return f"暂时无法处理您的请求，请稍后重试。{suffix}"
        message = str(exc)
        if not message or message.startswith("'"):
            return "这次操作的信息还不完整，请从对应的商品或订单卡片重新操作。"
        if "库存" in message or "stock" in message.lower() or "工具参数" in message or "详情编号与请求编号不一致" in message:
            return customer_error_reply(message)
        return message
