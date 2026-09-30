import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import CartCard from './CartCard.vue'

describe('CartCard', () => {
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

  it('emits a login-required remove intent', async () => {
    const wrapper = mount(CartCard, {
      props: { item: { cartId: 7, productName: '测试商品', price: 99, quantity: 2 } },
    })

    await wrapper.findAll('button')[2]?.trigger('click')
    expect(wrapper.emitted('prompt')?.[0]?.[0]).toEqual({
      prompt: '从购物车移除「测试商品」',
      label: '移出个人购物车商品',
      authRequired: true,
    })
  })
})
