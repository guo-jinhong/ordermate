from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.approval_workflow import ApprovalWorkflow
from app.business_fields import extract_quantity, denies_mutation, requests_refund, requests_cart_quantity_change, requests_all_cart_quantity_change, cart_quantity_arguments, vague_cart_quantity_request, cart_clarification_reply, complete_cart_clarification, requests_cart_removal
from app.business_feedback import cart_add_reply, REFUND_UNAVAILABLE, confirmation_reply, customer_error_reply, product_purchase_copy
from app.conversation_state import ConversationState, ConversationStateStore, extract_entity_id
from app.knowledge_base import knowledge_search_intent, route_knowledge_base
from app.product_terms import extract_product_keyword
from app.schemas import ChatResponse, ReferenceResolution, ToolCallRecord
from app.security_guard import is_suspicious_instruction
from app.tools.registry import ToolRegistry


def _extract_number_from_text(text: str) -> int | None:
    match = re.search(r"\b(\d+)\b", text)
    return int(match.group(1)) if match else None


def _extract_product_id_from_text(text: str) -> int | None:
    return extract_entity_id(text, "product")


def _extract_cart_id_from_text(text: str) -> int | None:
    match = re.search(r"(?:cart\s*id|cartid|购物车项|购物车)\s*#?\s*(\d+)", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _resolve_or_clarify_order_id(
    message: str,
    lowered: str,
    state: ConversationState,
) -> tuple[int | None, ChatResponse | None]:
    order_id = state.resolve_order_id(message, None)
    if order_id is None:
        return None, ChatResponse(answer="请告诉我需要操作的订单号，或先查看订单列表。")
    return order_id, None


def _resolve_or_clarify_product_id(
    message: str,
    lowered: str,
    state: ConversationState,
) -> tuple[int | None, ChatResponse | None]:
    explicit_id = _extract_product_id_from_text(lowered)
    product_id = state.resolve_product_id(message, explicit_id)
    if product_id is None:
        return None, ChatResponse(answer="请告诉我商品名称，或先搜索/推荐商品。")
    return product_id, None


def _resolve_or_clarify_cart_id(
    message: str,
    lowered: str,
    state: ConversationState,
) -> tuple[int | None, ChatResponse | None]:
    cart_id = state.resolve_cart_id(message, _extract_cart_id_from_text(lowered))
    if cart_id is None:
        return None, ChatResponse(answer="请先查看购物车，再告诉我要操作的商品名称。")
    return cart_id, None


class DemoAgentService:
    """Deterministic local agent used when no model API key is configured."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        state_store: ConversationStateStore | None = None,
        approval_workflow: ApprovalWorkflow | None = None,
    ) -> None:
        self._registry = registry
        self._state_store = state_store
        self._approval_workflow = approval_workflow

    async def chat(
        self,
        message: str,
        *,
        session_id: str,
        access_token: str | None,
    ) -> ChatResponse:
        if denies_mutation(message):
            return ChatResponse(answer="本轮包含否定操作的要求，未执行修改。请明确要执行的操作。")
        if requests_refund(message) and not denies_mutation(message):
            return ChatResponse(answer=REFUND_UNAVAILABLE)
        if is_suspicious_instruction(message):
            return ChatResponse(
                answer="该请求包含可能绕过安全规则或获取敏感信息的指令，已被拒绝。"
            )

        state = (
            await self._state_store.get(session_id, access_token)
            if self._state_store is not None
            else ConversationState()
        )

        message = complete_cart_clarification(message, state)
        normalized = message.strip()
        lowered = normalized.lower()

        response = await self._route(message, lowered, state, session_id, access_token)
        if (response.tool_calls and response.tool_calls[-1].outcome == "success"
                and response.tool_calls[-1].name in {"update_cart", "update_cart_items", "remove_from_cart"}
                and isinstance(response.data, list)):
            state.record_cart_items(response.data)

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
        if vague_cart_quantity_request(message):
            return ChatResponse(answer=cart_clarification_reply(message, state))
        if self._contains_any(lowered, "你能做什么", "你会什么", "有哪些功能", "帮助", "help"):
            state.turn_count += 1
            return ChatResponse(answer=self._format_capabilities())

        # 知识检索意图判定与 LLM 模式守卫共用 knowledge_search_intent（唯一词表），
        # 见 app/knowledge_base.py 的"知识意图（唯一事实源）"。
        if knowledge_search_intent(message):
            topic = message[:30]
            result = await self._run_tool(
                "search_knowledge_base",
                # 意图路由（分库隔离）：由服务端同一词表决定检索规则库还是商品库
                {"query": message, "kb": route_knowledge_base(message)},
                session_id=session_id,
                access_token=access_token,
                success_prefix="查到的相关说明如下：",
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
                success_prefix="已准备支付订单，处理前需要您的确认。",
                reference=ref,
            )

        if self._contains_any(lowered, "下单", "购买", "买", "创建订单", "再来一单", "place order", "buy again", "order again"):
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
                        product_id = state.find_product_id_by_message(message)
                        if product_id is not None:
                            state.record_product(product_id)
                if product_id is None:
                    return clarification
            ref = ReferenceResolution(type="product", value=str(product_id)) if _extract_product_id_from_text(lowered) is None else None
            return await self._run_tool(
                "create_order",
                {"product_id": product_id, "quantity": quantity},
                session_id=session_id,
                access_token=access_token,
                success_prefix="已准备创建订单，处理前需要您的确认。",
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
                success_prefix="已准备取消订单，但执行前仍需要您的确认。",
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
                success_prefix="已准备清空购物车，处理前需要您的确认。",
            )

        if requests_cart_removal(message):
            cart_result = await self._registry.execute("get_cart", {}, session_id=session_id, access_token=access_token)
            if cart_result.outcome != "success":
                return self._response_for_result("get_cart", {}, cart_result)
            current_items = cart_result.output.get("data")
            if not isinstance(current_items, list):
                return ChatResponse(answer="暂时没能读取购物车，请稍后重试；商品尚未移除。")
            state.record_cart_items(current_items)
            cart_id, clarification = _resolve_or_clarify_cart_id(message, lowered, state)
            if clarification:
                return clarification
            state.record_cart_view()
            return await self._run_tool(
                "remove_from_cart",
                {"cart_id": cart_id},
                session_id=session_id,
                access_token=access_token,
                success_prefix="已准备删除购物车商品，处理前需要您的确认。",
            )

        if requests_cart_quantity_change(message):
            if requests_all_cart_quantity_change(message) or re.search(r"增加|减少|减掉", message):
                cart_result = await self._registry.execute("get_cart", {}, session_id=session_id, access_token=access_token)
                if cart_result.outcome != "success":
                    return self._response_for_result("get_cart", {}, cart_result)
                current_items = cart_result.output.get("data")
                if not isinstance(current_items, list):
                    return ChatResponse(answer="暂时没能获取购物车商品，请稍后重试。")
                state.record_cart_items(current_items)
                if not current_items:
                    return ChatResponse(answer="您的购物车目前是空的，没有需要修改数量的商品。", data=[])
            try:
                arguments = cart_quantity_arguments(message, state)
            except ValueError as exc:
                return ChatResponse(answer=str(exc))
            if arguments is None:
                return ChatResponse(answer=cart_clarification_reply(message, state))
            name = "update_cart_items" if "items" in arguments else "update_cart"
            return await self._run_tool(name, arguments, session_id=session_id, access_token=access_token,
                success_prefix="购物车数量已修改。")

        if self._contains_any(lowered, "加入购物车", "加购物车", "放购物车", "添加购物车", "add to cart"):
            if not access_token:
                return await self._run_tool(
                    "get_cart",
                    {},
                    session_id=session_id,
                    access_token=access_token,
                    success_prefix="请先登录后再添加商品到购物车。",
                )
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
                        product_id = state.find_product_id_by_message(message)
                        if product_id is not None:
                            state.record_product(product_id)
                if product_id is None:
                    return clarification
            product_name = state.product_name_for_id(product_id) or "该商品"
            result = await self._run_tool(
                "add_to_cart",
                {"product_id": product_id, "quantity": quantity},
                session_id=session_id,
                access_token=access_token,
                success_prefix=f"已将「{product_name}」加入购物车，共 {quantity} 件。",
            )
            if result.tool_calls and result.tool_calls[0].outcome == "success":
                state.record_product(product_id)
                state.record_cart_view()
            return result

        if self._contains_any(lowered, "购物车", "cart"):
            result = await self._run_tool(
                "get_cart",
                {},
                session_id=session_id,
                access_token=access_token,
                success_prefix="这是您当前的购物车：",
            )
            if result.tool_calls and result.tool_calls[0].outcome == "success":
                items = result.data if isinstance(result.data, list) else []
                state.record_cart_items([item for item in items if isinstance(item, dict)])
            else:
                state.record_cart_view()
            return result

        if self._contains_any(lowered, "订单", "order", "查一下订单", "看看订单"):
            explicit_id = extract_entity_id(message, "order")
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
                success_prefix = "您的订单列表如下："
                ref = None

            result = await self._registry.execute(
                tool_name,
                arguments,
                session_id=session_id,
                access_token=access_token,
            )

            if result.outcome == "success" and tool_name == "get_my_orders":
                orders = self._normalize_list(result.output.get("data"))
                if not orders:
                    state.record_order(None, selected=False)
                if orders:
                    first_order = orders[0]
                    first_id = first_order.get("id")
                    first_no = first_order.get("orderNo")
                    if first_id is not None:
                        state.record_order(first_id, first_no, selected=len(orders) == 1)

            if result.outcome in {"success", "confirmation_required"} and order_id is not None:
                order_data = result.output.get("data")
                order_no = order_data.get("orderNo") if isinstance(order_data, dict) else None
                state.record_order(order_id, order_no)

            if result.outcome == "confirmation_required":
                answer = success_prefix
            elif result.outcome == "success":
                answer = ("您目前还没有订单，可以先挑选商品加入购物车。"
                          if tool_name == "get_my_orders" and not result.output.get("data")
                          else f"{success_prefix}\n{self._format_data(result.output.get('data'))}")
            else:
                answer = customer_error_reply(result.output.get("error"))

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
            lowered, "推荐", "商品", "手机", "电脑", "耳机", "搜索", "找", "库存", "有货", "价格", "多少钱", "find", "product"
        ):
            list_all_products = self._contains_any(
                lowered,
                "有哪些商品",
                "商品列表",
                "所有商品",
                "有什么商品",
                "推荐一些商品",
                "推荐商品",
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
            min_price, max_price, in_stock = self._extract_price_filters(message)
            has_search_filters = any(
                value is not None for value in (min_price, max_price, in_stock)
            )
            allows_generic_filtered_search = has_search_filters and self._contains_any(
                lowered, "推荐", "商品", "产品", "搜索", "筛选", "找"
            )
            # 明确重新推荐泛类商品时，不继承上一轮的商品关键词。
            if allows_generic_filtered_search and not explicit_keyword and self._contains_any(lowered, "商品", "产品"):
                force_full_product_scan = True
            keyword = "" if force_full_product_scan else state.resolve_product_keyword(message, explicit_keyword)
            ref = None
            if not keyword and not force_full_product_scan:
                keyword = explicit_keyword or ""
            elif not explicit_keyword and keyword:
                ref = ReferenceResolution(type="product", value=keyword)
            if not keyword:
                if force_full_product_scan or allows_generic_filtered_search:
                    keyword = ""
                else:
                    return ChatResponse(answer="请告诉我您想搜索什么商品。")

            return await self._search_products(
                keyword, lowered, state, session_id, access_token,
                reference=ref,
                state_keyword=explicit_keyword or keyword,
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
                    success_prefix="已准备取消订单，但执行前仍需要您的确认。",
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
        if result.outcome == "confirmation_required" and result.confirmation is not None and self._approval_workflow is not None:
            await self._approval_workflow.start(
                thread_id=result.confirmation.token,
                action=result.confirmation.action,
                arguments=result.confirmation.arguments,
            )
        if result.outcome == "confirmation_required":
            description = result.confirmation.description if result.confirmation is not None else success_prefix
            answer = confirmation_reply(description)
        elif result.outcome == "success":
            data = result.output.get("data")
            mutation_tools = {"add_to_cart", "update_cart", "remove_from_cart", "clear_cart"}
            answer = success_prefix if data is None or name in mutation_tools else f"{success_prefix}\n{self._format_data(data)}"
            if name == "get_cart" and data == []:
                answer = "您的购物车目前是空的，可以先挑选商品加入购物车。"
            if name == "add_to_cart":
                answer = cart_add_reply(arguments, result.output)
                if self._state_store is not None and isinstance(result.output.get("cart_snapshot"), list):
                    state = await self._state_store.get(session_id, access_token)
                    state.record_cart_items(result.output["cart_snapshot"])
            elif result.output.get("message"):
                answer = result.output["message"]
                if self._state_store is not None and isinstance(result.output.get("cart_snapshot"), list):
                    state = await self._state_store.get(session_id, access_token)
                    state.record_cart_items(result.output["cart_snapshot"])
            elif result.output.get("unchanged"):
                answer = f"购物车中相关商品已经是 {arguments['quantity']} 件，无需重复修改。"

        else:
            answer = customer_error_reply(result.output.get("error"))
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
        state_keyword: str | None = None,
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
                state_keyword if state_keyword is not None else keyword,
                int(first["id"]) if first.get("id") is not None else None,
                str(first.get("name") or ""),
                shown_ids,
            )
        else:
            state.record_product_search(
                state_keyword if state_keyword is not None else keyword,
                shown_product_ids=state.shown_product_ids,
            )
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
            answer=customer_error_reply(result.output.get("error")),
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
            if keyword:
                return f"暂时没有找到与“{keyword}”匹配的在售商品。"
            return "暂时没有找到符合当前筛选条件的在售商品。"
        lines = ["我找到这些商品："]
        for product in products[:10]:
            lines.append(
                f"• {product.get('name') or '商品名称暂未显示'} — "
                f"{DemoAgentService._format_currency(product.get('price'))}，"
                f"{product_purchase_copy(product)}"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_product_detail(data: Any) -> str:
        if not isinstance(data, dict):
            return "没有查到这个商品的详情。"
        return (
            "商品详情如下：\n"
            f"• 商品：{data.get('name') or '商品名称暂未显示'}\n"
            f"• 价格：{DemoAgentService._format_currency(data.get('price'))}\n"
            f"• 购买提示：{product_purchase_copy(data)}\n"
            f"• 描述：{data.get('description') or '暂无描述'}"
        )

    @staticmethod
    def _format_capabilities() -> str:
        return (
            "我可以帮您做这些电商客服操作：\n"
            "• 匿名搜索/推荐商品，按预算、价格和常见偏好筛选。\n"
            "• 查询商品价格、是否有货和详情，并理解“它/这款/刚才那个”。\n"
            "• 登录后查看购物车、加入购物车、修改数量、删除或清空购物车。\n"
            "• 登录后查询订单、查看订单详情、取消待支付订单、创建订单和支付订单。\n"
            "• 解答售后规则、退换货政策和商品使用问题。\n"
            "下单、支付、取消订单和清空购物车会先请您确认。"
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
            return "暂时没有查询到相关内容。"
        if isinstance(data, list):
            lines = []
            for item in data[:8]:
                if not isinstance(item, dict):
                    lines.append(f"• {item}")
                    continue
                if item.get("orderNo"):
                    lines.append(
                        f"• 订单 {item['orderNo']} · "
                        f"{DemoAgentService._order_status(item.get('status')) or '状态待确认'} · "
                        f"{DemoAgentService._format_currency(item.get('finalAmount'))}"
                    )
                    continue
                if item.get("productName"):
                    quantity = item.get("quantity")
                    quantity_text = f" · {quantity} 件" if quantity is not None else ""
                    lines.append(
                        f"• {item['productName']}{quantity_text} · "
                        f"单价 {DemoAgentService._format_currency(item.get('price'))}"
                    )
                    continue
                if item.get("name"):
                    lines.append(
                        f"• {item['name']} · "
                        f"{DemoAgentService._format_currency(item.get('price'))}"
                    )
            return "\n".join(lines)
        if isinstance(data, dict):
            if data.get("orderNo"):
                payment_status = DemoAgentService._payment_status(data.get("paymentStatus"))
                amount_label = "实付金额" if data.get("paymentStatus") == 1 else "订单金额"
                return "\n".join(
                    [
                        f"订单号：{data['orderNo']}",
                        f"订单状态：{DemoAgentService._order_status(data.get('status')) or '待确认'}",
                        f"支付状态：{payment_status}",
                        f"{amount_label}：{DemoAgentService._format_currency(data.get('finalAmount'))}",
                    ]
                )
            return "已查询到相关信息，请查看下方详情。"
        return str(data)

    @staticmethod
    def _format_currency(value: Any) -> str:
        if value is None or value == "":
            return "金额待确认"
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return "金额待确认"
        formatted = f"{amount:,.2f}".rstrip("0").rstrip(".")
        return f"¥{formatted}"

    @staticmethod
    def _payment_status(status: Any) -> str:
        return {0: "未支付", 1: "已支付"}.get(status, "待确认")

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
        }.get(status, f"订单状态暂时无法获取，请稍后刷新")

    @staticmethod
    def _contains_any(text: str, *keywords: str) -> bool:
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _extract_number(text: str) -> int | None:
        match = re.search(r"\b(\d+)\b", text)
        return int(match.group(1)) if match else None

    @staticmethod
    def _extract_product_id(text: str) -> int | None:
        return extract_entity_id(text, "product")

    @staticmethod
    def _extract_cart_id(text: str) -> int | None:
        match = re.search(r"(?:cart\s*id|cartid|购物车项|购物车)\s*#?\s*(\d+)", text, re.IGNORECASE)
        return int(match.group(1)) if match else None

    @staticmethod
    def _extract_quantity(text: str) -> int:
        quantity = extract_quantity(text)
        return quantity if quantity is not None else 1

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
