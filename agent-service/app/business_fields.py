"""Live 与 Demo 共用业务数量解析，避免两种模式执行不同数量。"""
import re
from contextlib import contextmanager
from contextvars import ContextVar


def requests_cart_removal(message: str) -> bool:
    """删除意图与对象分别校验，避免依赖模型自报操作成功。"""
    if denies_mutation(message) or re.search(r'订单|库存|仓库|账号|地址|退货|退款', message):
        return False
    if re.search(r'怎么|如何|是否|能否|规则|流程|失败|没成功', message):
        return False
    return bool(re.search(r'移除|删除|删掉|删去|remove\b|delete\b', message, re.I))


def requests_cart_quantity_change(message: str) -> bool:
    if denies_mutation(message) or re.search(r'库存|仓库', message):
        return False
    return bool(re.search(r'修改购物车|购物车数量|改数量|数量改|改成|改为|调整|变成|变为|设为|设置为|增加|减少|减掉|update cart', message, re.I))


def requests_all_cart_quantity_change(message: str) -> bool:
    return requests_cart_quantity_change(message) and bool(re.search(r'都|全部|所有|\ball\b|\bboth\b', message, re.I))


def vague_cart_quantity_request(message: str) -> bool:
    return not denies_mutation(message) and bool(re.search(r'少买|买少|数量.{0,8}(?:少|多|大|小)一点|(?:增加|减少)(?:一些|一点)', message))


def complete_cart_clarification(message: str, state) -> str:
    pending = state.pending_cart_clarification
    if not pending:
        return message
    quantity = extract_quantity(message)
    quantity_only = bool(re.fullmatch(r'[\d零一二两三四五六七八九十百千万]+\s*(?:件|个|本|台)?[。！!\s]*', message))
    if quantity_only and quantity is None:
        quantity = extract_quantity(message.strip('。！! ') + '件')
    # 只有补充数量或明确商品+数量，才能延续上次修改；换话题即放弃旧澄清。
    cart_id = pending.get('cart_id') if quantity_only else state.resolve_cart_id(message, None)
    if quantity is not None and cart_id is not None and not re.search(r'搜索|推荐|查询|订单|加入|加购|清空|删除|取消|支付|下单|购买', message):
        state.pending_cart_clarification = None
        return f'将购物车项 {cart_id} 数量改为 {quantity} 件'
    state.pending_cart_clarification = None
    return message


def cart_clarification_reply(message: str, state) -> str:
    cart_id = state.resolve_cart_id(message, None)
    state.pending_cart_clarification = {'cart_id': cart_id}
    if cart_id is not None and extract_quantity(message) is None:
        name = state.cart_product_name_for_id(cart_id) or '这件商品'
        return f'您希望将「{name}」的数量改为几件？也可以明确说“减少1件”。'
    if extract_quantity(message) is None:
        return '您想调整购物车里的哪件商品，数量改为几件？'
    return '您指的是购物车里的哪件商品？请提供商品名称或从对应卡片操作。'


def cart_quantity_arguments(message: str, state) -> dict | None:
    """从实时购物车解析目标范围和绝对数量；无法可靠解析时先澄清。"""
    if not requests_cart_quantity_change(message):
        return None
    if re.search(r'一半|半件|百分之|\d\s*%|[一二三四五六七八九]成|倍', message):
        raise ValueError('请明确要改成几件或增加、减少几件，我不会根据比例猜测商品数量。')
    number = r'-?\d+(?:\.\d+)?|[零一二两三四五六七八九十百千万]+'
    changes = list(re.finditer(rf'(改成|改为|调整为|变成|变为|设置为|设为|增加|减少|减掉)\s*({number})', message))
    delta = next((m for m in changes if m.group(1) in {'增加', '减少', '减掉'}), None)
    if len(changes) > 1:
        raise ValueError('这句话包含多个数量要求，请分别说明每件商品要改成几件。')
    quantity = extract_quantity(f"{changes[0].group(2)}件") if changes else extract_quantity(message)
    if quantity is None:
        return None
    if quantity <= 0:
        raise ValueError('商品数量需要是正整数。如果想移除商品，请明确告诉我要删除哪件商品。')
    bulk = requests_all_cart_quantity_change(message)
    if bulk:
        # 筛选只在修改动作之前解析，避免把目标数量当成筛选阈值。
        scope = message[:changes[0].start()] if changes else re.split(r'数量(?:改|调整)', message)[0]
        threshold = re.search(rf'(超过|大于|少于|小于|至少|不少于|不超过|等于)\s*({number})\s*(?:件|个|本|台)?', scope)
        items = list(state.cart_items)
        if threshold:
            limit = extract_quantity(threshold.group(2) + '件')
            compare = {'超过': lambda n: n > limit, '大于': lambda n: n > limit,
                       '少于': lambda n: n < limit, '小于': lambda n: n < limit,
                       '至少': lambda n: n >= limit, '不少于': lambda n: n >= limit,
                       '不超过': lambda n: n <= limit, '等于': lambda n: n == limit}[threshold.group(1)]
            items = [item for item in items if compare(int(item['quantity']))]
            scope = scope[:threshold.start()] + scope[threshold.end():]
        # 剩余范围必须是明确的名称/类别，不能把无法理解的条件扩大成整个购物车。
        selector = re.sub(r'购物车|商品|数量|帮我|请|只|把|将|所有|全部|都|统一|一起|现在|对|里面|里的|中|里|的|[\s，,。]', '', scope)
        selector = re.sub(rf'^(?:{number})(?:件|种|个)$', '', selector).strip('「」“”"')
        if selector:
            # 当前目录包含英文名称，类别必须兼容其明确的英文词。
            aliases = {'耳机': ('耳机', 'headphones', 'earphones', 'earbuds'),
                       '手机': ('手机', 'smartphone'), '框架指南': ('框架指南', 'framework guide')}
            terms = aliases.get(selector, (selector.lower(),))
            items = [item for item in items if any(term in str(item.get('productName') or '').lower() for term in terms)]
            if not items:
                raise ValueError('没能确定您指定的购物车商品范围，请提供商品名称或更明确的筛选条件。')
    else:
        cart_id = state.resolve_cart_id(message, None)
        if cart_id is None:
            return None
        items = [item for item in state.cart_items if item.get('cartId') == cart_id]
        if not items:
            # 显式卡片编号仍交给业务接口核对是否存在。
            if delta:
                raise ValueError('没有查到这件商品的当前数量，请刷新购物车后再试。')
            return {'cart_id': cart_id, 'quantity': quantity}
    if not items:
        raise ValueError('购物车中没有符合这次筛选条件的商品，无需修改。')
    operations = []
    for item in items:
        target = quantity
        if delta:
            target = int(item['quantity']) + (quantity if delta.group(1) == '增加' else -quantity)
        if target <= 0:
            raise ValueError('减少后数量将不大于0。如果想移除商品，请明确说明删除。')
        operations.append({'cart_id': int(item['cartId']), 'quantity': target})
    if not bulk:
        return operations[0]
    targets = {item['quantity'] for item in operations}
    if len(targets) != 1:
        raise ValueError('这些商品的当前数量不同，请指定统一的目标数量，或分别调整商品数量。')
    return {'items': operations, 'quantity': operations[0]['quantity']}


def extract_quantity(message: str) -> int | None:
    # 商品名称中的“12件套”等是名称的一部分，不是购买数量。
    text = re.sub(r'[「“"]([^」”"]+)[」”"]', '', message)
    number = r"-?\d+(?:\.\d+)?|[零一二两三四五六七八九十百千万]+"
    matches = list(re.finditer(rf"(?<![\d.])({number})\s*(?:台|个|件|部|只|双|本|份|条|款|units?\b|items?\b)", text, re.I))
    # “两件商品都改成3件”里的两件是对象数，优先明确的目标数量。
    target = re.search(rf"(?:数量|quantity|qty|改成|改为|调整为|变成|变为|设为|设置为)\s*(?:改为|改成|为|到|至|[:：])?\s*({number})", text, re.I)
    raw = target.group(1) if target else matches[-1].group(1) if matches else None
    if raw is None:
        return None
    if re.fullmatch(r"-?\d+(?:\.\d+)?", raw):
        return int(raw) if '.' not in raw else 0
    digits = {ch: index for index, ch in enumerate('零一二三四五六七八九')}
    digits['两'] = 2
    total, digit = 0, 0
    for ch in raw:
        if ch in digits:
            digit = digits[ch]
        else:
            unit = {'十': 10, '百': 100, '千': 1000, '万': 10000}[ch]
            total += (digit or 1) * unit
            digit = 0
    return total + digit


def denies_mutation(message: str) -> bool:
    # 商品名称可能较长，否定删除不能因固定字符窗口而失效。
    if re.search(r"(?:不要|别|不用|不需要|勿|don't|do not)[^。！？;；\n]*(?:删除|移除|删掉|删去|remove\b|delete\b)", message, re.I):
        return True
    return bool(re.search(
        r"(?:不要|别|不用|不需要|不想|不必|勿|don't|do not).{0,16}"
        r"(?:加入购物车|加购物车|加购|下单|购买|支付|付款|取消|清空|删除|移除|删掉|删去|修改|调整|改成|改为|变成|变为|设为|add|buy|pay|cancel|clear|remove|update)",
        message, re.I,
    ))


def requests_refund(message: str) -> bool:
    if not re.search(r"退款|退货|refund|return", message, re.I):
        return False
    if re.search(r"规则|政策|条件|多久|怎么|如何|能否|是否|进度|状态|流程", message):
        return False
    return bool(re.search(r"申请|办理|发起|帮我|我要|我想|订单|order|^退款|^退货|^refund", message, re.I))


# 再次购买授权只来自本次用户消息，模型参数不能开启此开关。
_purchase_message = ContextVar("current_purchase_message", default="")
_repeat_purchase = ContextVar("explicit_repeat_purchase", default=False)


def requests_repeat_purchase(message: str) -> bool:
    if denies_mutation(message) or re.search(r'怎么|如何|是否|能否|规则|流程|如果|假如|例如|比如|之前|上次|说过|[？?]', message):
        return False
    text = re.sub(r'[「“\"]([^」”\"]+)[」”\"]', '', message)
    return bool(re.search(r'再(?:次)?(?:买|购买|下单)|重新(?:买|购买|下单)|再来一单|\bbuy again\b|\border again\b', text, re.I))


@contextmanager
def purchase_request(message: str):
    message_token = _purchase_message.set(message)
    token = _repeat_purchase.set(requests_repeat_purchase(message))
    try:
        yield
    finally:
        _repeat_purchase.reset(token)
        _purchase_message.reset(message_token)


def repeat_purchase_authorized() -> bool:
    return _repeat_purchase.get()


def mutation_is_consultation(message: str) -> bool:
    # 引号里的指令及引用往事不能当作本轮授权；保留引号外明确指令。
    text = re.sub(r'[「“\"]([^」”\"]+)[」”\"]', '', message)
    return bool(re.search(r'怎么|如何|规则|政策|流程|条件|如果|假如|例如|比如|是否|能否|(?:之前|上次).{0,5}(?:说过|问过|说的)|[？?]', text)) or (
        text != message and not re.search(r'取消|支付|付款|清空|删除|移除|修改|调整|下单|购买|买|加入购物车', text))


def current_mutation_is_consultation() -> bool:
    return mutation_is_consultation(_purchase_message.get())
