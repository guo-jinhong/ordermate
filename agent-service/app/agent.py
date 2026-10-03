from __future__ import annotations

import json
import re
import asyncio
from contextvars import ContextVar
import time
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Any

from app.audit import AuditLogger
from app.clients.ecommerce_client import EcommerceApiError
from app.business_fields import mutation_is_consultation, extract_quantity, denies_mutation, requests_refund, requests_cart_quantity_change, requests_all_cart_quantity_change, cart_quantity_arguments, vague_cart_quantity_request, cart_clarification_reply, complete_cart_clarification, requests_cart_removal
from app.business_feedback import abandoned_action_reply, cart_add_reply, REFUND_UNAVAILABLE, confirmation_reply, customer_error_reply
from app.conversation_memory import ConversationMemoryStore
from app.conversation_state import ConversationState, ConversationStateStore, extract_entity_id, quoted_entity_name, is_generic_product_reference
from app.knowledge_base import knowledge_search_intent, route_knowledge_base
from app.product_terms import translate_product_keyword
from app.prompts import SYSTEM_PROMPT
from app.schemas import ChatResponse, ReferenceResolution, ToolCallRecord
from app.tools.definitions import TOOLS
from app.circuit_breaker import AsyncCircuitBreaker, CircuitBreakerOpenError
from app.metrics import llm_calls_total, llm_latency_seconds
from app.tools.registry import ToolRegistry


_llm_trace_context: ContextVar[list[dict] | None] = ContextVar(
    "llm_trace_context",
    default=None,
)
from app.security_guard import is_suspicious_instruction


# LLM 调用可观测埋点：复用统一审计日志，输出结构化为 JSON 的调用/失败事件
_llm_audit = AuditLogger()


def _usage_dict(usage: Any) -> dict | None:
    """兼容 chat.completions 与 responses 两种 usage 命名，提取 token 统计。"""
    if usage is None:
        return None
    out: dict[str, int] = {}
    for attr in ("prompt_tokens", "input_tokens"):
        value = getattr(usage, attr, None)
        if value is not None:
            out["input_tokens"] = value
            break
    for attr in ("completion_tokens", "output_tokens"):
        value = getattr(usage, attr, None)
        if value is not None:
            out["output_tokens"] = value
            break
    total = getattr(usage, "total_tokens", None)
    if total is not None:
        out["total_tokens"] = total
    return out or None


def build_state_context(state: ConversationState) -> str:
    lines = ["Conversation context / 对话上下文（用于解析代词如'它'、'这个'、'那个'）："]
    if state.last_topic:
        lines.append(f"- 上一个话题: {state.last_topic}")
    if state.last_order_id is not None:
        order_ref = f"#{state.last_order_id}"
        if state.last_order_no:
            order_ref += f" ({state.last_order_no})"
        lines.append(f"- Last referenced order / 上一个订单: {order_ref}")
    if state.last_product_keyword:
        lines.append(f"- 上一个搜索关键词: {state.last_product_keyword}")
    if state.last_product_id is not None:
        product_ref = f"#{state.last_product_id}"
        if state.last_product_name:
            product_ref += f" ({state.last_product_name})"
        lines.append(f"- 上一个商品: {product_ref}")
    if state.shown_products:
        shown = []
        for product in state.shown_products[:10]:
            product_id = product.get("id")
            name = product.get("name")
            price = product.get("price")
            stock = product.get("stock")
            if product_id is None or not name:
                continue
            extra = []
            if price is not None:
                extra.append(f"¥{price}")
            if stock is not None:
                extra.append(f"库存{stock}")
            suffix = f" ({', '.join(extra)})" if extra else ""
            shown.append(f"#{product_id} {name}{suffix}")
        if shown:
            lines.append("- 最近展示商品: " + "；".join(shown))
    if state.last_cart_viewed:
        lines.append("- 用户最近查看了购物车")
    if state.last_knowledge_topic:
        lines.append(f"- 上一个知识库话题: {state.last_knowledge_topic}")
    if state.turn_count > 0:
        lines.append(f"- 本次会话轮数: {state.turn_count}")
    if len(lines) == 1:
        lines.append("- 无先前上下文")
    return "\n".join(lines)


def update_state_from_tool(state: ConversationState, tool_name: str, arguments: dict[str, Any], output: Any) -> None:
    data = output.get("data") if isinstance(output, dict) else None

    if tool_name == "search_products":
        keyword = translate_product_keyword(arguments.get("keyword"))
        product_id = None
        product_name = None
        products = data.get("content") if isinstance(data, dict) else data
        shown_ids = []
        if isinstance(products, list) and products and isinstance(products[0], dict):
            product_id = products[0].get("id")
            product_name = products[0].get("name")
            shown_ids = [
                int(item["id"])
                for item in products
                if isinstance(item, dict) and item.get("id") is not None
            ]
            shown_products = [
                {
                    "id": int(item["id"]),
                    "name": str(item.get("name") or ""),
                    "price": item.get("price"),
                    "stock": item.get("stock"),
                }
                for item in products
                if isinstance(item, dict) and item.get("id") is not None
            ]
        else:
            shown_products = []
        state.record_product_search(
            str(keyword),
            int(product_id) if product_id is not None else None,
            str(product_name) if product_name else None,
            shown_ids,
            shown_products,
        )

    elif tool_name == "get_product_detail":
        product_id = arguments.get("product_id")
        product_name = data.get("name") if isinstance(data, dict) else None
        if product_id is not None:
            state.record_product(int(product_id), str(product_name) if product_name else None)

    elif tool_name == "get_my_orders":
        if isinstance(data, dict) and isinstance(data.get("content"), list):
            data = data["content"]
        if isinstance(data, list) and not data:
            state.record_order(None, selected=False)
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                order_id = first.get("id")
                order_no = first.get("orderNo")
                if order_id is not None:
                    state.record_order(int(order_id), str(order_no) if order_no else None, selected=len(data) == 1)

    elif tool_name == "get_order_detail":
        order_id = arguments.get("order_id")
        if order_id is not None:
            order_no = None
            if isinstance(data, dict):
                order_no = data.get("orderNo")
            state.record_order(int(order_id), str(order_no) if order_no else None)

    elif tool_name == "cancel_order":
        order_id = arguments.get("order_id")
        if order_id is not None:
            state.record_order(int(order_id))

    elif tool_name == "get_cart":
        cart_items = data if isinstance(data, list) else []
        state.record_cart_items([item for item in cart_items if isinstance(item, dict)])
        state.record_cart_view()

    elif tool_name == "add_to_cart":
        product_id = arguments.get("product_id")
        if product_id is not None:
            display = output.get("display") or {}
            state.record_product(int(product_id), display.get("product_name"))
        snapshot = output.get("cart_snapshot")
        if isinstance(snapshot, list):
            state.record_cart_items(snapshot)
        else:
            state.record_cart_view()

    elif tool_name in {"update_cart", "update_cart_items", "remove_from_cart", "clear_cart"}:
        if isinstance(output.get("cart_snapshot"), list):
            state.record_cart_items(output["cart_snapshot"])
        state.record_cart_view()

    elif tool_name in {"create_order", "pay_order"}:
        order_id = arguments.get("order_id")
        if order_id is not None:
            state.record_order(int(order_id))

    elif tool_name == "search_knowledge_base":
        query = arguments.get("query")
        if query:
            state.record_knowledge_topic(str(query)[:30])


_REFERRAL_PATTERN = re.compile(r"它|这个|那个|该|此|刚才|刚刚|再|还|这|那|its?|this|that|the (?:order|product)")


def _contains_any(text: str, *keywords: str) -> bool:
    return any(keyword in text for keyword in keywords)


def _has_reference_to_state(message: str, state: ConversationState, topic: str) -> bool:
    if not _REFERRAL_PATTERN.search(message):
        return False
    return state.last_topic == topic


def _guard_tool_call(
    name: str,
    arguments: dict[str, Any],
    message: str,
    state: ConversationState,
) -> str | None:
    lowered = message.lower()
    if name in ToolRegistry._WRITE_TOOLS and mutation_is_consultation(message):
        return "您是在咨询或引用操作，本次未操作。请明确要进行的操作。"
    if name == "refund_order":
        return REFUND_UNAVAILABLE
    if name in {"add_to_cart", "update_cart", "update_cart_items", "remove_from_cart", "clear_cart", "create_order", "cancel_order", "pay_order", "refund_order"} and denies_mutation(message):
        return "本轮包含否定操作的要求，未执行修改。请明确要执行的操作。"
    if name == "cancel_order" and not _contains_any(lowered, "取消", "cancel"):
        return "我不会在用户没有明确要求取消订单时调用取消工具。"
    if name == "update_cart_items":
        try:
            expected_arguments = cart_quantity_arguments(message, state)
        except ValueError as exc:
            return str(exc)
        if not expected_arguments or "items" not in expected_arguments:
            return "请明确需要批量修改的购物车商品和目标数量。"
        expected_items = {(item["cart_id"], item["quantity"]) for item in expected_arguments["items"]}
        supplied = arguments.get("items") or []
        if any(not isinstance(item, dict) for item in supplied):
            return "工具参数与指定商品范围不一致，请重新核对。"
        actual_items = {(item.get("cart_id"), item.get("quantity")) for item in supplied}
        if actual_items != expected_items or len(supplied) != len(expected_items) or arguments.get("quantity") != expected_arguments["quantity"]:
            return "工具参数与指定商品范围或数量不一致，请重新核对。"
        return None
    # 模型参数必须与本轮明确选择一致，不能把历史对象当成当前对象。
    kind = "product" if name in {"add_to_cart", "create_order", "get_product_detail"} else "cart" if name in {"update_cart", "remove_from_cart"} else None
    if kind:
        key = "product_id" if kind == "product" else "cart_id"
        expected = state.resolve_product_id(message, None) if kind == "product" else state.resolve_cart_id(message, None)
        supplied = arguments.get(key)
        if expected is not None and supplied is not None and str(supplied) != str(expected):
            return "工具参数与本轮指定的商品或购物车项不一致，请重新核对编号。"
        if expected is None:
            return "无法唯一确认本轮指定的商品或购物车项，请提供准确名称或编号。"
        try:
            parsed_change = cart_quantity_arguments(message, state) if name == "update_cart" else None
        except ValueError as exc:
            return str(exc)
        quantity = parsed_change.get("quantity") if parsed_change else _extract_quantity(message)
        if quantity is not None and arguments.get("quantity") is not None and str(arguments["quantity"]) != str(quantity):
            return "工具数量与本轮指定数量不一致，请重新核对。"
    if name in {"cancel_order", "get_order_detail", "pay_order"}:
        expected_order = state.resolve_order_id(message, None)
        if expected_order is None:
            return "无法确认本轮指定的订单，请提供准确订单编号或先查看订单详情。"
        if arguments.get("order_id") is not None and str(arguments["order_id"]) != str(expected_order):
            return "工具订单编号与本轮指定订单不一致，请重新核对。"
    if name == "cancel_order":
        if not _contains_any(lowered, "取消", "cancel"):
            return "我不会在用户没有明确要求取消订单时调用取消工具。"
        if arguments.get("order_id") is None and state.last_order_id is None:
            return "取消订单前需要明确订单 ID。"
        return None

    if name == "get_order_detail":
        has_order_intent = _contains_any(lowered, "订单", "order", "详情", "详细")
        if has_order_intent or _has_reference_to_state(message, state, "order"):
            return None
        return "查询订单详情需要用户明确提到订单或引用上一笔订单。"

    if name == "get_my_orders":
        if _contains_any(lowered, "订单", "order"):
            return None
        return "只有用户询问订单时才会读取订单列表。"

    if name == "get_cart":
        if _contains_any(lowered, "购物车", "cart") or requests_cart_quantity_change(message):
            return None
        return "只有用户询问购物车时才会读取购物车。"

    if name == "add_to_cart":
        if _contains_any(lowered, "加购物车", "加入购物车", "放购物车", "添加购物车", "add to cart"):
            return None
        return "只有用户明确要求加入购物车时才会修改购物车。"

    if name == "update_cart":
        if requests_cart_quantity_change(message):
            return None
        return "只有用户明确要求修改购物车数量时才会修改购物车。"

    if name == "remove_from_cart":
        if requests_cart_removal(message):
            return None
        return "只有用户明确要求删除购物车商品时才会修改购物车。"

    if name == "clear_cart":
        if _contains_any(lowered, "清空购物车", "clear cart"):
            return None
        return "只有用户明确要求清空购物车时才会清空购物车。"

    if name == "create_order":
        if _contains_any(lowered, "下单", "购买", "买", "创建订单", "place order", "order it"):
            return None
        return "只有用户明确要求下单时才会创建订单。"

    if name == "pay_order":
        if _contains_any(lowered, "支付", "付款", "pay"):
            return None
        return "只有用户明确要求支付时才会调用支付工具。"

    if name == "search_products":
        if _contains_any(
            lowered,
            "推荐",
            "商品",
            "搜索",
            "找",
            "买",
            "价格",
            "库存",
            "有货",
            "手机",
            "电脑",
            "笔记本",
            "耳机",
            "充电宝",
            "鞋",
            "跑鞋",
            "水壶",
            "杯",
            "键盘",
            "鼠标",
            "相机",
            "手表",
            "product",
            "price",
            "stock",
            "available",
            "find",
            "search",
            "recommend",
            "phone",
            "laptop",
            "headphones",
        ) or _has_reference_to_state(message, state, "product"):
            return None
        return "只有用户询问商品时才会搜索商品。"

    if name == "search_knowledge_base":
        # 触发判定与 demo 模式共用 knowledge_search_intent（唯一词表），
        # 见 app/knowledge_base.py 的"知识意图（唯一事实源）"。
        if knowledge_search_intent(message):
            return None
        return "只有用户询问规则、政策、保修或商品参数等知识库内容时才会检索知识库。"

    return None


_TOOL_PARAM_REQUIREMENTS: dict[str, list[tuple[str, str]]] = {
    "cancel_order": [("order_id", "state.last_order_id")],
    "get_order_detail": [("order_id", "state.last_order_id")],
    "get_my_orders": [],
    "search_products": [("keyword", "none")],
    "get_product_detail": [("product_id", "state.last_product_id")],
    "add_to_cart": [("product_id", "state.last_product_id"), ("quantity", "message.quantity")],
    "update_cart": [("cart_id", "state.cart_id"), ("quantity", "message.quantity")],
    "remove_from_cart": [("cart_id", "state.cart_id")],
    "clear_cart": [],
    "create_order": [("product_id", "state.last_product_id"), ("quantity", "message.quantity")],
    "pay_order": [("order_id", "state.last_order_id")],
    "get_cart": [],
    "search_knowledge_base": [("query", "none")],
}


_TOOL_PARAM_LABELS: dict[str, dict[str, str]] = {
    "search_products": {
        "keyword": "商品关键词，例如手机、耳机、充电宝",
    },
    "get_product_detail": {
        "product_id": "商品名称或编号",
    },
    "get_cart": {},
    "add_to_cart": {
        "product_id": "商品名称或编号",
        "quantity": "加入购物车数量",
    },
    "update_cart": {
        "cart_id": "购物车中的商品名称",
        "quantity": "新的商品数量",
    },
    "remove_from_cart": {
        "cart_id": "购物车中的商品名称",
    },
    "clear_cart": {},
    "get_my_orders": {},
    "get_order_detail": {
        "order_id": "订单号",
    },
    "cancel_order": {
        "order_id": "订单号",
    },
    "create_order": {
        "product_id": "商品名称或编号",
        "quantity": "下单数量",
    },
    "pay_order": {
        "order_id": "订单号",
    },
    "search_knowledge_base": {
        "query": "要查询的规则、售后、FAQ 或产品手册问题",
    },
}


def _model_uses_chat_completions(model: str) -> bool:
    return model.lower().startswith("deepseek-")


_PRODUCT_QUERY_PATTERN = re.compile(
    r"手机|耳机|充电宝|笔记本|电脑|水杯|运动鞋|商品|产品|价格|库存|有货|"
    r"推荐|搜索|查询|预算|以内|以上|不超过|低于|高于|"
    r"product|price|stock|available|recommend|search|budget|under|over",
    re.IGNORECASE,
)
_ORDER_QUERY_PATTERN = re.compile(
    r"订单|订单号|物流|支付|取消订单|下单|购买|买|"
    r"order|payment|pay|cancel|purchase",
    re.IGNORECASE,
)
_CART_QUERY_PATTERN = re.compile(
    r"购物车|加购|加入购物车|清空购物车|cart",
    re.IGNORECASE,
)


def _required_business_tools(message: str) -> set[str]:
    required: set[str] = set()
    if _PRODUCT_QUERY_PATTERN.search(message):
        required.add("search_products")
    if _ORDER_QUERY_PATTERN.search(message):
        required.update({"get_my_orders", "get_order_detail", "cancel_order", "create_order", "pay_order"})
    if _CART_QUERY_PATTERN.search(message):
        required.update({"get_cart", "add_to_cart", "update_cart", "remove_from_cart", "clear_cart"})
    return required


def _should_retry_for_missing_tool_call(message: str, records: list[ToolCallRecord]) -> bool:
    if records:
        return False
    return bool(_required_business_tools(message))


def _is_confirmation_message(message: str) -> bool:
    normalized = re.sub(r"\s+", "", message.lower())
    return normalized in {
        "确认",
        "确定",
        "对",
        "是",
        "是的",
        "没错",
        "可以",
        "执行",
        "确认执行",
        "同意",
        "ok",
        "yes",
        "y",
    }


def _extract_order_id_from_message(message: str) -> int | None:
    return extract_entity_id(message, "order")


def _direct_cancel_order_arguments(message: str, state: ConversationState) -> dict[str, Any] | None:
    if denies_mutation(message):
        return None
    lowered = message.lower()
    if not _contains_any(lowered, "取消订单", "撤销订单", "作废订单", "cancel order", "revoke order"):
        return None
    order_id = _extract_order_id_from_message(message)
    if order_id is None:
        order_id = state.resolve_order_id(message, None)
    if order_id is None:
        return None
    return {"order_id": order_id}


def _direct_clear_cart_arguments(message: str, state: ConversationState) -> dict[str, Any] | None:
    if denies_mutation(message):
        return None
    lowered = message.lower()
    if not _contains_any(lowered, "清空购物车", "清空全部", "clear cart", "empty cart"):
        return None
    return {}


def _direct_add_to_cart_arguments(message: str, state: ConversationState) -> dict[str, Any] | None:
    if denies_mutation(message):
        return None
    lowered = message.lower()
    if not _contains_any(lowered, "加购物车", "加入购物车", "放购物车", "添加购物车", "add to cart"):
        return None
    product_id = state.resolve_product_id(message, None)
    if product_id is None:
        return None
    quantity = _extract_quantity(message)
    return {
        "product_id": product_id,
        "quantity": quantity if quantity is not None else 1,
    }


def _direct_update_cart_arguments(message: str, state: ConversationState) -> dict[str, Any] | None:
    return cart_quantity_arguments(message, state)


def _answer_for_direct_tool(
    name: str,
    arguments: dict[str, Any],
    execution_output: dict[str, Any],
    outcome: str,
    state: ConversationState,
) -> str:
    if outcome == "success" and execution_output.get("message"):
        return execution_output["message"]
    if name == "add_to_cart":
        display = execution_output.get("display")
        display_name = display.get("product_name") if isinstance(display, dict) else None
        product_name = display_name or state.product_name_for_id(arguments.get("product_id")) or "该商品"
        quantity = arguments.get("quantity") or 1
        if outcome == "success":
            return cart_add_reply(arguments, execution_output, product_name)
        return customer_error_reply(execution_output.get("error"))
    if name == "remove_from_cart":
        if outcome == "confirmation_required":
            data = execution_output.get("data") or {}
            product_name = data.get("product_name") or state.cart_product_name_for_id(arguments.get("cart_id")) or "该商品"
            return confirmation_reply(f"从购物车移除「{product_name}」")
        return customer_error_reply(execution_output.get("error"))
    if name == "update_cart":
        quantity = arguments.get("quantity")
        if execution_output.get("unchanged"):
            return f"这件商品在购物车中已经是 {quantity} 件，无需重复修改。"
        data = execution_output.get("data")
        data_name = data.get("product_name") if isinstance(data, dict) else None
        product_name = data_name or state.cart_product_name_for_id(arguments.get("cart_id")) or "该商品"
        if outcome == "confirmation_required":
            previous = data.get("previous_quantity") if isinstance(data, dict) else None
            change = f"从 {previous} 件改为 {quantity} 件" if previous is not None else f"改为 {quantity} 件"
            return f"准备将「{product_name}」的购物车数量{change}，确认后才会修改。"
        if outcome == "success":
            return f"已将「{product_name}」的数量修改为 {quantity} 件。"
        return customer_error_reply(execution_output.get("error"))
    if name == "update_cart_items":
        quantity = arguments.get("quantity")
        if execution_output.get("unchanged"):
            return f"这些商品在购物车中已经都是 {quantity} 件，无需重复修改。"
        items = arguments.get("items") or []
        if outcome == "confirmation_required":
            return f"已准备把购物车中 {len(items)} 个商品的数量都改为 {quantity} 件，请点击确认按钮，或直接回复“确认”。"
        if outcome == "success":
            return f"购物车中 {len(items)} 个商品的数量已修改为 {quantity} 件。"
        return customer_error_reply(execution_output.get("error"))
    if name == "cancel_order":
        data = execution_output.get("data")
        order_no = data.get("orderNo") if isinstance(data, dict) else None
        order_label = order_no or state.last_order_no or "当前订单"
        if outcome == "confirmation_required":
            return confirmation_reply(f"取消订单 {order_label}")
        if outcome == "success":
            return f"订单 {order_label} 已成功取消。"
        return customer_error_reply(execution_output.get("error"))
    if name == "clear_cart":
        if outcome == "confirmation_required":
            return confirmation_reply("清空购物车")
        if outcome == "success":
            return "购物车已清空。"
        return customer_error_reply(execution_output.get("error"))
    if outcome == "success":
        return "操作已完成。"
    return customer_error_reply(execution_output.get("error"))


def _customer_order_list_answer(data: Any) -> str:
    """订单列表使用受控文案，避免模型主动承诺未开放的支付或退款能力。"""
    order_count = len(data) if isinstance(data, list) else 0
    if not order_count:
        return "您目前还没有订单，可以先挑选商品加入购物车。"
    return f"查到您的订单，共 {order_count} 笔。您可以查看订单详情；待支付订单还可以取消。"


def _missing_tool_retry_message(message: str) -> str:
    tools = ", ".join(sorted(_required_business_tools(message)))
    return (
        "上一轮没有调用工具，但用户问题涉及结构化电商业务数据。"
        f"必须从这些工具中选择合适工具调用：{tools}。"
        "在工具返回真实数据前，不得输出商品、价格、库存、购物车或订单相关结论。"
        f"原始用户问题：{message}"
    )


def _chat_tools_from_responses_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chat_tools = []
    for tool in tools:
        if tool.get("type") != "function":
            continue
        function = {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
        }
        chat_tools.append({"type": "function", "function": function})
    return chat_tools


def _chat_messages_from_responses_input(
    instructions: str,
    input_items: list[Any],
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": instructions}]
    index = 0
    while index < len(input_items):
        item = input_items[index]
        if isinstance(item, dict):
            item_type = item.get("type")
            if item_type == "function_call_output":
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": item["call_id"],
                        "content": item["output"],
                    }
                )
            elif item.get("role") in {"user", "assistant", "system"}:
                messages.append(
                    {
                        "role": item["role"],
                        "content": item.get("content", ""),
                    }
                )
            index += 1
            continue

        if getattr(item, "type", None) == "function_call":
            tool_calls = []
            while index < len(input_items) and getattr(input_items[index], "type", None) == "function_call":
                call_item = input_items[index]
                tool_calls.append(
                    {
                        "id": call_item.call_id,
                        "type": "function",
                        "function": {
                            "name": call_item.name,
                            "arguments": call_item.arguments,
                        },
                    }
                )
                index += 1
            messages.append(
                {
                    "role": "assistant",
                    "tool_calls": tool_calls,
                }
            )
            continue
        index += 1
    return messages


def _responses_shape_from_chat_completion(completion: Any) -> Any:
    message = completion.choices[0].message
    tool_calls = getattr(message, "tool_calls", None) or []
    output = [
        SimpleNamespace(
            type="function_call",
            name=tool_call.function.name,
            arguments=tool_call.function.arguments,
            call_id=tool_call.id,
        )
        for tool_call in tool_calls
    ]
    return SimpleNamespace(output=output, output_text=getattr(message, "content", None) or "")


def _check_missing_params(
    name: str, arguments: dict[str, Any]
) -> list[str]:
    requirements = _TOOL_PARAM_REQUIREMENTS.get(name)
    if not requirements:
        return []
    missing = []
    for param, _ in requirements:
        if arguments.get(param) is None:
            missing.append(param)
    return missing


def _infer_from_state(
    name: str,
    arguments: dict[str, Any],
    state: ConversationState,
    missing: list[str],
    message: str = "",
) -> dict[str, Any]:
    inferred = dict(arguments)
    for param in missing:
        requirements = _TOOL_PARAM_REQUIREMENTS.get(name, [])
        for req_param, source in requirements:
            if req_param == param:
                value = None
                if source == "state.last_order_id":
                    value = state.resolve_order_id(message, None) if message else state.last_order_id
                elif source == "state.last_product_id":
                    value = state.resolve_product_id(message, None) if message else state.last_product_id
                elif source == "message.quantity":
                    value = _extract_quantity(message) if message else None
                    if value is None and message and name in {"add_to_cart", "create_order"}:
                        value = 1
                if value is not None:
                    inferred[param] = value
    return inferred


def _generate_clarification(
    name: str,
    missing: list[str],
    arguments: dict[str, Any],
    state: ConversationState,
) -> str:
    inferred = _infer_from_state(name, arguments, state, missing)
    still_missing = [m for m in missing if inferred.get(m) is None]
    if not still_missing:
        return ""
    labels = _TOOL_PARAM_LABELS.get(name, {})
    label_parts = [labels.get(m, m) for m in still_missing]
    if len(label_parts) == 1:
        return f"请告诉我{label_parts[0]}。"
    return f"请同时提供：{'、'.join(label_parts)}。"


def _extract_quantity(message: str) -> int | None:
    return extract_quantity(message)


def _detect_reference(
    message: str,
    records: list[ToolCallRecord],
    pre_chat_order_id: int | None,
    pre_chat_product_keyword: str | None,
) -> ReferenceResolution | None:
    if not _REFERRAL_PATTERN.search(message):
        return None
    for record in records:
        if record.name in ("get_order_detail", "cancel_order"):
            arg_order_id = record.arguments.get("order_id")
            if (
                arg_order_id is not None
                and pre_chat_order_id is not None
                and str(arg_order_id) == str(pre_chat_order_id)
            ):
                return ReferenceResolution(type="order", value=str(arg_order_id))
        elif record.name == "search_products":
            arg_keyword = record.arguments.get("keyword")
            if (
                arg_keyword
                and pre_chat_product_keyword
                and str(arg_keyword) == str(pre_chat_product_keyword)
            ):
                return ReferenceResolution(type="product", value=str(arg_keyword))
    return None


def _normalize_tool_arguments(
    name: str,
    arguments: dict[str, Any],
    message: str,
    state: ConversationState | None = None,
) -> dict[str, Any]:
    normalized = dict(arguments)
    if name in {"add_to_cart", "create_order"}:
        if normalized.get("product_id") is None and state is not None:
            product_id = state.resolve_product_id(message, None)
            if product_id is not None:
                normalized["product_id"] = product_id
        if normalized.get("quantity") is None:
            normalized["quantity"] = _extract_quantity(message) or 1
    return normalized


def _post_process_tool_output(
    name: str,
    execution_output: dict[str, Any],
    message: str,
) -> dict[str, Any]:
    return execution_output


def _normalize_products(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("content"), list):
        data = data["content"]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict) and {"id", "name", "price"} & set(data.keys()):
        return [data]
    return []


class AgentService:
    def __init__(
        self,
        model_client: Any,
        registry: ToolRegistry,
        *,
        model: str,
        max_tool_rounds: int = 5,
        memory: ConversationMemoryStore | None = None,
        state_store: ConversationStateStore | None = None,
        confirmed_action_executor: Any | None = None,
        approval_workflow: Any | None = None,
        fallback_model_client: Any | None = None,
        fallback_model: str | None = None,
        llm_circuit_breaker: AsyncCircuitBreaker | None = None,
    ) -> None:
        self._model_client = model_client
        self._fallback_model_client = fallback_model_client
        self._fallback_model = fallback_model
        self._registry = registry
        self._model = model
        self._llm_breaker = llm_circuit_breaker or AsyncCircuitBreaker("llm")
        self._max_tool_rounds = max_tool_rounds
        self._memory = memory
        self._state_store = state_store
        self._confirmed_action_executor = confirmed_action_executor
        self._approval_workflow = approval_workflow

    async def _create_model_response(
        self,
        *,
        instructions: str,
        input_items: list[Any],
    ) -> Any:
        start = time.monotonic()
        error: str | None = None
        usage: dict | None = None

        async def _call(client, model: str):
            if _model_uses_chat_completions(model) and hasattr(client, "chat"):
                completion = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=model,
                        messages=_chat_messages_from_responses_input(instructions, input_items),
                        tools=_chat_tools_from_responses_tools(TOOLS),
                        extra_body={"thinking": {"type": "disabled"}},
                    ),
                    timeout=20,
                )
                return _responses_shape_from_chat_completion(completion), getattr(completion, "usage", None)
            response = await asyncio.wait_for(
                client.responses.create(
                    model=model,
                    instructions=instructions,
                    tools=TOOLS,
                    input=input_items,
                ),
                timeout=20,
            )
            return response, getattr(response, "usage", None)

        try:
            # 熔断器保护：连续失败后直接抛 CircuitBreakerOpenError，不再打 LLM
            try:
                result, resp_usage = await self._llm_breaker.call(
                    _call, self._model_client, self._model
                )
            except CircuitBreakerOpenError:
                # 主模型熔断，尝试 fallback
                if self._fallback_model_client is not None and self._fallback_model is not None:
                    result, resp_usage = await _call(self._fallback_model_client, self._fallback_model)
                else:
                    raise
            except Exception:
                # 主模型失败，尝试 fallback（不重复计入熔断，fallback 成功也算恢复）
                if self._fallback_model_client is not None and self._fallback_model is not None:
                    result, resp_usage = await _call(self._fallback_model_client, self._fallback_model)
                else:
                    raise
            usage = _usage_dict(resp_usage)
            return result
        except Exception as exc:  # noqa: BLE001 - 记录后仍需向上抛出，交由上层降级处理
            error = str(exc)
            raise
        finally:
            latency_ms = int((time.monotonic() - start) * 1000)
            # 收集展示用埋点（键名避开 'token'，防止前端把统计数字误脱敏）
            entry: dict[str, Any] = {"model": self._model, "latency_ms": latency_ms}
            if error is not None:
                entry["error"] = error
            elif usage:
                entry.update(
                    input=usage.get("input_tokens"),
                    output=usage.get("output_tokens"),
                    total=usage.get("total_tokens"),
                )
                llm_calls_total.labels(model=self._model, outcome="success").inc()
                llm_latency_seconds.observe(latency_ms / 1000.0)
                entry = {key: value for key, value in entry.items() if value is not None}
            trace = _llm_trace_context.get()
            if trace is not None:
                trace.append(entry)

            if error is not None:
                _llm_audit.emit(
                    "llm_call_failed",
                    model=self._model,
                    latency_ms=latency_ms,
                    error=error,
                )
                outcome = "timeout" if "Timeout" in (error or "") else "error"
                llm_calls_total.labels(model=self._model, outcome=outcome).inc()
                llm_latency_seconds.observe(latency_ms / 1000.0)
            else:
                _llm_audit.emit(
                    "llm_call",
                    model=self._model,
                    latency_ms=latency_ms,
                    **(usage or {}),
                )

    def collect_llm_trace(self) -> list[dict]:
        """取出当前异步请求的 LLM 埋点，不与并发请求共享状态。"""
        trace = list(_llm_trace_context.get() or [])
        _llm_trace_context.set([])
        return trace

    async def chat(
        self,
        message: str,
        *,
        session_id: str,
        access_token: str | None,
    ) -> ChatResponse:
        _llm_trace_context.set([])
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

        history = (
            await self._memory.get(session_id, access_token)
            if self._memory is not None
            else []
        )

        summary_text = None
        compressed_count = 0
        if self._memory is not None and history:
            compress_result = await self._memory.summarize_and_compress(session_id, access_token)
            if compress_result:
                summary_text, compressed_count = compress_result
                history = await self._memory.get(session_id, access_token)

        state_context = build_state_context(state) if self._state_store is not None else None
        context_parts = [SYSTEM_PROMPT]
        if summary_text:
            context_parts.append(f"[历史对话摘要] {summary_text}")
        if state_context:
            context_parts.append(state_context)
        system_instructions = "\n\n".join(context_parts)

        input_items: list[Any] = [*history, {"role": "user", "content": message}]
        records: list[ToolCallRecord] = []
        pending_confirmation = None
        last_data = None
        if summary_text is not None:
            state.record_summary(summary_text, compressed_turns=compressed_count)

        pre_chat_order_id = state.last_order_id
        pre_chat_product_keyword = state.last_product_keyword
        forced_tool_retry = False

        if message.strip() in {'取消这次操作', '放弃这次操作', '不改了', '不要改了', '不执行', '放弃', '算了'} and state.pending_confirmation_token:
            abandoned_action = state.pending_confirmation_action or ''
            try:
                pending = await self._registry.consume_confirmation(state.pending_confirmation_token, session_id, access_token)
                operations = getattr(self._registry, "operations", None)
                if operations:
                    await operations.transition(pending.token, {"accepted"}, "cancelled", {"status": "cancelled", "message": abandoned_action_reply(abandoned_action)})
                if self._approval_workflow is not None:
                    await self._approval_workflow.resume(pending.token, False, action=pending.action, arguments=pending.arguments)
            except EcommerceApiError:
                pass
            state.clear_confirmation()
            if self._state_store is not None:
                await self._state_store.save(session_id, access_token, state)
            return ChatResponse(answer=abandoned_action_reply(abandoned_action))

        if (
            _is_confirmation_message(message)
            and state.pending_confirmation_token
            and state.pending_confirmation_action
            and state.pending_confirmation_arguments is not None
            and self._confirmed_action_executor is not None
        ):
            try:
                pending = await self._registry.consume_confirmation(state.pending_confirmation_token, session_id, access_token)
                if self._approval_workflow is not None:
                    await self._approval_workflow.resume(pending.token, True, action=pending.action, arguments=pending.arguments)
                data, answer = await self._confirmed_action_executor(
                    pending.action,
                    pending.arguments,
                    access_token,
                    session_id,
                )
                if pending.action == "remove_from_cart" and isinstance(data, list):
                    state.record_cart_items(data)
                state.clear_confirmation()
                if self._memory is not None:
                    await self._memory.append_turn(session_id, access_token, message, answer)
                if self._state_store is not None:
                    state.turn_count += 1
                    await self._state_store.save(session_id, access_token, state)
                return ChatResponse(answer=answer, tool_calls=[], data=data)
            except Exception as exc:
                state.clear_confirmation()
                if self._state_store is not None:
                    await self._state_store.save(session_id, access_token, state)
                return ChatResponse(answer=customer_error_reply(str(exc)), tool_calls=[])

        if _is_confirmation_message(message):
            return ChatResponse(answer="当前没有待确认的操作。请先说明您要修改的商品或订单。")
        message = complete_cart_clarification(message, state)
        if vague_cart_quantity_request(message):
            answer = cart_clarification_reply(message, state)
            if self._memory is not None:
                await self._memory.append_turn(session_id, access_token, message, answer)
            if self._state_store is not None:
                await self._state_store.save(session_id, access_token, state)
            return ChatResponse(answer=answer)
        if _contains_any(message.lower(), "加入购物车", "加购物车", "放购物车", "添加购物车") and is_generic_product_reference(message) and state.resolve_product_id(message, None) is None:
            return ChatResponse(answer="您想把哪件商品加入购物车？请告诉我商品名称，或从商品卡片操作。")
        direct_cancel_arguments = _direct_cancel_order_arguments(message, state)
        if direct_cancel_arguments is not None:
            execution = await self._registry.execute(
                "cancel_order",
                direct_cancel_arguments,
                session_id=session_id,
                access_token=access_token,
            )
            execution_output = _post_process_tool_output(
                "cancel_order", execution.output, message
            )
            if execution.confirmation is not None:
                state.remember_confirmation(
                    execution.confirmation.token,
                    execution.confirmation.action,
                    execution.confirmation.arguments,
                )
            answer = _answer_for_direct_tool(
                "cancel_order",
                direct_cancel_arguments,
                execution_output,
                execution.outcome,
                state,
            )
            record = ToolCallRecord(
                name="cancel_order",
                arguments=direct_cancel_arguments,
                outcome=execution.outcome,
                result_message=execution_output.get("error") if execution.outcome == "error" else None,
            )
            if self._memory is not None:
                await self._memory.append_turn(session_id, access_token, message, answer)
            if self._state_store is not None:
                state.turn_count += 1
                await self._state_store.save(session_id, access_token, state)
            return ChatResponse(
                answer=answer,
                tool_calls=[record],
                confirmation=execution.confirmation,
                data=execution_output.get("data"),
                reference=ReferenceResolution(
                    type="order",
                    value=str(direct_cancel_arguments["order_id"]),
                ),
            )

        direct_clear_arguments = _direct_clear_cart_arguments(message, state)
        if direct_clear_arguments is not None:
            execution = await self._registry.execute(
                "clear_cart",
                {},
                session_id=session_id,
                access_token=access_token,
            )
            execution_output = _post_process_tool_output(
                "clear_cart", execution.output, message
            )
            if execution.confirmation is not None:
                state.remember_confirmation(
                    execution.confirmation.token,
                    execution.confirmation.action,
                    execution.confirmation.arguments,
                )
            answer = _answer_for_direct_tool(
                "clear_cart",
                {},
                execution_output,
                execution.outcome,
                state,
            )
            record = ToolCallRecord(
                name="clear_cart",
                arguments={},
                outcome=execution.outcome,
                result_message=execution_output.get("error") if execution.outcome == "error" else None,
            )
            if self._memory is not None:
                await self._memory.append_turn(session_id, access_token, message, answer)
            if self._state_store is not None:
                state.turn_count += 1
                await self._state_store.save(session_id, access_token, state)
            return ChatResponse(
                answer=answer,
                tool_calls=[record],
                confirmation=execution.confirmation,
                data=execution_output.get("data"),
                reference=ReferenceResolution(
                    type="cart",
                    value="current",
                ),
            )

        # 删除直接走真实购物车工具；模型不参与执行结果判定。
        if requests_cart_removal(message):
            cart_result = await self._registry.execute("get_cart", {}, session_id=session_id, access_token=access_token)
            if cart_result.outcome != "success":
                return ChatResponse(answer=customer_error_reply(cart_result.output.get("error")),
                    tool_calls=[ToolCallRecord(name="get_cart", arguments={}, outcome=cart_result.outcome)])
            current_items = cart_result.output.get("data")
            if not isinstance(current_items, list):
                return ChatResponse(answer="暂时没能读取购物车，请稍后重试；商品尚未移除。")
            state.record_cart_items(current_items)
            cart_id = state.resolve_cart_id(message, None)
            if cart_id is None:
                if self._state_store is not None:
                    await self._state_store.save(session_id, access_token, state)
                return ChatResponse(answer="您想移除购物车中的哪件商品？请提供商品名称，或点击对应卡片的移除按钮。"
                    if current_items else "购物车目前是空的，没有需要移除的商品。", data=current_items,
                    tool_calls=[ToolCallRecord(name="get_cart", arguments={}, outcome="success")])
            arguments = {"cart_id": cart_id}
            execution = await self._registry.execute("remove_from_cart", arguments, session_id=session_id, access_token=access_token)
            if execution.confirmation is not None:
                state.remember_confirmation(execution.confirmation.token, execution.confirmation.action, execution.confirmation.arguments)
            if execution.outcome == "success":
                update_state_from_tool(state, "remove_from_cart", arguments, execution.output)
            answer = _answer_for_direct_tool("remove_from_cart", arguments, execution.output, execution.outcome, state)
            if self._memory is not None:
                await self._memory.append_turn(session_id, access_token, message, answer)
            if self._state_store is not None:
                state.turn_count += 1
                await self._state_store.save(session_id, access_token, state)
            return ChatResponse(answer=answer,
                tool_calls=[ToolCallRecord(name="remove_from_cart", arguments=arguments, outcome=execution.outcome,
                    result_message=execution.output.get("error") if execution.outcome == "error" else None)],
                confirmation=execution.confirmation, data=execution.output.get("data"))

        direct_add_arguments = _direct_add_to_cart_arguments(message, state)
        if direct_add_arguments is not None:
            execution = await self._registry.execute(
                "add_to_cart",
                direct_add_arguments,
                session_id=session_id,
                access_token=access_token,
            )
            execution_output = _post_process_tool_output(
                "add_to_cart", execution.output, message
            )
            if self._state_store is not None and execution.outcome == "success":
                update_state_from_tool(state, "add_to_cart", direct_add_arguments, execution_output)
            answer = _answer_for_direct_tool(
                "add_to_cart",
                direct_add_arguments,
                execution_output,
                execution.outcome,
                state,
            )
            record = ToolCallRecord(
                name="add_to_cart",
                arguments=direct_add_arguments,
                outcome=execution.outcome,
                result_message=execution_output.get("error") if execution.outcome == "error" else None,
            )
            if self._memory is not None:
                await self._memory.append_turn(session_id, access_token, message, answer)
            if self._state_store is not None:
                state.turn_count += 1
                await self._state_store.save(session_id, access_token, state)
            return ChatResponse(
                answer=answer,
                tool_calls=[record],
                confirmation=execution.confirmation,
                data=execution_output.get("data"),
                reference=ReferenceResolution(
                    type="product",
                    value=str(direct_add_arguments["product_id"]),
                ),
            )

        # 批量操作使用当前业务数据，不能依赖上一轮购物车快照。
        if requests_cart_quantity_change(message) and (requests_all_cart_quantity_change(message) or re.search(r"增加|减少|减掉", message)):
            cart_result = await self._registry.execute("get_cart", {}, session_id=session_id, access_token=access_token)
            if cart_result.outcome != "success":
                return ChatResponse(answer=customer_error_reply(cart_result.output.get("error")),
                    tool_calls=[ToolCallRecord(name="get_cart", arguments={}, outcome=cart_result.outcome)])
            current_items = cart_result.output.get("data")
            if not isinstance(current_items, list):
                return ChatResponse(answer="暂时没能获取购物车商品，请稍后重试。")
            state.record_cart_items(current_items)
            if not current_items:
                if self._state_store is not None:
                    await self._state_store.save(session_id, access_token, state)
                return ChatResponse(answer="您的购物车目前是空的，没有需要修改数量的商品。", data=[])
        try:
            direct_update_arguments = _direct_update_cart_arguments(message, state)
        except ValueError as exc:
            return ChatResponse(answer=str(exc))
        if direct_update_arguments is not None:
            direct_update_name = "update_cart_items" if "items" in direct_update_arguments else "update_cart"
            execution = await self._registry.execute(
                direct_update_name,
                direct_update_arguments,
                session_id=session_id,
                access_token=access_token,
            )
            execution_output = _post_process_tool_output(
                direct_update_name, execution.output, message
            )
            if execution.confirmation is not None:
                state.remember_confirmation(
                    execution.confirmation.token,
                    execution.confirmation.action,
                    execution.confirmation.arguments,
                )
            if execution.outcome == "success":
                update_state_from_tool(state, direct_update_name, direct_update_arguments, execution_output)
            answer = _answer_for_direct_tool(
                direct_update_name,
                direct_update_arguments,
                execution_output,
                execution.outcome,
                state,
            )
            record = ToolCallRecord(
                name=direct_update_name,
                arguments=direct_update_arguments,
                outcome=execution.outcome,
                result_message=execution_output.get("error") if execution.outcome == "error" else None,
            )
            if self._memory is not None:
                await self._memory.append_turn(session_id, access_token, message, answer)
            if self._state_store is not None:
                state.turn_count += 1
                await self._state_store.save(session_id, access_token, state)
            return ChatResponse(
                answer=answer,
                tool_calls=[record],
                confirmation=execution.confirmation,
                data=execution_output.get("data"),
            )

        if requests_cart_quantity_change(message):
            answer = cart_clarification_reply(message, state)
            if self._memory is not None:
                await self._memory.append_turn(session_id, access_token, message, answer)
            if self._state_store is not None:
                await self._state_store.save(session_id, access_token, state)
            return ChatResponse(answer=answer)

        for _ in range(self._max_tool_rounds):
            try:
                response = await self._create_model_response(
                    instructions=system_instructions,
                    input_items=input_items,
                )
            except asyncio.TimeoutError:
                raise RuntimeError("LLM request timed out")
            function_calls = [
                item for item in response.output if item.type == "function_call"
            ]
            if not function_calls:
                if (
                    not forced_tool_retry
                    and _should_retry_for_missing_tool_call(message, records)
                ):
                    forced_tool_retry = True
                    input_items.append(
                        {
                            "role": "user",
                            "content": _missing_tool_retry_message(message),
                        }
                    )
                    continue
                answer = response.output_text or "我无法生成回复。"
                if records and records[-1].outcome in {"error", "clarification_needed"}:
                    answer = customer_error_reply(records[-1].result_message)
                elif pending_confirmation is not None:
                    answer = confirmation_reply(pending_confirmation.description)
                elif records and records[-1].name in {"add_to_cart", "update_cart", "update_cart_items", "remove_from_cart"} and records[-1].outcome == "success":
                    answer = _answer_for_direct_tool(records[-1].name, records[-1].arguments, execution_output, "success", state)
                elif records and records[-1].name == "get_product_detail" and records[-1].outcome == "success":
                    product = execution_output.get("data")
                    if isinstance(product, dict):
                        answer = f"商品详情：{product.get('name') or '商品名称待确认'}。"
                        if product.get("price") is not None:
                            answer += f"价格 ¥{product['price']}。"
                        if product.get("stock") is not None:
                            answer += f"库存 {product['stock']} 件。"


                if records and records[-1].outcome == "success" and pending_confirmation is None:
                    verified_data = execution_output.get("data")
                    if records[-1].name == "search_products":
                        count = len(_normalize_products(verified_data))
                        answer = (f"已查询到 {count} 项商品，请查看商品卡片中的价格和库存。"
                                  if count else "暂时没有找到符合条件的商品，您可以调整关键词或筛选条件再试试。")
                    elif records[-1].name == "get_cart":
                        count = len(verified_data) if isinstance(verified_data, list) else 0
                        answer = f"购物车中有 {count} 项商品。" if count else "您的购物车目前是空的。"
                    elif records[-1].name == "get_order_detail" and isinstance(verified_data, dict):
                        answer = f"已查询订单 {verified_data.get('orderNo') or records[-1].arguments.get('order_id')} 的详情，请查看订单卡片。"
                if forced_tool_retry and _should_retry_for_missing_tool_call(message, records):
                    answer = "这次没能获取到相关信息，请稍后重试。"
                if (
                    records
                    and records[-1].name == "get_my_orders"
                    and records[-1].outcome == "success"
                    and pending_confirmation is None
                    and not _contains_any(message.lower(), "退款", "退货", "售后", "refund", "return")
                ):
                    answer = _customer_order_list_answer(last_data)
                if self._memory is not None:
                    await self._memory.append_turn(
                        session_id, access_token, message, answer
                    )
                if self._state_store is not None:
                    state.turn_count += 1
                    await self._state_store.save(session_id, access_token, state)
                reference = _detect_reference(
                    message, records, pre_chat_order_id, pre_chat_product_keyword
                )
                return ChatResponse(
                    answer=answer,
                    tool_calls=records,
                    confirmation=pending_confirmation,
                    data=last_data,
                    reference=reference,
                )

            input_items.extend(response.output)
            for call in function_calls:
                try:
                    arguments = json.loads(call.arguments)
                except json.JSONDecodeError as exc:
                    # B3-1: JSON 解析失败不执行工具，把具体错误和原始参数反馈给 LLM，
                    # 让它在下一轮重新输出合法 JSON（最多重试 max_tool_rounds 次）
                    arguments = {}
                    execution_output = {
                        "ok": False,
                        "error": f"工具参数不是合法 JSON：{exc.msg}（位置 {exc.pos}）。请严格按 JSON 格式重新输出工具调用参数，不要包含多余文本或注释。",
                        "raw_arguments": call.arguments[:500],
                    }
                    outcome = "error"
                else:
                    if call.name == "search_knowledge_base":
                        # 意图路由（分库隔离）：服务端根据用户消息决定检索规则库还是
                        # 商品库，覆盖 LLM 传入的 kb 参数，防止跨库检索噪声
                        arguments["kb"] = route_knowledge_base(message)
                    guard_error = _guard_tool_call(call.name, arguments, message, state)
                    if guard_error:
                        execution_output = {"ok": False, "error": guard_error}
                        outcome = "error"
                    else:
                        missing = _check_missing_params(call.name, arguments)
                        if missing:
                            inferred = _infer_from_state(call.name, arguments, state, missing, message)
                            still_missing = [m for m in missing if inferred.get(m) is None]
                            if still_missing:
                                clarification = _generate_clarification(
                                    call.name, missing, arguments, state
                                )
                                execution_output = {
                                    "ok": False,
                                    "error": clarification,
                                    "clarification": True,
                                }
                                outcome = "clarification_needed"
                            else:
                                arguments = inferred
                                arguments = _normalize_tool_arguments(
                                    call.name, arguments, message, state
                                )
                                execution = await self._registry.execute(
                                    call.name,
                                    arguments,
                                    session_id=session_id,
                                    access_token=access_token,
                                )
                                execution_output = _post_process_tool_output(
                                    call.name, execution.output, message
                                )
                                outcome = execution.outcome
                                if execution_output.get("data") is not None:
                                    last_data = execution_output["data"]
                                if execution.confirmation is not None:
                                    pending_confirmation = execution.confirmation
                                    if self._state_store is not None:
                                        state.remember_confirmation(
                                            execution.confirmation.token,
                                            execution.confirmation.action,
                                            execution.confirmation.arguments,
                                        )
                                if self._state_store is not None and outcome == "success":
                                    update_state_from_tool(state, call.name, arguments, execution_output)
                        else:
                            arguments = _normalize_tool_arguments(
                                call.name, arguments, message, state
                            )
                            execution = await self._registry.execute(
                                call.name,
                                arguments,
                                session_id=session_id,
                                access_token=access_token,
                            )
                            execution_output = _post_process_tool_output(
                                call.name, execution.output, message
                            )
                            outcome = execution.outcome
                            if execution_output.get("data") is not None:
                                last_data = execution_output["data"]
                            if execution.confirmation is not None:
                                pending_confirmation = execution.confirmation
                                if self._state_store is not None:
                                    state.remember_confirmation(
                                        execution.confirmation.token,
                                        execution.confirmation.action,
                                        execution.confirmation.arguments,
                                    )
                            if self._state_store is not None and outcome == "success":
                                update_state_from_tool(state, call.name, arguments, execution_output)

                result_message = execution_output.get("error") if outcome in ("error", "clarification_needed") else None
                records.append(
                    ToolCallRecord(
                        name=call.name,
                        arguments=arguments,
                        outcome=outcome,
                        result_message=result_message,
                    )
                )
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(execution_output, ensure_ascii=False),
                    }
                )
                if execution_output.get("result_unknown"):
                    # 结果待核实立即结束本轮，防止模型再次调用写工具。
                    answer = customer_error_reply(execution_output.get("error"))
                    if self._memory is not None:
                        await self._memory.append_turn(session_id, access_token, message, answer)
                    if self._state_store is not None:
                        state.turn_count += 1
                        await self._state_store.save(session_id, access_token, state)
                    return ChatResponse(answer=answer, tool_calls=records, data=last_data)

        answer = "该请求需要过多的工具调用步骤，请尝试更简单的请求。"
        if self._memory is not None:
            await self._memory.append_turn(session_id, access_token, message, answer)
        if self._state_store is not None:
            state.turn_count += 1
            await self._state_store.save(session_id, access_token, state)
        reference = _detect_reference(
            message, records, pre_chat_order_id, pre_chat_product_keyword
        )
        return ChatResponse(
            answer=answer,
            tool_calls=records,
            confirmation=pending_confirmation,
            data=last_data,
            reference=reference,
        )
