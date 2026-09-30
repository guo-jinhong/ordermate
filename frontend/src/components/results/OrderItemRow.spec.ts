import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import OrderItemRow from './OrderItemRow.vue'

describe('OrderItemRow', () => {
  it('uses unit price and quantity when total price is missing', () => {
    const wrapper = mount(OrderItemRow, {
      props: { item: { productName: '测试商品', quantity: 2, unitPrice: 99 } },
    })

    expect(wrapper.text()).toContain('数量 × 2')
    expect(wrapper.text()).toContain('¥198')
  })

  it('degrades invalid quantities and amounts', () => {
    const wrapper = mount(OrderItemRow, {
      props: { item: { productId: 8, quantity: 1.5, unitPrice: 'bad' } },
    })

    expect(wrapper.text()).toContain('商品名称待确认')
    expect(wrapper.text()).toContain('数量 × —')
    expect(wrapper.text()).toContain('金额待确认')
  })
})
