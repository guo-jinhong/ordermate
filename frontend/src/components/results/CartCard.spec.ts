import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import CartCard from './CartCard.vue'

describe('CartCard', () => {
  it('uses productId for details and cartId for mutations', async () => {
    const wrapper = mount(CartCard, { props: { item: { cartId: 71, productId: 8, productName: 'Spring Framework Guide', quantity: 1 } } })
    await wrapper.get('button.product-title').trigger('click')
    await wrapper.get('button[aria-label="增加Spring Framework Guide的数量"]').trigger('click')
    expect(wrapper.emitted('prompt')?.[0]?.[0]).toMatchObject({ prompt: '查看商品 8 的详情' })
    expect(wrapper.emitted('prompt')?.[1]?.[0]).toMatchObject({ prompt: '将购物车项 71 的数量改为 2 件', displayPrompt: '将购物车中「Spring Framework Guide」的数量改为 2 件' })
  })
  it('renders quantity and a calculated subtotal', () => {
    const wrapper = mount(CartCard, {
      props: { item: { cartId: 7, productId: 8, productName: '测试商品', price: 99, quantity: 2 } },
    })

    expect(wrapper.text()).toContain('测试商品')
    expect(wrapper.text()).toContain('¥99')
    expect(wrapper.text()).toContain('¥198')
  })

  it('degrades invalid values and disables unsafe actions', () => {
    const wrapper = mount(CartCard, {
      props: { item: { productName: '字段不完整商品', price: 'bad', quantity: 1.5 } },
    })

    expect(wrapper.text()).toContain('价格待确认')
    expect(wrapper.text()).toContain('金额待确认')
    expect(wrapper.findAll('button').every((button) => button.attributes('disabled') !== undefined)).toBe(true)
  })

  it('requests explicit quantities and never decreases below one', async () => {
    const wrapper = mount(CartCard, { props: { item: { cartId: 7, productId: 8, productName: '测试商品', quantity: 2 } } })
    await wrapper.get('button[aria-label="减少测试商品的数量"]').trigger('click')
    await wrapper.get('button[aria-label="增加测试商品的数量"]').trigger('click')
    expect(wrapper.emitted('prompt')?.map(event => (event[0] as { prompt: string }).prompt)).toEqual([
      '将购物车项 7 的数量改为 1 件', '将购物车项 7 的数量改为 3 件',
    ])
    await wrapper.setProps({ item: { cartId: 7, productName: '测试商品', quantity: 1 } })
    expect(wrapper.get('button[aria-label="减少测试商品的数量"]').attributes('disabled')).toBeDefined()
    await wrapper.setProps({ busy: true })
    expect(wrapper.findAll('button').every(button => button.attributes('disabled') !== undefined)).toBe(true)
  })

  it('emits a login-required remove intent', async () => {
    const wrapper = mount(CartCard, {
      props: { managing: true, item: { cartId: 7, productName: '测试商品', price: 99, quantity: 2 } },
    })

    await wrapper.get('button.danger').trigger('click')
    expect(wrapper.emitted('prompt')?.[0]?.[0]).toEqual({
      prompt: '移除购物车项 7',
      displayPrompt: '从购物车移除「测试商品」',
      label: '移出个人购物车商品',
      authRequired: true,
      preserveScroll: true,
    })
  })
})
