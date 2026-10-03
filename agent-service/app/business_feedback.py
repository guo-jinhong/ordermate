"""用业务回执生成客户文案，区分本次增量与当前累计数量。"""
from decimal import Decimal, InvalidOperation
import re


REFUND_UNAVAILABLE = "目前暂不支持在这里直接申请退货退款，需要联系人工售后处理。我可以先帮您查询订单状态或了解售后规则。"


def confirmation_reply(description: str) -> str:
    """确认阶段只描述待处理事项，不暗示操作已完成。"""
    action = description.strip().rstrip('。.!！')
    return f"请确认是否要{action}。您确认后，我再为您处理。"


def customer_error_reply(error: str | None) -> str:
    """保留内部诊断记录，客户回复使用可理解的原因和下一步。"""
    reason = (error or '').strip()
    # 库存字段保留给业务校验，面向消费者只说明可购买数量与下一步。
    if '库存' in reason or 'stock' in reason.lower():
        match = re.search(r'当前库存(?:为|[:：])?\s*(\d+)\s*件', reason)
        if match:
            available = int(match.group(1))
            if available == 0:
                return '这件商品暂时缺货，可以看看其他商品，或稍后再来。'
            return f'这件商品目前可供购买 {available} 件，请减少数量后再试。'
        if '无法获取' in reason:
            return '暂时无法确认这件商品是否可购买，请稍后再试。'
        return '您选择的数量暂时无法满足，请减少数量后再试，或看看其他商品。'
    if '无法唯一确认' in reason:
        return '您指的是哪件商品？请告诉我商品名称，或从对应的商品卡片操作。'
    if '详情编号与请求编号不一致' in reason:
        subject = '订单' if '订单' in reason else '商品'
        return f'{subject}信息暂时无法确认，本次未操作。请重新查看{subject}后再试。'
    if '工具参数' in reason or '工具数量' in reason or '工具订单编号' in reason:
        return '这次操作的信息暂时无法确认，本次未操作。请从对应的商品或订单卡片重新操作。'
    if '没有明确要求取消订单' in reason:
        return '您的订单没有取消。如果需要取消，请告诉我要取消哪笔订单。'
    if not reason or '工具执行失败' in reason:
        return '这次操作没有完成，请稍后重试。'
    return reason.rstrip('。.!！') + '。'


def cart_add_reply(arguments: dict, output: dict, fallback_name: str | None = None) -> str:
    display = output.get('display') or {}
    name = display.get('product_name') or fallback_name or '该商品'
    added = display.get('added_quantity', arguments.get('quantity', 1))
    total = display.get('cart_quantity')
    if total is None:
        return f"已将「{name}」加入购物车，本次加入 {added} 件。购物车总数量暂时无法更新，请查看购物车确认，暂时不要重复添加。"
    if total > added:
        answer = f"又为您加入了 {added} 件「{name}」，购物车中这件商品现在共有 {total} 件。"
    else:
        answer = f"已将「{name}」加入购物车，本次加入 {added} 件，购物车中这件商品现在共有 {total} 件。"
    subtotal = display.get('cart_subtotal')
    if subtotal is not None:
        try:
            amount = f"{Decimal(str(subtotal)):,.2f}"
            if amount.endswith('.00'):
                amount = amount[:-3]
            answer += f" 小计 ¥{amount}。"
        except (InvalidOperation, ValueError):
            pass
    return answer


def product_purchase_copy(product: dict) -> str:
    """由真实可用数量生成购买提示，不编造固定限购政策。"""
    if product.get('status') not in (None, '', 1, '1'):
        return '暂不可购买'
    try:
        available = Decimal(str(product.get('stock')))
        if not available.is_finite() or available < 0 or available != available.to_integral_value():
            return '购买状态待确认'
    except (InvalidOperation, ValueError):
        return '购买状态待确认'
    if available == 0:
        return '暂时缺货'
    return '可购买'


def abandoned_action_reply(action: str) -> str:
    if action == 'cancel_order':
        return '本次未操作，您的订单未取消。'
    if action == 'create_order':
        return '本次未下单。'
    if action == 'pay_order':
        return '本次未支付，订单保持不变。'
    if action in {'clear_cart', 'remove_from_cart', 'update_cart', 'update_cart_items'}:
        return '本次未操作，购物车保持不变。'
    return '本次未操作，购物车和订单保持不变。'
