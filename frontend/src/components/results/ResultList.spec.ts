import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ResultList from './ResultList.vue'

describe('ResultList', () => {
  it.each([
    {
      kind: 'product' as const,
      payload: { kind: 'product' as const, items: [{ id: 1, name: '测试商品' }], context: {} },
      title: '商品结果',
      value: '测试商品',
    },
    {
      kind: 'cart' as const,
      payload: { kind: 'cart' as const, items: [{ cartId: 2, productName: '购物车商品' }] },
      title: '购物车',
      value: '购物车商品',
    },
    {
      kind: 'order' as const,
      payload: { kind: 'order' as const, items: [{ id: 3, orderNo: 'ORD-3' }] },
      title: '订单结果',
      value: 'ORD-3',
    },
  ])('dispatches the $kind branch', ({ payload, kind, title, value }) => {
    const wrapper = mount(ResultList, { props: { payload } })

    expect(wrapper.get(`[data-result-kind="${kind}"]`).text()).toContain(title)
    expect(wrapper.text()).toContain(value)
  })

  it('reveals products in batches and resets for a new result', async () => {
    const items = Array.from({ length: 14 }, (_, i) => ({ id: i + 1, name: `商品${i + 1}`, stock: 10, price: 20 }))
    const wrapper = mount(ResultList, { props: { payload: { kind: 'product', items, context: {} } } })
    expect(wrapper.findAll('.product-card')).toHaveLength(4)
    await wrapper.get('.result-pagination button').trigger('click')
    expect(wrapper.findAll('.product-card')).toHaveLength(8)
    await wrapper.get('.result-pagination button').trigger('click')
    expect(wrapper.findAll('.product-card')).toHaveLength(12)
    await wrapper.get('.result-pagination button').trigger('click')
    expect(wrapper.findAll('.product-card')).toHaveLength(14)
    expect(wrapper.find('.result-pagination button').exists()).toBe(false)
    await wrapper.setProps({ payload: { kind: 'product', items: items.slice(0, 8), context: {} } })
    expect(wrapper.findAll('.product-card')).toHaveLength(4)
  })

  it('keeps all cart totals visible while expanding and managing rows', async () => {
    const items = Array.from({ length: 6 }, (_, i) => ({ cartId: i + 1, productName: `商品${i}`, price: 10, quantity: 2 }))
    const wrapper = mount(ResultList, { props: { payload: { kind: 'cart', items } } })
    expect(wrapper.findAll('.cart-card')).toHaveLength(4)
    expect(wrapper.get('.cart-summary').text()).toContain('合计 ¥120')
    expect(wrapper.get('.cart-summary').text()).toContain('共 12 件')
    expect(wrapper.find('.danger').exists()).toBe(false)
    await wrapper.get('.summary-link').trigger('click')
    expect(wrapper.findAll('.cart-card')).toHaveLength(6)
    await wrapper.findAll('.result-tools button')[1]!.trigger('click')
    expect(wrapper.findAll('.danger')).toHaveLength(6)
    expect(wrapper.get('.cart-summary button').text()).toBe('清空购物车')
    await wrapper.get('.summary-link').trigger('click')
    expect(wrapper.findAll('.cart-card')).toHaveLength(4)
  })

  it('shows cart statistics without rows until details are requested', async () => {
    const wrapper = mount(ResultList, { props: { payload: { kind: 'cart', summaryOnly: true, items: [{ cartId: 1, price: 99, quantity: 2 }] } } })
    expect(wrapper.find('.cart-card').exists()).toBe(false)
    expect(wrapper.text()).toContain('合计 ¥198')
    await wrapper.get('.summary-link').trigger('click')
    expect(wrapper.findAll('.cart-card')).toHaveLength(1)
  })

  it('resets expansion and management when the result is replaced', async () => {
    const items = Array.from({ length: 6 }, (_, i) => ({ cartId: i + 1, quantity: 1, price: 10 }))
    const wrapper = mount(ResultList, { props: { payload: { kind: 'cart', summaryOnly: true, items } } })
    await wrapper.get('.summary-link').trigger('click')
    await wrapper.get('.summary-link').trigger('click')
    await wrapper.findAll('.result-tools button')[1]!.trigger('click')
    expect(wrapper.findAll('.cart-card')).toHaveLength(6)
    expect(wrapper.find('.danger').exists()).toBe(true)
    await wrapper.setProps({ payload: { kind: 'cart', summaryOnly: true, items: [...items] } })
    expect(wrapper.find('.cart-card').exists()).toBe(false)
    await wrapper.get('.summary-link').trigger('click')
    expect(wrapper.findAll('.cart-card')).toHaveLength(4)
    expect(wrapper.find('.danger').exists()).toBe(false)
  })

  it('preserves expansion and management during an in-place cart update', async () => {
    const items = Array.from({ length: 6 }, (_, i) => ({ cartId: i + 1, productId: i + 1, quantity: 1, price: 10 }))
    const wrapper = mount(ResultList, { props: { payload: { kind: 'cart', items } } })
    await wrapper.get('.summary-link').trigger('click')
    await wrapper.findAll('.result-tools button')[1]!.trigger('click')
    await wrapper.setProps({ payload: { kind: 'cart', preserveState: true, items: items.map(item => ({ ...item, quantity: 2 })) } })
    expect(wrapper.findAll('.cart-card')).toHaveLength(6)
    expect(wrapper.findAll('.danger')).toHaveLength(6)
    await wrapper.setProps({ payload: { kind: 'cart', preserveState: true, stale: true, feedback: '请刷新', items } })
    expect(wrapper.findAll('.quantity-control button').every(button => button.attributes('disabled') !== undefined)).toBe(true)
    expect(wrapper.findAll('.result-tools button')[0]!.attributes('disabled')).toBeUndefined()
  })

  it('keeps a complete description available in product detail results', () => {
    const wrapper = mount(ResultList, { props: { payload: { kind: 'product', context: { detail: true }, items: [{ id: 8, name: '商品', price: 99, description: '完整商品说明', stock: 10 }] } } })
    expect(wrapper.find('.product-card.compact').exists()).toBe(false)
    expect(wrapper.get('.description').text()).toBe('完整商品说明')
  })

  it('renders empty results and forwards the action prompt', async () => {
    const wrapper = mount(ResultList, {
      props: { payload: { kind: 'empty', emptyKind: 'order' } },
    })

    await wrapper.get('button').trigger('click')

    expect(wrapper.text()).toContain('暂时没有订单')
    expect(wrapper.emitted('prompt')).toEqual([[{
      prompt: '推荐一些商品',
      label: '去查看商品',
      authRequired: false,
    }]])
  })

  it('renders raw results and renders nothing for none', async () => {
    const wrapper = mount(ResultList, {
      props: { payload: { kind: 'raw', value: { custom: true } } },
    })
    expect(wrapper.text()).toContain('查看未识别数据')

    await wrapper.setProps({ payload: { kind: 'none' } })
    expect(wrapper.html()).toBe('<!--v-if-->')
  })
})
