from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.conversation_state import ConversationState, ConversationStateStore
from app.product_terms import extract_product_keyword
from app.schemas import ChatResponse, ReferenceResolution, ToolCallRecord
from app.security_guard import is_suspicious_instruction
from app.tools.registry import ToolRegistry


def _extract_number_from_text(text: str) -> int | None:
    match = re.search(r"\b(\d+)\b", text)
    return int(match.group(1)) if match else None


def _extract_product_id_from_text(text: str) -> int | None:
    patterns = [
        r"(?:商品|product)\s*#?\s*(\d+)",
        r"(\d+)\s*号\s*(?:商品|产品)",
        r"#\s*(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _extract_cart_id_from_text(text: str) -> int | None:
    match = re.search(r"(?:cart\s*id|cartid|购物车项|购物车)\s*#?\s*(\d+)", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _resolve_or_clarify_order_id(
    message: str,
    lowered: str,
    state: ConversationState,
) -> tuple[int | None, ChatResponse | None]:
    explicit_id = _extract_number_from_text(lowered)
    order_id = state.resolve_order_id(message, explicit_id)
    if order_id is None:
        return None, ChatResponse(answer="请告诉我需要操作的订单 ID。")
    return order_id, None


def _resolve_or_clarify_product_id(
    message: str,
    lowered: str,
    state: ConversationState,
) -> tuple[int | None, ChatResponse | None]:
    explicit_id = _extract_product_id_from_text(lowered)
    product_id = state.resolve_product_id(message, explicit_id)
    if product_id is None:
        return None, ChatResponse(answer="请告诉我要操作的商品 ID，或先搜索/推荐商品。")
    return product_id, None


def _resolve_or_clarify_cart_id(
    lowered: str,
) -> tuple[int | None, ChatResponse | None]:
    cart_id = _extract_cart_id_from_text(lowered)
    if cart_id is None:
        return None, ChatResponse(answer="请告诉我购物车项 cartId。")
    return cart_id, None


class DemoAgentService:
    """Deterministic local agent used when no model API key is configured."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        state_store: ConversationStateStore | None = None,
    ) -> None:
        self._registry = registry
        self._state_store = state_store

    async def chat(
        self,
        message: str,
        *,
        session_id: str,
        access_token: str | None,
    ) -> ChatResponse:
        if is_suspicious_instruction(message):
            return ChatResponse(
                answer="该请求包含可能绕过安全规则或获取敏感信息的指令，已被拒绝。"
            )

        state = (
            await self._state_store.get(session_id, access_token)
            if self._state_store is not None
            else ConversationState()
        )

        normalized = message.strip()
        lowered = normalized.lower()

        response = await self._route(message, lowered, state, session_id, access_token)

        if self._state_store is not None:
            await self._state_store.save(session_id, access_token, state)

        return response

    async def _route(
        self,
        message: str,
        lowered: str,
        state: ConversationState,
        session_id: str,
        access_token: str | None,
    ) -> ChatResponse:
        if self._contains_any(lowered, "你能做什么", "你会什么", "有哪些功能", "帮助", "help"):
            state.turn_count += 1
            return ChatResponse(answer=self._format_capabilities())

        if self._contains_any(
            lowered,
            "退款",
            "售后",
            "规则",
            "政策",
            "参数",
            "配置",
            "refund",
            "return",
            "policy",
            "warranty",
            "shipping",
            "invoice",
            "membership",
        ):
            topic = message[:30]
            result = await self._run_tool(
                "search_knowledge_base",
                {"query": message},
                session_id=session_id,
                access_token=access_token,
                success_prefix="我从项目知识库中检索到以下说明：",
            )
            state.record_knowledge_topic(topic)
            return result

        if self._contains_any(lowered, "支付", "付款", "pay"):
            order_id, clarification = _resolve_or_clarify_order_id(message, lowered, state)
            if clarification:
                return clarification
            ref = ReferenceResolution(type="order", value=str(order_id)) if _extract_number_from_text(lowered) is None else None
            return await self._run_tool(
                "pay_order",
                {"order_id": order_id},
                session_id=session_id,
                access_token=access_token,
                success_prefix="已准备支付订单，执行前需要你的明确确认。",
                reference=ref,
            )

        if self._contains_any(lowered, "下单", "购买", "买", "创建订单", "place order"):
            quantity = self._extract_quantity(lowered)
            product_id, clarification = _resolve_or_clarify_product_id(message, lowered, state)
            if clarification:
                keyword = self._extract_product_keyword(lowered)
                if keyword:
                    search = await self._search_products(
                        keyword, lowered, state, session_id, access_token
                    )
                    products = self._normalize_products(search.data)
                    if products:
                        product_id = int(products[0]["id"])
                        state.record_product(
                            product_id, str(products[0].get("name") or "")
                        )
                if product_id is None:
                    return clarification
            ref = ReferenceResolution(type="product", value=str(product_id)) if _extract_product_id_from_text(lowered) is None else None
            return await self._run_tool(
                "create_order",
                {"product_id": product_id, "quantity": quantity},
                session_id=session_id,
                access_token=access_token,
                success_prefix="已准备使用默认演示地址和 DEMO 支付方式创建订单，执行前需要你的确认。",
                reference=ref,
            )

        if self._contains_any(lowered, "取消", "cancel"):
            order_id, clarification = _resolve_or_clarify_order_id(message, lowered, state)
            if clarification:
                return clarification
            ref = (
                ReferenceResolution(type="order", value=str(order_id))
                if _extract_number_from_text(lowered) is None
                else None
            )
            result = await self._run_tool(
                "cancel_order",
                {"order_id": order_id},
                session_id=session_id,
                access_token=access_token,
                success_prefix="已准备取消订单，但执行前仍需要你的明确确认。",
                reference=ref,
            )
            if result.tool_calls and result.tool_calls[0].outcome in {
                "success",
                "confirmation_required",
            }:
                state.record_order(order_id)
            return result

        if self._contains_any(lowered, "清空购物车", "清空 cart", "clear cart"):
            state.record_cart_view()
            return await self._run_tool(
                "clear_cart",
                {},
                session_id=session_id,
                access_token=access_token,
                success_prefix="已准备清空购物车，执行前需要你的明确确认。",
            )

        if self._contains_any(lowered, "删除购物车", "移除购物车", "删掉购物车", "remove cart"):
            cart_id, clarification = _resolve_or_clarify_cart_id(lowered)
            if clarification:
                return clarification
            state.record_cart_view()
            return await self._run_tool(
                "remove_from_cart",
                {"cart_id": cart_id},
                session_id=session_id,
                access_token=access_token,
                success_prefix="已准备删除购物车商品，执行前需要你的明确确认。",
            )

        if self._contains_any(lowered, "修改购物车", "购物车数量", "改数量", "update cart"):
            cart_id, clarification = _resolve_or_clarify_cart_id(lowered)
            if clarification:
                return clarification
            quantity = self._extract_quantity(lowered)
            state.record_cart_view()
            return await self._run_tool(
                "update_cart",
                {"cart_id": cart_id, "quantity": quantity},
                session_id=session_id,
                access_token=access_token,
                success_prefix="已准备修改购物车数量，执行前需要你的明确确认。",
            )

        if self._contains_any(lowered, "加入购物车", "加购物车", "放购物车", "添加购物车", "add to cart"):
            product_id, clarification = _resolve_or_clarify_product_id(message, lowered, state)
            quantity = self._extract_quantity(lowered)
            if clarification:
                keyword = self._extract_product_keyword(lowered)
                if keyword:
                    search = await self._search_products(
                        keyword, lowered, state, session_id, access_token
                    )
                    products = self._normalize_products(search.data)
                    if products:
                        product_id = int(products[0]["id"])
                        state.record_product(
                            product_id, str(products[0].get("name") or "")
                        )
                if product_id is None:
                    return clarification
            result = await self._run_tool(
                "add_to_cart",
                {"product_id": product_id, "quantity": quantity},
                session_id=session_id,
                access_token=access_token,
                success_prefix=f"已将商品 #{product_id} x {quantity} 加入购物车。",
            )
            if result.tool_calls and result.tool_calls[0].outcome == "success":
                state.record_product(product_id)
                state.record_cart_view()
            return result

        if self._contains_any(lowered, "购物车", "cart"):
            state.record_cart_view()
            return await self._run_tool(
                "get_cart",
                {},
                session_id=session_id,
                access_token=access_token,
                success_prefix="这是你当前的购物车：",
            )

        if self._contains_any(lowered, "订单", "order", "查一下订单", "看看订单"):
            explicit_id = self._extract_number(lowered)
            order_id = state.resolve_order_id(message, explicit_id)
            if order_id is not None:
                tool_name = "get_order_detail"
                arguments = {"order_id": order_id}
                success_prefix = "订单详情如下："
                ref = (
                    ReferenceResolution(type="order", value=str(order_id))
                    if explicit_id is None
                    else None
                )
            else:
                tool_name = "get_my_orders"
                arguments = {}
                success_prefix = "你的订单列表如下："
                ref = None

            result = await self._registry.execute(
                tool_name,
                arguments,
                session_id=session_id,
                access_token=access_token,
            )

            if result.outcome == "success" and tool_name == "get_my_orders":
                orders = self._normalize_list(result.output.get("data"))
                if orders:
                    first_order = orders[0]
                    first_id = first_order.get("id")
                    first_no = first_order.get("orderNo")
                    if first_id is not None:
                        state.record_order(first_id, first_no)

            if result.outcome in {"success", "confirmation_required"} and order_id is not None:
                state.record_order(order_id)

            if result.outcome == "confirmation_required":
                answer = success_prefix
            elif result.outcome == "success":
                answer = f"{success_prefix}\n{self._format_data(result.output.get('data'))}"
            else:
                answer = result.output.get("error", "工具执行失败。")

            return ChatResponse(
                answer=answer,
                tool_calls=[
                    ToolCallRecord(name=tool_name, arguments=arguments, outcome=result.outcome)
                ],
                confirmation=result.confirmation,
                data=result.output.get("data"),
                reference=ref,
            )

        if self._contains_any(
            lowered, "推荐", "商品", "手机", "电脑", "耳机", "搜索", "找", "库存", "价格", "多少钱", "find", "product"
        ):
            list_all_products = self._contains_any(
                lowered, "有哪些商品", "商品列表", "所有商品", "有什么商品"
            )
            explicit_keyword = self._extract_product_keyword(lowered)
            explicit_product_id = self._extract_product_id(lowered)
            if explicit_product_id is not None or (
                not explicit_keyword and state.resolve_product_id(message, None) is not None
            ):
                product_id = state.resolve_product_id(message, explicit_product_id)
                result = await self._run_tool(
                    "get_product_detail",
                    {"product_id": product_id},
                    session_id=session_id,
                    access_token=access_token,
                    success_prefix="商品详情如下：",
                    reference=ReferenceResolution(type="product", value=str(product_id)) if explicit_product_id is None else None,
                )
                if result.tool_calls and result.tool_calls[0].outcome == "success":
                    data = result.data
                    if isinstance(data, dict):
                        state.record_product(product_id, str(data.get("name") or ""))
                    result.answer = self._format_product_detail(data)
                return result

            list_phone_products = self._contains_any(lowered, "手机")
            force_full_product_scan = list_all_products or list_phone_products
            keyword = "" if force_full_product_scan else state.resolve_product_keyword(message, explicit_keyword)
            ref = None
            if not keyword and not force_full_product_scan:
                keyword = explicit_keyword or ""
            elif not explicit_keyword:
                ref = ReferenceResolution(type="product", value=keyword)
            if not keyword:
                if force_full_product_scan:
                    keyword = ""
                else:
                    return ChatResponse(answer="请告诉我你想搜索什么商品。")

            min_price, max_price, in_stock = self._extract_price_filters(message)
            return await self._search_products(
                keyword, lowered, state, session_id, access_token,
                reference=ref,
                min_price=min_price,
                max_price=max_price,
                in_stock=in_stock,
            )

        if self._is_followup_query(message, state):
            return await self._handle_followup(message, state, session_id, access_token)

        state.turn_count += 1
        return ChatResponse(
            answer=(
                "当前是本地演示模式。我可以搜索商品、查看购物车、查询订单，"
                "也可以演示带二次确认的订单取消流程。"
            )
        )

    async def _handle_followup(
        self,
        message: str,
        state: ConversationState,
        session_id: str,
        access_token: str | None,
    ) -> ChatResponse:
        lowered = message.lower()

        if state.last_topic == "order" and state.last_order_id is not None:
            order_ref = ReferenceResolution(type="order", value=str(state.last_order_id))
            if self._contains_any(lowered, "详情", "详细", "detail", "看看"):
                return await self._run_tool(
                    "get_order_detail",
                    {"order_id": state.last_order_id},
                    session_id=session_id,
                    access_token=access_token,
                    success_prefix="订单详情如下：",
                    reference=order_ref,
                )
            if self._contains_any(lowered, "取消", "cancel"):
                result = await self._run_tool(
                    "cancel_order",
                    {"order_id": state.last_order_id},
                    session_id=session_id,
                    access_token=access_token,
                    success_prefix="已准备取消订单，但执行前仍需要你的明确确认。",
                    reference=order_ref,
                )
                state.record_order(state.last_order_id)
                return result

        if state.last_topic == "product" and state.last_product_keyword:
            product_ref = ReferenceResolution(type="product", value=state.last_product_keyword)
            if self._contains_any(lowered, "再看看", "再来", "更多", "other"):
                return await self._search_products(
                    state.last_product_keyword,
                    lowered,
                    state,
                    session_id,
                    access_token,
                    reference=product_ref,
                    exclude_shown=True,
                )

        return ChatResponse(
            answer=(
                "当前是本地演示模式。我可以搜索商品、查看购物车、查询订单，"
                "也可以演示带二次确认的订单取消流程。"
            )
        )

    @staticmethod
    def _is_followup_query(message: str, state: ConversationState) -> bool:
        if state.turn_count == 0:
            return False
        short = len(message) <= 15
        has_referral = bool(
            re.search(r"它|这个|那个|这个|该|此|刚才|刚刚|再|还", message)
        )
        return short and has_referral and state.last_topic is not None

    async def _run_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        session_id: str,
        access_token: str | None,
        success_prefix: str,
        reference: ReferenceResolution | None = None,
    ) -> ChatResponse:
        result = await self._registry.execute(
            name,
            arguments,
            session_id=session_id,
            access_token=access_token,
        )
        if result.outcome == "confirmation_required":
            answer = success_prefix
        elif result.outcome == "success":
            data = result.output.get("data")
            answer = success_prefix if data is None else f"{success_prefix}\n{self._format_data(data)}"
        else:
            answer = result.output.get("error", "工具执行失败。")
        return ChatResponse(
            answer=answer,
            tool_calls=[
                ToolCallRecord(name=name, arguments=arguments, outcome=result.outcome)
            ],
            confirmation=result.confirmation,
            data=result.output.get("data"),
            reference=reference,
        )

    async def _search_products(
        self,
        keyword: str,
        lowered: str,
        state: ConversationState,
        session_id: str,
        access_token: str | None,
        *,
        reference: ReferenceResolution | None = None,
        exclude_shown: bool = False,
        min_price: float | None = None,
        max_price: float | None = None,
        in_stock: bool | None = None,
    ) -> ChatResponse:
        args: dict[str, Any] = {"keyword": keyword}
        if min_price is not None:
            args["min_price"] = min_price
        if max_price is not None:
            args["max_price"] = max_price
        if in_stock is not None:
            args["in_stock"] = in_stock

        result = await self._registry.execute(
            "search_products",
            args,
            session_id=session_id,
            access_token=access_token,
        )
        if result.outcome != "success":
            return self._response_for_result(
                "search_products", args, result
            )

        products = self._normalize_products(result.output.get("data"))
        products = self._filter_products_for_intent(products, lowered)
        products = self._filter_by_price_safety_net(products, min_price, max_price)
        products = self._sort_products(products, lowered)
        if exclude_shown and state.shown_product_ids:
            shown = set(state.shown_product_ids)
            products = [product for product in products if product.get("id") not in shown]
        shown_ids = [
            int(product["id"])
            for product in products[:10]
            if product.get("id") is not None
        ]
        if products:
            first = products[0]
            state.record_product_search(
                keyword,
                int(first["id"]) if first.get("id") is not None else None,
                str(first.get("name") or ""),
                shown_ids,
            )
        else:
            state.record_product_search(keyword, shown_product_ids=state.shown_product_ids)
        answer = (
            "没有更多符合条件的商品了。"
            if exclude_shown and not products
            else self._format_products(products, keyword)
        )
        return ChatResponse(
            answer=answer,
            tool_calls=[
                ToolCallRecord(
                    name="search_products",
                    arguments=args,
                    outcome=result.outcome,
                )
            ],
            data=products,
            reference=reference,
        )

    @staticmethod
    def _response_for_result(name: str, arguments: dict[str, Any], result: Any):
        return ChatResponse(
            answer=result.output.get("error", "工具执行失败。"),
            tool_calls=[
                ToolCallRecord(name=name, arguments=arguments, outcome=result.outcome)
            ],
            confirmation=result.confirmation,
            data=result.output.get("data"),
        )

    @staticmethod
    def _format_products(
        products: list[dict[str, Any]], keyword: str
    ) -> str:
        if not products:
            return f"暂时没有找到包含'{keyword}'的在售商品。"
        lines = ["我找到这些商品："]
        for product in products[:10]:
            lines.append(
                f"• #{product.get('id')} {product.get('name')} — "
                f"¥{product.get('price')}，库存 {product.get('stock', '未知')}"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_product_detail(data: Any) -> str:
        if not isinstance(data, dict):
            return "没有查到这个商品的详情。"
        return (
            "商品详情如下：\n"
            f"• #{data.get('id')} {data.get('name')}\n"
            f"• 价格：¥{data.get('price')}\n"
            f"• 库存：{data.get('stock', '未知')}\n"
            f"• 描述：{data.get('description') or '暂无描述'}"
        )

    @staticmethod
    def _format_capabilities() -> str:
        return (
            "我可以帮你做这些电商客服操作：\n"
            "• 匿名搜索/推荐商品，按预算、价格和常见偏好筛选。\n"
            "• 查询商品价格、库存和详情，并理解“它/这款/刚才那个”。\n"
            "• 登录后查看购物车、加入购物车、修改数量、删除或清空购物车。\n"
            "• 登录后查询订单、查看订单详情、取消待支付订单、创建订单和支付订单。\n"
            "• 售后、退款、规则和参数问题会检索项目知识库。\n"
            "取消、删除、清空、下单和支付都会先让你二次确认。"
        )

    @staticmethod
    def _sort_products(
        products: list[dict[str, Any]], lowered: str
    ) -> list[dict[str, Any]]:
        reverse = DemoAgentService._contains_any(
            lowered, "高端", "贵", "旗舰", "性能", "从高到低", "高价"
        )
        if DemoAgentService._contains_any(
            lowered, "便宜", "性价比", "预算", "以内", "以下", "低价", "从低到高"
        ) or reverse:
            return sorted(
                products,
                key=lambda product: Decimal(str(product.get("price") or "0")),
                reverse=reverse,
            )
        if DemoAgentService._contains_any(lowered, "现在有什么商品", "有哪些商品", "商品列表", "所有商品", "有什么商品"):
            return sorted(
                products,
                key=lambda product: (
                    0 if int(product.get("id") or 0) >= 100 else 1,
                    int(product.get("id") or 0),
                ),
            )
        return products

    @staticmethod
    def _filter_products_for_intent(
        products: list[dict[str, Any]], lowered: str
    ) -> list[dict[str, Any]]:
        # Category filtering
        if DemoAgentService._contains_any(lowered, "国产") and DemoAgentService._contains_any(lowered, "手机", "phone"):
            products = [
                product
                for product in products
                if DemoAgentService._is_domestic_phone(product)
            ]
        elif DemoAgentService._contains_any(lowered, "手机", "phone"):
            products = [
                product
                for product in products
                if DemoAgentService._is_phone_product(product)
            ]

        return products

    @staticmethod
    def _filter_by_price_safety_net(
        products: list[dict[str, Any]],
        min_price: float | None,
        max_price: float | None,
    ) -> list[dict[str, Any]]:
        """Client-side price safety-net in case backend filtering missed items."""
        if min_price is None and max_price is None:
            return products
        filtered = []
        for product in products:
            try:
                price = float(product.get("price", 0))
            except (ValueError, TypeError):
                continue
            if min_price is not None and price < min_price:
                continue
            if max_price is not None and price > max_price:
                continue
            filtered.append(product)
        return filtered

    @staticmethod
    def _is_domestic_phone(product: dict[str, Any]) -> bool:
        if not DemoAgentService._is_phone_product(product):
            return False
        name = str(product.get("name") or "").lower()
        description = str(product.get("description") or "").lower()
        text = f"{name} {description}"
        return any(
            brand.lower() in text
            for brand in ("华为", "小米", "oppo", "vivo", "荣耀", "一加", "红米", "realme")
        )

    @staticmethod
    def _is_phone_product(product: dict[str, Any]) -> bool:
        if product.get("categoryId") == 101:
            return True
        name = str(product.get("name") or "").lower()
        description = str(product.get("description") or "").lower()
        text = f"{name} {description}"
        # Exclude headphones/earbuds
        if any(kw in text for kw in ("headphone", "earphone", "耳机", "buds", "freebuds", "耳机", "头戴式")):
            return False
        # Phone markers - both Chinese and English
        phone_markers = (
            "smartphone", "iphone", "mate", "find x", "x100",
            "14 ultra", "手机", "电话", "旗舰",
            "redmi", "poco", "honor", "荣耀", "oneplus", "一加",
            "realme", "iqoo", "vivo", "oppo", "huawei", "小米", "华为",
            "pro max", "ultra", "折叠屏",
        )
        return any(marker.lower() in text for marker in phone_markers)

    @staticmethod
    def _normalize_products(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, dict):
            content = data.get("content")
            if isinstance(content, list):
                return [item for item in content if isinstance(item, dict)]
            if {"id", "name", "price"} & set(data.keys()):
                return [data]
            return []
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    @staticmethod
    def _normalize_list(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, dict) and isinstance(data.get("content"), list):
            data = data["content"]
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    @staticmethod
    def _format_data(data: Any) -> str:
        if data is None or data == []:
            return "暂无数据。"
        if isinstance(data, list):
            lines = []
            for item in data[:8]:
                if not isinstance(item, dict):
                    lines.append(f"• {item}")
                    continue
                identifier = item.get("orderNo") or item.get("id") or item.get("cartId")
                status = item.get("status")
                name = item.get("productName") or DemoAgentService._order_status(status)
                amount = item.get("finalAmount") or item.get("price")
                parts = [
                    str(value)
                    for value in (identifier, name, amount)
                    if value is not None
                ]
                lines.append("• " + " · ".join(parts))
            return "\n".join(lines)
        if isinstance(data, dict):
            useful = [
                (
                    f"{key}: "
                    f"{DemoAgentService._order_status(value) if key == 'status' else value}"
                )
                for key, value in data.items()
                if key in {"id", "orderNo", "status", "paymentStatus", "finalAmount"}
            ]
            return "\n".join(useful) if useful else str(data)
        return str(data)

    @staticmethod
    def _order_status(status: Any) -> str | None:
        if status is None:
            return None
        return {
            0: "待支付",
            1: "已支付",
            2: "已发货",
            3: "已完成",
            4: "已取消",
        }.get(status, f"未知状态({status})")

    @staticmethod
    def _contains_any(text: str, *keywords: str) -> bool:
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _extract_number(text: str) -> int | None:
        match = re.search(r"\b(\d+)\b", text)
        return int(match.group(1)) if match else None

    @staticmethod
    def _extract_product_id(text: str) -> int | None:
        patterns = [
            r"(?:商品|product)\s*#?\s*(\d+)",
            r"(\d+)\s*号\s*(?:商品|产品)",
            r"#\s*(\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None

    @staticmethod
    def _extract_cart_id(text: str) -> int | None:
        match = re.search(r"(?:cart\s*id|cartid|购物车项|购物车)\s*#?\s*(\d+)", text, re.IGNORECASE)
        return int(match.group(1)) if match else None

    @staticmethod
    def _extract_quantity(text: str) -> int:
        match = re.search(r"(\d+)\s*(?:个|件|台|双|本|份|x)", text, re.IGNORECASE)
        if match:
            return max(int(match.group(1)), 1)
        match = re.search(r"(?:数量|quantity|qty)\s*[:：]?\s*(\d+)", text, re.IGNORECASE)
        return max(int(match.group(1)), 1) if match else 1

    @staticmethod
    def _extract_budget(text: str) -> Decimal | None:
        match = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:元|块|rmb|¥)?\s*(?:内|以内|以下|之内|以内的|以下的|under|below|less than)",
            text,
        )
        if not match:
            return None
        try:
            return Decimal(match.group(1))
        except InvalidOperation:
            return None

    @staticmethod
    def _chinese_to_number(text: str) -> float | None:
        """Convert Chinese numerals to float. e.g. 四千→4000, 三千五百→3500"""
        chinese_digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
                         "六": 6, "七": 7, "八": 8, "九": 9}
        chinese_units = {"十": 10, "百": 100, "千": 1000, "万": 10000}

        if not text:
            return None

        # Try simple case: just a digit
        if text in chinese_digits:
            return float(chinese_digits[text])

        # Handle "十" as 10 or "十X" as 10+X
        if text.startswith("十") and len(text) == 1:
            return 10.0

        result = 0.0
        current = 0.0
        has_unit = False

        for char in text:
            if char in chinese_digits:
                current = chinese_digits[char]
            elif char in chinese_units:
                unit_value = chinese_units[char]
                if current == 0:
                    current = 1
                result += current * unit_value
                current = 0
                has_unit = True
            else:
                return None

        if not has_unit and current > 0:
            result = current

        return result if result > 0 else None

    @staticmethod
    def _extract_price_filters(text: str) -> tuple[float | None, float | None, bool | None]:
        """Extract min_price, max_price, and in_stock from user text."""
        min_price = None
        max_price = None
        in_stock = None

        # Helper: extract number from a match, trying Arabic first then Chinese
        def _parse_number(match_str: str) -> float | None:
            # Try Arabic numerals
            num_match = re.search(r"(\d+(?:\.\d+)?)", match_str)
            if num_match:
                try:
                    return float(num_match.group(1))
                except (InvalidOperation, ValueError):
                    pass
            # Try Chinese numerals
            chinese_match = re.search(r"[零一二两三四五六七八九十百千万]+", match_str)
            if chinese_match:
                result = DemoAgentService._chinese_to_number(chinese_match.group(0))
                if result is not None:
                    return result
            return None

        max_match = re.search(
            r"(\d+(?:\.\d+)?|[零一二两三四五六七八九十百千万]+)\s*(?:元|块|rmb|¥)?\s*(?:内|以内|以下|之内|以内的|以下的|预算|budget)",
            text,
        )
        if max_match:
            try:
                max_price = _parse_number(max_match.group(1))
            except (InvalidOperation, ValueError):
                pass

        min_match = re.search(
            r"(?:以上|超过|大于|高于|不低于|from|over|above|more than)\s*(\d+(?:\.\d+)?|[零一二两三四五六七八九十百千万]+)",
            text,
        )
        if not min_match:
            min_match = re.search(
                r"(\d+(?:\.\d+)?|[零一二两三四五六七八九十百千万]+)\s*(?:元|块|rmb|¥)?\s*(?:以上|超过|大于|高于|不低于|及以上|or more|\+)",
                text,
            )
        if min_match:
            try:
                min_price = _parse_number(min_match.group(1))
            except (InvalidOperation, ValueError):
                pass

        has_stock_query = re.search(
            r"(?:有货|现货|库存|有卖|available|in stock|instock)",
            text.lower(),
        )
        no_stock_query = re.search(
            r"(?:无货|缺货|没货|库存为0|out of stock|unavailable)",
            text.lower(),
        )
        if has_stock_query:
            in_stock = True
        elif no_stock_query:
            in_stock = False

        return min_price, max_price, in_stock

    @staticmethod
    def _extract_product_keyword(text: str) -> str:
        return extract_product_keyword(text)
