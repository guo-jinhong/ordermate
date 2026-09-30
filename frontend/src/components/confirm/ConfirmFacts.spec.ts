import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { ConfirmationAction } from '../../types/api'
import ConfirmFacts from './ConfirmFacts.vue'

describe('ConfirmFacts', () => {
  it.each<[ConfirmationAction, Record<string, unknown>, string]>([
    ['cancel_order', { order_id: 101, order_no: 'ORD-101' }, 'ORD-101'],
    ['refund_order', { order_id: 102, order_no: 'ORD-102', reason: '重复购买' }, '重复购买'],
    ['update_cart', { cart_id: 11, product_name: '测试耳机', quantity: 3 }, '测试耳机'],
    ['update_cart_items', { items: [{ cart_id: 1 }, { cart_id: 2 }], quantity: 4 }, '目标数量4'],
    ['remove_from_cart', { cart_id: 12, product_name: '测试耳机' }, '测试耳机'],
    ['clear_cart', {}, '当前购物车全部商品'],
    ['create_order', { product_id: 9, product_name: '测试耳机', quantity: 2, address_id: 7 }, '当前账号的收货地址'],
    ['pay_order', { order_id: 103, order_no: 'ORD-103' }, 'ORD-103'],
  ])('renders business facts for %s', (action, args, expected) => {
    const wrapper = mount(ConfirmFacts, { props: { action, args } })

    expect(wrapper.text()).toContain(expected)
  })

  it('does not expose internal product, cart, or address ids', () => {
    const cart = mount(ConfirmFacts, {
      props: { action: 'update_cart', args: { cart_id: 8765, product_name: '测试耳机', quantity: 3 } },
    })
    const order = mount(ConfirmFacts, {
      props: { action: 'create_order', args: { product_id: 9876, product_name: '测试耳机', quantity: 2, address_id: 7654 } },
    })

    expect(cart.text()).not.toContain('8765')
    expect(order.text()).not.toContain('9876')
    expect(order.text()).not.toContain('7654')
  })

  it('uses a safe fallback for a future action', () => {
    const wrapper = mount(ConfirmFacts, {
      props: { action: 'future_action', args: { secret: 'should-not-render' } },
    })

    expect(wrapper.text()).toContain('服务端已锁定本次操作内容')
    expect(wrapper.text()).not.toContain('should-not-render')
  })
})
