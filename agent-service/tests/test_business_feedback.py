from types import SimpleNamespace

import pytest

from app.agent import AgentService
from app.business_feedback import confirmation_reply, customer_error_reply
from app.business_fields import requests_refund
from app.clients.ecommerce_client import EcommerceApiError
from app.conversation_state import ConversationStateStore
from app.demo_agent import DemoAgentService
from app.tools.confirmation import ConfirmationStore
from app.tools.definitions import TOOLS
from app.tools.registry import ToolRegistry


class CartBusiness:
    def __init__(self, quantity=0, read_fails=False):
        self.quantity = quantity
        self.read_fails = read_fails
        self.adds = []

    async def get_product_detail(self, product_id):
        return {'id': product_id, 'name': 'Spring Framework Guide', 'stock': 80, 'price': 99}

    async def add_to_cart(self, product_id, quantity, access_token):
        self.adds.append((product_id, quantity))
        self.quantity += quantity

    async def get_cart(self, access_token):
        if self.read_fails:
            raise EcommerceApiError('verification timeout')
        return [{'cartId': 71, 'productId': 8, 'productName': 'Spring Framework Guide', 'price': 99, 'quantity': self.quantity},
                {'cartId': 72, 'productId': 2, 'productName': 'Smartphone X', 'price': 2999, 'quantity': 1}]

    async def update_cart(self, cart_id, quantity, access_token):
        assert cart_id == 71
        self.quantity = quantity


def service(mode, business, store=None):
    registry = ToolRegistry(business, ConfirmationStore())
    return DemoAgentService(registry, state_store=store) if mode == 'demo' else AgentService(SimpleNamespace(), registry, model='test', state_store=store)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['live', 'demo'])
async def test_repeated_add_reports_added_quantity_and_verified_cart_total(mode):
    business = CartBusiness()
    store = ConversationStateStore()
    agent = service(mode, business, store)
    first = await agent.chat('将商品 8 加入购物车，数量 1 件', session_id='repeat', access_token='jwt')
    second = await agent.chat('将商品 8 加入购物车，数量 1 件', session_id='repeat', access_token='jwt')
    assert '本次加入 1 件' in first.answer
    assert '现在共有 1 件' in first.answer
    assert '小计 ¥99' in first.answer
    assert '又为您加入了 1 件' in second.answer
    assert '现在共有 2 件' in second.answer
    assert '小计 ¥198' in second.answer
    assert first.answer != second.answer
    assert business.adds == [(8, 1), (8, 1)]
    state = await store.get('repeat', 'jwt')
    assert state.cart_quantity_for_id(71) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['live', 'demo'])
async def test_existing_cart_in_new_conversation_uses_server_total(mode):
    result = await service(mode, CartBusiness(quantity=3)).chat('将商品 8 加入购物车，数量 2 件', session_id='new-session', access_token='jwt')
    assert '又为您加入了 2 件' in result.answer
    assert '现在共有 5 件' in result.answer
    assert '小计 ¥495' in result.answer


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['live', 'demo'])
async def test_post_write_read_failure_does_not_retry_successful_add(mode):
    business = CartBusiness(read_fails=True)
    result = await service(mode, business).chat('将商品 8 加入购物车，数量 1 件', session_id='read-failed', access_token='jwt')
    assert business.adds == [(8, 1)]
    assert business.quantity == 1
    assert result.tool_calls[0].outcome == 'success'
    assert '本次加入 1 件' in result.answer
    assert '购物车总数量暂时无法更新' in result.answer
    assert '现在共有' not in result.answer


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['live', 'demo'])
async def test_repeated_quantity_update_checks_fresh_server_data(mode):
    business = CartBusiness(quantity=2)
    store = ConversationStateStore()
    state = await store.get('same', 'jwt')
    state.record_cart_items([{'cartId': 71, 'productId': 8, 'productName': 'Spring Framework Guide', 'quantity': 1}])
    result = await service(mode, business, store).chat('将购物车项 71 的数量改为 2 件', session_id='same', access_token='jwt')
    assert result.confirmation is None
    assert '已经是 2 件' in result.answer
    assert '无需重复修改' in result.answer
    assert business.quantity == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['live', 'demo'])
async def test_cached_same_quantity_does_not_hide_external_cart_changes(mode):
    business = CartBusiness(quantity=2)
    store = ConversationStateStore()
    state = await store.get('stale', 'jwt')
    state.record_cart_items([{'cartId': 71, 'productId': 8, 'productName': 'Spring Framework Guide', 'quantity': 1}])
    result = await service(mode, business, store).chat('将购物车项 71 的数量改为 1 件', session_id='stale', access_token='jwt')
    assert result.confirmation is None
    assert '从 2 件改为 1 件' in result.answer
    assert business.quantity == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['live', 'demo'])
async def test_refund_request_does_not_fabricate_supported_submission(mode):
    result = await service(mode, CartBusiness()).chat('帮我申请订单 100 退款', session_id='refund', access_token='jwt')
    assert result.confirmation is None
    assert result.tool_calls == []
    assert '暂不支持在这里直接申请' in result.answer
    assert '已提交' not in result.answer
    assert '已退款' not in result.answer


def test_refund_policy_query_remains_a_knowledge_question():
    assert not requests_refund('退货退款有哪些规则和条件？')
    assert not requests_refund('订单退款进度怎么查询？')
    assert 'refund_order' not in {tool['name'] for tool in TOOLS}


@pytest.mark.parametrize('description', ['清空购物车', '取消订单 ORD-100。', '将「框架指南」的购物车数量从 1 件改为 2 件'])
def test_confirmation_copy_keeps_action_pending(description):
    answer = confirmation_reply(description)
    assert description.rstrip('。') in answer
    assert '您确认后' in answer
    assert '已完成' not in answer
    assert '。。' not in answer


@pytest.mark.parametrize('error', ['工具参数与本轮指定的商品或购物车项不一致，请重新核对编号。', '工具数量与本轮指定数量不一致，请重新核对。'])
def test_internal_alignment_error_has_customer_next_step(error):
    answer = customer_error_reply(error)
    assert '本次未操作' in answer
    assert '卡片' in answer
    assert '工具' not in answer
    assert '本轮' not in answer


def test_customer_error_preserves_business_reason_without_duplicate_punctuation():
    assert customer_error_reply('库存不足。') == '您选择的数量暂时无法满足，请减少数量后再试，或看看其他商品。'


@pytest.mark.asyncio
async def test_demo_empty_cart_and_orders_describe_empty_state():
    class EmptyBusiness:
        async def get_cart(self, access_token):
            return []

        async def get_my_orders(self, access_token):
            return []

    agent = service('demo', EmptyBusiness())
    cart = await agent.chat('查看购物车', session_id='empty-copy', access_token='jwt')
    orders = await agent.chat('查看我的订单', session_id='empty-copy', access_token='jwt')
    assert '购物车目前是空的' in cart.answer
    assert '还没有订单' in orders.answer
    assert '暂无数据' not in cart.answer + orders.answer


class BulkCartBusiness:
    def __init__(self, quantities=(1, 1, 3)):
        self.cart = [dict(cartId=71 + i, productId=8 + i, productName=name, quantity=quantity)
                     for i, (name, quantity) in enumerate(zip(['框架指南', '手机', '耳机'], quantities))]
        self.updates = []

    async def get_cart(self, access_token):
        return [dict(item) for item in self.cart]

    async def update_cart(self, cart_id, quantity, access_token):
        self.updates.append((cart_id, quantity))
        next(item for item in self.cart if item['cartId'] == cart_id)['quantity'] = quantity
        return None

    async def update_cart_items(self, items, access_token):
        for item in items:
            await self.update_cart(item['cart_id'], item['quantity'], access_token)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['live', 'demo'])
@pytest.mark.parametrize('message', [
    '帮我把所有商品数量变成1件', '所有商品都改为一件', '把购物车里的商品全部设为1',
    '全部商品数量设置为1件', '所有商品变为一件',
])
async def test_bulk_quantity_phrases_prepare_and_execute_actual_updates(mode, message):
    from app.main import _execute_confirmed_action

    business = BulkCartBusiness()
    store = ConversationStateStore()
    # 缓存故意缺一件且数量过期，执行对象必须来自实时购物车。
    state = await store.get('bulk-natural', 'jwt')
    state.record_cart_items([dict(cartId=71, productId=8, productName='框架指南', quantity=9)])
    agent = service(mode, business, store)
    response = await agent.chat(message, session_id='bulk-natural', access_token='jwt')
    assert response.confirmation is None
    assert response.tool_calls[-1].outcome == 'success'
    items = response.tool_calls[-1].arguments['items']
    assert {item['cart_id'] for item in items} == {71, 72, 73}
    assert all(item['quantity'] == 1 for item in items)
    assert [item['quantity'] for item in business.cart] == [1, 1, 1]
    assert business.updates == [(71, 1), (72, 1), (73, 1)]
    assert '3 种商品' in response.answer



@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['live', 'demo'])
@pytest.mark.parametrize('quantities', [(), (1, 1, 1)])
async def test_bulk_empty_or_already_target_quantity_needs_no_confirmation(mode, quantities):
    business = BulkCartBusiness(quantities)
    result = await service(mode, business).chat('所有商品数量变成1件', session_id='bulk-empty', access_token='jwt')
    assert result.confirmation is None
    assert '没有需要修改' in result.answer or '无需重复修改' in result.answer
    assert business.updates == []


def test_bulk_tool_is_exposed_and_inventory_and_denials_are_not_cart_updates():
    from app.business_fields import requests_all_cart_quantity_change
    assert 'update_cart_items' in {tool['name'] for tool in TOOLS}
    assert not requests_all_cart_quantity_change('不要把所有商品变成1件')
    assert not requests_all_cart_quantity_change('把所有商品库存改为1件')


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['live', 'demo'])
@pytest.mark.parametrize('message,expected', [
    ('把框架指南的数量减少1件', {71: 2}),
    ('把框架指南的数量调整一下，减少1件', {71: 2}),
    ('把框架指南的数量增加两件', {71: 5}),
    ('只把购物车里所有耳机改为1件', {73: 1}),
    ('把所有数量超过2件的商品改为2件', {71: 2}),
    ('把所有数量不少于2件的商品改为1件', {71: 1, 73: 1}),
    ('把所有数量不超过1件的商品改为2件', {72: 2}),
])
async def test_quantity_delta_and_scoped_batch_use_exact_targets(mode, message, expected):
    business = BulkCartBusiness((3, 1, 2))
    result = await service(mode, business).chat(message, session_id='scoped', access_token='jwt')
    assert result.confirmation is None
    args = result.tool_calls[-1].arguments
    operations = args.get('items') or [args]
    assert {item['cart_id']: item['quantity'] for item in operations} == expected
    assert dict(business.updates) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['live', 'demo'])
@pytest.mark.parametrize('message', [
    '把所有价格100元以内的商品改为1件', '把所有除手机外的商品改为1件',
    '把所有数量超过9件的商品改为1件', '把框架指南的数量减少3件',
])
async def test_unresolved_scope_and_nonpositive_delta_cannot_prepare_modification(mode, message):
    result = await service(mode, BulkCartBusiness((3, 1, 2))).chat(message, session_id='unclear', access_token='jwt')
    assert result.confirmation is None
    assert not result.tool_calls


@pytest.mark.asyncio
@pytest.mark.parametrize('expired', [True, False])
async def test_expired_or_consumed_token_cannot_execute_text_confirmation(expired):
    from app.tools.confirmation import fingerprint_access_token

    business = BulkCartBusiness((3, 1, 2))
    confirmations = ConfirmationStore(ttl_seconds=0 if expired else 60)
    registry = ToolRegistry(business, confirmations)
    store = ConversationStateStore()
    executed = []
    async def executor(*args):
        executed.append(args)
        return {}, 'unexpected execution'
    agent = AgentService(SimpleNamespace(), registry, model='test', state_store=store, confirmed_action_executor=executor)
    prepared = await agent.chat('清空购物车', session_id='token-check', access_token='jwt')
    if not expired:
        await confirmations.consume(prepared.confirmation.token, 'token-check', fingerprint_access_token('jwt'))
    response = await agent.chat('确认', session_id='token-check', access_token='jwt')
    assert '失效' in response.answer
    assert executed == []
    assert (await store.get('token-check', 'jwt')).pending_confirmation_token is None


@pytest.mark.asyncio
async def test_text_rejection_revokes_pending_token():
    from app.tools.confirmation import fingerprint_access_token
    store = ConversationStateStore()
    confirmations = ConfirmationStore()
    registry = ToolRegistry(BulkCartBusiness(), confirmations)
    agent = AgentService(SimpleNamespace(), registry, model='test', state_store=store)
    prepared = await agent.chat('清空购物车', session_id='reject', access_token='jwt')
    result = await agent.chat('不改了', session_id='reject', access_token='jwt')
    assert '本次未操作' in result.answer
    assert (await store.get('reject', 'jwt')).pending_confirmation_token is None
    assert await confirmations.consume(prepared.confirmation.token, 'reject', fingerprint_access_token('jwt')) is None


def test_scoped_tool_guard_rejects_model_expanding_scope_or_wrong_delta():
    from app.agent import _guard_tool_call
    from app.conversation_state import ConversationState
    state = ConversationState()
    state.record_cart_items(BulkCartBusiness((3, 1, 2)).cart)
    assert _guard_tool_call('update_cart_items', {'items': [{'cart_id': 71, 'quantity': 1}, {'cart_id': 73, 'quantity': 1}], 'quantity': 1},
        '只把所有耳机改为1件', state)
    assert _guard_tool_call('update_cart', {'cart_id': 71, 'quantity': 1}, '把框架指南减少1件', state)


def test_chinese_category_scope_matches_english_catalog_names_without_expansion():
    from app.business_fields import cart_quantity_arguments
    from app.conversation_state import ConversationState
    state = ConversationState()
    state.record_cart_items([dict(cartId=71, productId=8, productName='Spring Framework Guide', quantity=3),
                             dict(cartId=72, productId=2, productName='Smartphone X', quantity=1),
                             dict(cartId=73, productId=1, productName='Wireless Headphones', quantity=2)])
    assert cart_quantity_arguments('只把所有耳机改为1件', state)['items'] == [{'cart_id': 73, 'quantity': 1}]


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['live', 'demo'])
@pytest.mark.parametrize('reply', ['2件', '2', '两件'])
async def test_vague_quantity_asks_then_uses_explicit_followup(mode, reply):
    business = BulkCartBusiness((3, 1, 2))
    store = ConversationStateStore()
    state = await store.get('clarify', 'jwt')
    state.record_cart_items(business.cart)
    agent = service(mode, business, store)
    clarification = await agent.chat('把框架指南数量改少一点', session_id='clarify', access_token='jwt')
    assert '改为几件' in clarification.answer
    assert clarification.confirmation is None
    result = await agent.chat(reply, session_id='clarify', access_token='jwt')
    assert result.confirmation is None
    assert result.tool_calls[-1].arguments == {'cart_id': 71, 'quantity': 2}
    assert business.updates == [(71, 2)]


@pytest.mark.asyncio
async def test_live_ambiguity_and_no_pending_confirmation_have_clear_questions():
    store = ConversationStateStore()
    state = await store.get('vague', 'jwt')
    business = BulkCartBusiness((3, 1, 2))
    state.record_cart_items(business.cart)
    agent = service('live', business, store)
    for question, expected in [('帮我少买一点', '哪件商品'), ('它改成1件', '哪件商品'), ('确认', '没有待确认')]:
        result = await agent.chat(question, session_id='vague', access_token='jwt')
        assert expected in result.answer
        assert result.confirmation is None
    result = await agent.chat('把它加入购物车', session_id='fresh-vague', access_token='jwt')
    assert '哪件商品' in result.answer


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['live', 'demo'])
async def test_fractional_adjustment_asks_exact_quantity_instead_of_guessing(mode):
    result = await service(mode, BulkCartBusiness((3, 1, 2))).chat('把框架指南数量减少一半', session_id='half', access_token='jwt')
    assert result.confirmation is None
    assert '比例' in result.answer


@pytest.mark.parametrize('product, expected', [
    ({'stock': 10}, '可购买'),
    ({'stock': 120}, '可购买'),
    ({'stock': 0}, '暂时缺货'),
    ({'stock': None}, '购买状态待确认'),
    ({'stock': -1}, '购买状态待确认'),
    ({'stock': 1.5}, '购买状态待确认'),
    ({'stock': 'NaN'}, '购买状态待确认'),
    ({'stock': 10, 'status': 0}, '暂不可购买'),
])
def test_product_purchase_copy_uses_availability_without_inventing_limits(product, expected):
    from app.business_feedback import product_purchase_copy
    from app.demo_agent import DemoAgentService
    assert product_purchase_copy(product) == expected
    detail = DemoAgentService._format_product_detail(product)
    recommendation = DemoAgentService._format_products([product], '')
    for answer in [detail, recommendation]:
        assert expected in answer
        assert '库存' not in answer
        assert '限购' not in answer


@pytest.mark.parametrize('error, expected', [
    ('库存不足，当前库存为 3 件，无法购买 5 件。', '这件商品目前可供购买 3 件，请减少数量后再试。'),
    ('库存不足，当前库存为 0 件，无法购买 5 件。', '这件商品暂时缺货，可以看看其他商品，或稍后再来。'),
    ('无法获取商品库存信息。', '暂时无法确认这件商品是否可购买，请稍后再试。'),
    ('Insufficient stock for product: 测试商品', '您选择的数量暂时无法满足，请减少数量后再试，或看看其他商品。'),
])
def test_customer_stock_errors_are_friendly_in_replies_and_tool_events(error, expected):
    from app.business_feedback import customer_error_reply
    from app.clients.ecommerce_client import EcommerceApiError
    assert customer_error_reply(error) == expected
    assert ToolRegistry._friendly_error(EcommerceApiError(error)) == expected
