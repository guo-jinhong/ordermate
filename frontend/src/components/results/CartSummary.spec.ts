import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import CartSummary from './CartSummary.vue'

describe('CartSummary', () => {
  it('shows a complete total when every item is valid', () => {
    const wrapper = mount(CartSummary, {
      props: { items: [{ price: 100, quantity: 2 }, { price: 50, quantity: 1 }] },
    })

    expect(wrapper.text()).toContain('2 种商品 · 共 3 件')
    expect(wrapper.text()).toContain('合计 ¥250')
  })

  it('labels a partial calculation as known amount', () => {
    const wrapper = mount(CartSummary, {
      props: { items: [{ price: 100, quantity: 2 }, { price: null, quantity: 1 }] },
    })

    expect(wrapper.text()).toContain('已知金额 ¥200')
    expect(wrapper.text()).not.toContain('合计 ¥200')
  })
})
