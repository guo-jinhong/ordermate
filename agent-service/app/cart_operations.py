"""普通购物车写操作共用执行与读回核验，确认旧请求也复用同一实现。"""
from app.clients.ecommerce_client import EcommerceApiError


async def execute_cart_mutation(ecommerce, action, arguments, access_token):
    if action == "update_cart_items" and any(item["quantity"] != arguments["quantity"] for item in arguments["items"]):
        raise ValueError("批量修改的各项数量与统一目标数量不一致，未执行修改。")
    unknown_receipt = False
    try:
        if action == "update_cart":
            await ecommerce.update_cart(arguments["cart_id"], arguments["quantity"], access_token)
        elif action == "update_cart_items":
            await ecommerce.update_cart_items(arguments["items"], access_token)
        elif action == "remove_from_cart":
            await ecommerce.remove_from_cart(arguments["cart_id"], access_token)
        else:
            raise ValueError("不支持的购物车操作。")
    except EcommerceApiError as exc:
        if not exc.result_unknown:
            raise
        unknown_receipt = True
        # 写回执丢失时只读核实目标状态，绝不重发写请求。

    try:
        cart = await ecommerce.get_cart(access_token)
    except EcommerceApiError as exc:
        raise EcommerceApiError("已发送购物车修改请求，但暂时无法核实结果，请刷新购物车确认，勿重复提交。", result_unknown=True) from exc
    if not isinstance(cart, list):
        raise EcommerceApiError("购物车返回异常，暂时无法核实修改结果，请刷新确认，勿重复提交。", result_unknown=True)
    by_id = {str(item.get("cartId", item.get("id"))): item for item in cart if isinstance(item, dict)}
    name = arguments.get("product_name") or "该商品"
    if action == "remove_from_cart":
        if str(arguments["cart_id"]) in by_id:
            if unknown_receipt:
                raise EcommerceApiError("本次移除结果暂时无法确认，请查询购物车核实，勿重复提交。", result_unknown=True)
            raise EcommerceApiError("移除未生效，该商品仍在购物车中，请刷新后重试。")
        message = f"已从购物车移除「{name}」。"
    else:
        targets = arguments["items"] if action == "update_cart_items" else [arguments]
        if any(str(item["cart_id"]) not in by_id or str(by_id[str(item["cart_id"])].get("quantity")) != str(item["quantity"]) for item in targets):
            raise EcommerceApiError("购物车数量修改结果未核对一致，请刷新购物车确认，勿重复提交。", result_unknown=True)
        if action == "update_cart_items":
            message = f"已将购物车中 {len(targets)} 种商品的数量都修改为 {arguments['quantity']} 件。"
        else:
            previous = arguments.get("previous_quantity")
            change = f"从 {previous} 件改为 {arguments['quantity']} 件" if previous is not None else f"改为 {arguments['quantity']} 件"
            message = f"已将「{name}」的购物车数量{change}。"
    return cart, message
