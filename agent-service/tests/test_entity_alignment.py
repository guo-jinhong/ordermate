"""商品卡片、历史上下文、模型参数和业务回执必须引用同一对象。"""
from types import SimpleNamespace
import json

import pytest

from app.agent import AgentService, _direct_update_cart_arguments, _direct_add_to_cart_arguments, _direct_cancel_order_arguments, _guard_tool_call, _infer_from_state, update_state_from_tool
from app.business_fields import extract_quantity
from app.conversation_state import ConversationState, ConversationStateStore
from app.demo_agent import DemoAgentService
from app.tools.confirmation import ConfirmationStore
from app.tools.registry import ToolRegistry


class Catalog:
    def __init__(self):
        self.adds = []
        self.wrong_detail = False

    async def get_product_detail(self, product_id):
        return {"id": 2 if self.wrong_detail else product_id,
                "name": "Spring Framework Guide" if product_id == 8 else "Smartphone X",
                "stock": 200, "price": 99}

    async def add_to_cart(self, product_id, quantity, access_token):
        self.adds.append((product_id, quantity))
        return None

    async def search_products(self, *args):
        return [{"id": 2, "name": "Smartphone X", "stock": 200, "price": 2999}]


def stale_state():
    return ConversationState(last_product_id=2, last_product_name="Smartphone X", last_topic="product")


@pytest.mark.parametrize("message", [
    "将「Spring Framework Guide」加入购物车，数量 1 件",
    "将 Spring Framework Guide 加入购物车", "将未知商品加入购物车",
])
def test_named_product_never_falls_back_to_previous_phone(message):
    assert stale_state().resolve_product_id(message, None) is None


def test_exact_name_precedes_shared_word_and_ambiguous_alias_is_rejected():
    state = stale_state()
    state.shown_products = [{"id": 7, "name": "Spring Pocket Guide"},
                            {"id": 8, "name": "Spring Framework Guide"}]
    assert state.resolve_product_id("将 Spring Framework Guide 加入购物车", None) == 8
    assert state.resolve_product_id("将 Spring 加入购物车", None) is None
    assert state.resolve_product_id("将「Spring Missing Guide」加入购物车", None) is None


def test_empty_search_clears_previous_selection():
    state = stale_state()
    state.record_product_search("missing", shown_products=[], shown_product_ids=[])
    assert state.resolve_product_id("加入购物车", None) is None


def test_pronoun_does_not_mean_first_result_in_a_multiple_result_list():
    state = ConversationState()
    state.record_product_search('', product_id=2, product_name='Smartphone X', shown_products=[
        {'id': 2, 'name': 'Smartphone X'}, {'id': 8, 'name': 'Spring Framework Guide'}])
    assert state.resolve_product_id('把它加入购物车', None) is None
    state.record_product(8, 'Spring Framework Guide')
    state.record_cart_view()
    assert state.resolve_product_id('把它加入购物车', None) == 8
    update_state_from_tool(state, 'get_my_orders', {}, {'data': [{'id': 100, 'orderNo': 'ORD-900'}, {'id': 200, 'orderNo': 'ORD-901'}]})
    assert state.resolve_order_id('取消它', None) is None
    state.record_order(200, 'ORD-901')
    assert state.resolve_order_id('取消它', None) == 200


def test_unfiltered_recommendation_updates_context_instead_of_keeping_old_phone():
    state = stale_state()
    update_state_from_tool(state, "search_products", {"keyword": ""}, {"data": [
        {"id": 4, "name": "Cotton T-Shirt"}, {"id": 8, "name": "Spring Framework Guide"}]})
    assert state.resolve_product_id("将「Spring Framework Guide」加入购物车，数量 1 件", None) == 8
    update_state_from_tool(state, "search_products", {"keyword": ""}, {"data": []})
    assert state.resolve_product_id("加入购物车", None) is None


def test_cart_id_is_distinct_from_product_id_and_unknown_name_is_rejected():
    state = stale_state()
    state.record_cart_items([{"cartId": 71, "productId": 8, "productName": "Spring Framework Guide", "quantity": 1}])
    assert state.resolve_cart_id("移除购物车项 71", None) == 71
    assert state.resolve_cart_id("从购物车移除「Smartphone X」", None) is None
    assert state.resolve_cart_id("修改购物车中未知商品数量", None) is None


def test_two_units_does_not_mean_update_every_cart_item():
    state = ConversationState()
    state.record_cart_items([{"cartId": 71, "productName": "Spring Framework Guide"},
                             {"cartId": 72, "productName": "Smartphone X"}])
    assert _direct_update_cart_arguments("将 Spring Framework Guide 数量改成两件", state) == {"cart_id": 71, "quantity": 2}


@pytest.mark.parametrize("tool,args,message", [
    ("add_to_cart", {"product_id": 2, "quantity": 1}, "将商品 8 加入购物车，数量 1 件"),
    ("get_product_detail", {"product_id": 2}, "查看商品 8 的详情"),
    ("create_order", {"product_id": 2, "quantity": 1}, "购买商品 8，数量 1 件"),
    ("update_cart", {"cart_id": 8, "quantity": 2}, "将购物车项 71 的数量改为 2 件"),
    ("remove_from_cart", {"cart_id": 8}, "移除购物车项 71"),
    ("add_to_cart", {"product_id": 8, "quantity": 2}, "将商品 8 加入购物车，数量 1 件"),
])
def test_wrong_model_object_or_quantity_cannot_reach_business_api(tool, args, message):
    assert _guard_tool_call(tool, args, message, stale_state())


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["live", "demo"])
@pytest.mark.parametrize("with_context", [False, True])
async def test_card_id_and_reply_match_book_even_with_stale_phone(mode, with_context):
    catalog = Catalog()
    registry = ToolRegistry(catalog, ConfirmationStore())
    store = ConversationStateStore()
    if with_context:
        await store.save("card", "jwt", stale_state())
    agent = DemoAgentService(registry, state_store=store) if mode == "demo" else AgentService(
        SimpleNamespace(), registry, model="test", state_store=store)
    response = await agent.chat("将商品 8 加入购物车，数量 1 件", session_id="card", access_token="jwt")
    assert catalog.adds == [(8, 1)]
    assert response.tool_calls[0].arguments == {"product_id": 8, "quantity": 1}
    assert "Spring Framework Guide" in response.answer
    assert "Smartphone" not in response.answer


@pytest.mark.asyncio
async def test_model_guess_and_fabricated_success_are_both_blocked():
    responses = iter([
        SimpleNamespace(output=[SimpleNamespace(type="function_call", name="add_to_cart",
            arguments=json.dumps({"product_id": 2, "quantity": 1}), call_id="wrong")], output_text=""),
        SimpleNamespace(output=[], output_text="已将手机成功加入购物车。"),
    ])
    async def create(**kwargs):
        return next(responses)
    catalog = Catalog()
    store = ConversationStateStore()
    await store.save("wrong", "jwt", stale_state())
    agent = AgentService(SimpleNamespace(responses=SimpleNamespace(create=create)),
        ToolRegistry(catalog, ConfirmationStore()), model="test", state_store=store)
    result = await agent.chat("将「Spring Framework Guide」加入购物车，数量 1 件", session_id="wrong", access_token="jwt")
    assert catalog.adds == []
    assert result.tool_calls[0].outcome == "error"
    assert "您指的是哪件商品" in result.answer
    assert "成功" not in result.answer


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity", [100, 0, -1, 1.5])
@pytest.mark.parametrize("mode", ["live", "demo"])
async def test_invalid_or_over_limit_quantity_never_becomes_one_unit(quantity, mode):
    catalog = Catalog()
    registry = ToolRegistry(catalog, ConfirmationStore())
    agent = DemoAgentService(registry) if mode == "demo" else AgentService(SimpleNamespace(), registry, model="test")
    result = await agent.chat(f"将商品 8 加入购物车，数量 {quantity} 件", session_id="quantity", access_token="jwt")
    assert catalog.adds == []
    assert result.tool_calls[0].outcome == "error"


@pytest.mark.asyncio
async def test_mismatched_detail_id_stops_before_write():
    catalog = Catalog()
    catalog.wrong_detail = True
    result = await ToolRegistry(catalog, ConfirmationStore()).execute("add_to_cart", {"product_id": 8, "quantity": 1}, session_id="wrong-api", access_token="jwt")
    assert result.outcome == "error"
    assert "商品信息暂时无法确认" in result.output["error"]
    assert catalog.adds == []


@pytest.mark.parametrize('text,quantity', [('数量两件', 2), ('数量十二件', 12), ('数量二十三件', 23), ('数量一百件', 100), ('数量改为 3', 3), ('将「12件套」加入购物车，数量两件', 2), ('数量 0', 0), ('数量 -1', -1), ('数量 1.5', 0)])
def test_live_and_demo_use_identical_quantities(text, quantity):
    assert extract_quantity(text) == quantity
    assert DemoAgentService._extract_quantity(text) == quantity


def test_english_cart_read_cannot_become_add_to_cart():
    state = stale_state()
    assert _direct_add_to_cart_arguments('show Smartphone X cart', state) is None
    assert _guard_tool_call('add_to_cart', {'product_id': 2, 'quantity': 1}, 'show Smartphone X cart', state)


@pytest.mark.parametrize('text', ['不要将商品 8 加入购物车', '别清空购物车', '不要取消订单 100'])
def test_negated_instruction_does_not_enter_direct_mutation(text):
    state = stale_state()
    state.record_order(100)
    assert _direct_add_to_cart_arguments(text, state) is None
    assert _direct_cancel_order_arguments(text, state) is None


def test_order_number_is_not_internal_order_id_or_quantity():
    state = ConversationState()
    state.record_order(100, 'ORD-900')
    assert state.resolve_order_id('取消订单 ORD-900', None) == 100
    assert _direct_cancel_order_arguments('取消订单 ORD-900', state) == {'order_id': 100}
    assert _guard_tool_call('cancel_order', {'order_id': 900}, '取消订单 ORD-900', state)
    assert _direct_cancel_order_arguments('取消订单，金额 99 元', state) is None
    assert _direct_cancel_order_arguments('取消订单', state) is None
    state.record_product(8, 'Spring Framework Guide')
    assert state.resolve_order_id('支付它', None) is None


def test_missing_order_argument_uses_current_request_instead_of_old_order():
    state = ConversationState()
    state.record_order(100, 'ORD-900')
    assert _infer_from_state('get_order_detail', {}, state, ['order_id'], '查看订单 200 的详情') == {'order_id': 200}
    update_state_from_tool(state, 'get_my_orders', {}, {'data': []})
    assert state.resolve_order_id('取消它', None) is None


@pytest.mark.parametrize('mode', ['live', 'demo'])
@pytest.mark.asyncio
async def test_multiple_explicit_products_are_not_silently_reduced_to_first(mode):
    catalog = Catalog()
    registry = ToolRegistry(catalog, ConfirmationStore())
    if mode == 'demo':
        result = await DemoAgentService(registry).chat('将商品 8 和商品 2 加入购物车', session_id='multiple', access_token='jwt')
        assert result.confirmation is None
    else:
        assert _guard_tool_call('add_to_cart', {'product_id': 8, 'quantity': 1}, '将商品 8 和商品 2 加入购物车', stale_state())
    assert catalog.adds == []


@pytest.mark.asyncio
@pytest.mark.parametrize('action,args', [('update_cart', {'cart_id': 999, 'quantity': 2}), ('remove_from_cart', {'cart_id': 999})])
async def test_removed_cart_item_cannot_produce_confirmation(action, args):
    class EmptyCart(Catalog):
        async def get_cart(self, access_token):
            return []
    result = await ToolRegistry(EmptyCart(), ConfirmationStore()).execute(action, args, session_id='stale-card', access_token='jwt')
    assert result.outcome == 'error'
    assert result.confirmation is None
    assert '已不存在' in result.output['error']


@pytest.mark.asyncio
async def test_product_reply_cannot_replace_verified_book_with_phone():
    replies = iter([
        SimpleNamespace(output=[SimpleNamespace(type='function_call', name='get_product_detail', arguments='{"product_id":8}', call_id='detail')], output_text=''),
        SimpleNamespace(output=[], output_text='智能手机 X，价格2999元，库存30件。')])
    async def create(**kwargs):
        return next(replies)
    agent = AgentService(SimpleNamespace(responses=SimpleNamespace(create=create)), ToolRegistry(Catalog(), ConfirmationStore()), model='test')
    result = await agent.chat('查看商品 8 的详情', session_id='reply-grounding', access_token=None)
    assert 'Spring Framework Guide' in result.answer
    assert '99' in result.answer
    assert '智能手机' not in result.answer


@pytest.mark.parametrize('mode', ['live', 'demo'])
def test_http_cart_and_order_confirmation_flow_keeps_exact_entities(mode):
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.main import create_app
    import re

    class Business(Catalog):
        def __init__(self):
            super().__init__()
            self.cart = [{"cartId": 71, "productId": 8, "productName": "Spring Framework Guide", "quantity": 1},
                         {"cartId": 72, "productId": 2, "productName": "Smartphone X", "quantity": 1}]
            self.updates, self.removes, self.cancelled = [], [], []

        async def get_current_user(self, access_token):
            return {'id': 1, 'username': 'isolated-test'}

        async def get_cart(self, access_token):
            return [dict(item) for item in self.cart]

        async def update_cart(self, cart_id, quantity, access_token):
            self.updates.append((cart_id, quantity))
            next(item for item in self.cart if item['cartId'] == cart_id)['quantity'] = quantity

        async def remove_from_cart(self, cart_id, access_token):
            self.removes.append(cart_id)
            self.cart = [item for item in self.cart if item['cartId'] != cart_id]

        async def get_order_detail(self, order_id, access_token):
            return {'id': order_id, 'orderNo': 'ORD-900', 'status': 0, 'finalAmount': 99}

        async def cancel_order(self, order_id, access_token):
            self.cancelled.append(order_id)
            return {'id': order_id, 'orderNo': 'ORD-900', 'status': 4}

        async def close(self):
            pass

    class Model:
        def __init__(self):
            self.responses = self
        async def create(self, **kwargs):
            items = kwargs['input']
            if any(getattr(item, 'type', None) == 'function_call' for item in items):
                return SimpleNamespace(output=[], output_text='错误的模型说明：已修改手机。')
            message = [item['content'] for item in items if isinstance(item, dict) and item.get('role') == 'user'][-1]
            if '购物车项' in message:
                name, args = 'remove_from_cart', {'cart_id': int(re.search(r'购物车项\s*(\d+)', message).group(1))}
            elif '购物车' in message:
                name, args = 'get_cart', {}
            else:
                name, args = 'get_order_detail', {'order_id': 100}
            return SimpleNamespace(output=[SimpleNamespace(type='function_call', name=name, arguments=json.dumps(args), call_id='flow')], output_text='')
        async def close(self):
            pass

    business = Business()
    settings = Settings(openai_api_key='test' if mode == 'live' else None, openai_model='test', openai_base_url=None,
                        ecommerce_api_base_url='http://isolated.test/api', request_timeout_seconds=1, max_tool_rounds=3, agent_mode=mode)
    app = create_app(settings, ecommerce_client=business, model_client=Model() if mode == 'live' else None)
    with TestClient(app) as client:
        def chat(message):
            response = client.post('/chat', json={'message': message, 'session_id': 'http-alignment', 'access_token': 'test-jwt'})
            assert response.status_code == 200
            return response.json()
        def confirm(prepared):
            assert prepared['confirmation'] is not None
            response = client.post('/confirm', json={'session_id': 'http-alignment', 'confirmation_token': prepared['confirmation']['token'], 'approved': True, 'access_token': 'test-jwt'})
            assert response.status_code == 200
            assert response.json()['status'] == 'executed'
            return response.json()

        added = chat('将商品 8 加入购物车，数量十二件')
        assert business.adds == [(8, 12)]
        assert 'Spring Framework Guide' in added['answer']
        cart_view = chat('查看我的购物车')
        assert '已修改手机' not in cart_view['answer']
        prepared = chat('将购物车项 71 的数量改为两件')
        assert prepared['confirmation'] is None
        assert 'Spring Framework Guide' in prepared['answer']
        assert business.updates == [(71, 2)]
        assert business.cart[1]['quantity'] == 1
        removed = chat('移除购物车项 71')
        assert removed['confirmation'] is None
        assert 'Spring Framework Guide' in removed['answer']
        assert business.removes == [71]
        assert business.cart[0]['productId'] == 2
        stale = chat('移除购物车项 71')
        assert stale['confirmation'] is None
        assert '已不存在' in stale['answer']
        order_view = chat('查看订单 100 的详情')
        assert 'ORD-900' in order_view['answer']
        assert '已修改手机' not in order_view['answer']
        cancelled = chat('取消订单 ORD-900')
        assert cancelled['confirmation']['arguments']['order_id'] == 100
        confirm(cancelled)
        assert business.cancelled == [100]
