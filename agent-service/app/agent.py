from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Any

from app.conversation_memory import ConversationMemoryStore
from app.conversation_state import ConversationState, ConversationStateStore
from app.product_terms import translate_product_keyword
from app.prompts import SYSTEM_PROMPT
from app.schemas import ChatResponse, ReferenceResolution, ToolCallRecord
from app.tools.definitions import TOOLS
from app.tools.registry import ToolRegistry
from app.security_guard import is_suspicious_instruction


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
        if keyword:
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
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                order_id = first.get("id")
                order_no = first.get("orderNo")
                if order_id is not None:
                    state.record_order(int(order_id), str(order_no) if order_no else None)

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
            state.record_product(int(product_id))
        state.record_cart_view()

    elif tool_name in {"update_cart", "remove_from_cart", "clear_cart"}:
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
        if _contains_any(lowered, "购物车", "cart"):
            return None
        return "只有用户询问购物车时才会读取购物车。"

    if name == "add_to_cart":
        if _contains_any(lowered, "加购物车", "加入购物车", "放购物车", "添加购物车", "add to cart", "cart"):
            return None
        return "只有用户明确要求加入购物车时才会修改购物车。"

    if name == "update_cart":
        if _contains_any(lowered, "修改购物车", "购物车数量", "改数量", "update cart"):
            return None
        return "只有用户明确要求修改购物车数量时才会修改购物车。"

    if name == "remove_from_cart":
        if _contains_any(lowered, "删除购物车", "移除购物车", "删掉购物车", "remove cart"):
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
        if _contains_any(lowered, "退款", "售后", "规则", "政策", "参数", "配置", "保修", "policy", "refund"):
            return None
        return "只有用户询问规则、政策或参数时才会检索知识库。"

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
        "product_id": "商品 ID",
    },
    "get_cart": {},
    "add_to_cart": {
        "product_id": "商品 ID",
        "quantity": "加入购物车数量",
    },
    "update_cart": {
        "cart_id": "购物车项 ID",
        "quantity": "新的商品数量",
    },
    "remove_from_cart": {
        "cart_id": "购物车项 ID",
    },
    "clear_cart": {},
    "get_my_orders": {},
    "get_order_detail": {
        "order_id": "订单 ID",
    },
    "cancel_order": {
        "order_id": "订单 ID",
    },
    "create_order": {
        "product_id": "商品 ID",
        "quantity": "下单数量",
    },
    "pay_order": {
        "order_id": "订单 ID",
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


def _direct_add_to_cart_arguments(message: str, state: ConversationState) -> dict[str, Any] | None:
    lowered = message.lower()
    if not _contains_any(lowered, "加购物车", "加入购物车", "放购物车", "添加购物车", "add to cart", "cart"):
        return None
    product_id = state.resolve_product_id(message, None)
    if product_id is None:
        return None
    return {
        "product_id": product_id,
        "quantity": _extract_quantity(message) or 1,
    }


def _direct_update_cart_arguments(message: str, state: ConversationState) -> dict[str, Any] | None:
    lowered = message.lower()
    if not _contains_any(lowered, "修改购物车", "购物车数量", "改数量", "数量改", "改成", "调整", "update cart"):
        return None
    quantity = _extract_quantity(message)
    if quantity is None:
        return None
    if _contains_any(lowered, "都", "全部", "所有", "两件", "两个", "all", "both"):
        items = [
            {
                "cart_id": int(item["cartId"]),
                "quantity": quantity,
            }
            for item in state.cart_items
            if item.get("cartId") is not None
        ]
        if items:
            return {"items": items, "quantity": quantity}
    cart_id = state.resolve_cart_id(message, None)
    if cart_id is None:
        return None
    return {"cart_id": cart_id, "quantity": quantity}


def _answer_for_direct_tool(
    name: str,
    arguments: dict[str, Any],
    execution_output: dict[str, Any],
    outcome: str,
    state: ConversationState,
) -> str:
    if name == "add_to_cart":
        product_name = state.product_name_for_id(arguments.get("product_id")) or f"商品 #{arguments.get('product_id')}"
        quantity = arguments.get("quantity") or 1
        if outcome == "success":
            return f"已把 {product_name} x {quantity} 加入购物车。"
        return f"加入购物车没有成功：{execution_output.get('error', '业务系统返回错误')}。"
    if name == "update_cart":
        quantity = arguments.get("quantity")
        if outcome == "confirmation_required":
            return f"已准备把购物车项 #{arguments.get('cart_id')} 的数量改为 {quantity}，请点击确认按钮，或直接回复“确认”。"
        if outcome == "success":
            return f"购物车数量已修改为 {quantity}。"
        return f"修改购物车数量没有成功：{execution_output.get('error', '业务系统返回错误')}。"
    if name == "update_cart_items":
        quantity = arguments.get("quantity")
        items = arguments.get("items") or []
        if outcome == "confirmation_required":
            return f"已准备把购物车中 {len(items)} 个商品的数量都改为 {quantity} 件，请点击确认按钮，或直接回复“确认”。"
        if outcome == "success":
            return f"购物车中 {len(items)} 个商品的数量已修改为 {quantity} 件。"
        return f"批量修改购物车数量没有成功：{execution_output.get('error', '业务系统返回错误')}。"
    if outcome == "success":
        return "操作已完成。"
    return execution_output.get("error") or "操作没有成功。"


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
                    value = state.last_order_id
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


_CHINESE_NUMBERS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _extract_quantity(message: str) -> int | None:
    arabic_match = re.search(r"(\d{1,2})\s*(?:台|个|件|部|只|双|份|条|款)", message)
    if arabic_match:
        value = int(arabic_match.group(1))
        return value if value > 0 else None
    chinese_match = re.search(r"([一二两三四五六七八九十])\s*(?:台|个|件|部|只|双|份|条|款)", message)
    if chinese_match:
        return _CHINESE_NUMBERS.get(chinese_match.group(1))
    return None


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
    ) -> None:
        self._model_client = model_client
        self._registry = registry
        self._model = model
        self._max_tool_rounds = max_tool_rounds
        self._memory = memory
        self._state_store = state_store
        self._confirmed_action_executor = confirmed_action_executor

    async def _create_model_response(
        self,
        *,
        instructions: str,
        input_items: list[Any],
    ) -> Any:
        if _model_uses_chat_completions(self._model) and hasattr(self._model_client, "chat"):
            completion = await self._model_client.chat.completions.create(
                model=self._model,
                messages=_chat_messages_from_responses_input(instructions, input_items),
                tools=_chat_tools_from_responses_tools(TOOLS),
                extra_body={"thinking": {"type": "disabled"}},
            )
            return _responses_shape_from_chat_completion(completion)

        return await self._model_client.responses.create(
            model=self._model,
            instructions=instructions,
            tools=TOOLS,
            input=input_items,
        )

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

        if (
            _is_confirmation_message(message)
            and state.pending_confirmation_token
            and state.pending_confirmation_action
            and state.pending_confirmation_arguments is not None
            and self._confirmed_action_executor is not None
        ):
            try:
                data, answer = await self._confirmed_action_executor(
                    state.pending_confirmation_action,
                    state.pending_confirmation_arguments,
                    access_token,
                )
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
                return ChatResponse(answer=f"确认执行失败：{exc}", tool_calls=[])

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

        direct_update_arguments = _direct_update_cart_arguments(message, state)
        if direct_update_arguments is not None:
            direct_update_name = "update_cart_items" if "items" in direct_update_arguments else "update_cart"
            if direct_update_name == "update_cart":
                current_quantity = state.cart_quantity_for_id(direct_update_arguments["cart_id"])
                same_quantity = current_quantity == direct_update_arguments["quantity"]
            else:
                same_quantity = all(
                    state.cart_quantity_for_id(item["cart_id"]) == item["quantity"]
                    for item in direct_update_arguments["items"]
                )
            if same_quantity:
                answer = f"购物车里相关商品当前已经是 {direct_update_arguments['quantity']} 件，不需要重复修改。"
                if self._memory is not None:
                    await self._memory.append_turn(session_id, access_token, message, answer)
                if self._state_store is not None:
                    state.turn_count += 1
                    await self._state_store.save(session_id, access_token, state)
                return ChatResponse(answer=answer, tool_calls=[], data=None)
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

        for _ in range(self._max_tool_rounds):
            response = await self._create_model_response(
                instructions=system_instructions,
                input_items=input_items,
            )
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
                if forced_tool_retry and _should_retry_for_missing_tool_call(message, records):
                    answer = "我需要先查询业务系统，才能回答商品、价格、库存、购物车或订单相关问题。请换个更明确的问法再试一次。"
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
                except json.JSONDecodeError:
                    arguments = {}
                    execution_output = {
                        "ok": False,
                        "error": "模型提供了无效的工具参数。",
                    }
                    outcome = "error"
                else:
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
