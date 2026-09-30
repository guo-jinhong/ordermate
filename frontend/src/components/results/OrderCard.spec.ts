import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import OrderCard from './OrderCard.vue'

describe('OrderCard', () => {
  it('renders a payable order and exposes the cancel action', async () => {
    const wrapper = mount(OrderCard, {
      props: {
        order: {
          id: 8,
          orderNo: 'ORD-8',
          status: 0,
          paymentStatus: 0,
          createdAt: '2026-09-27T08:00:00Z',
          totalAmount: 200,
          discountAmount: 20,
          finalAmount: 180,
          items: [{ productName: '测试商品', quantity: 2, unitPrice: 100 }],
        },
      },
    })

    expect(wrapper.text()).toContain('ORD-8')
    expect(wrapper.text()).toContain('待支付')
    expect(wrapper.text()).toContain('未支付')
    expect(wrapper.text()).toContain('订单金额¥180')
    expect(wrapper.text()).toContain('取消订单')

    await wrapper.get('.danger').trigger('click')
    expect(wrapper.emitted('prompt')?.[0]?.[0]).toEqual({
      prompt: '取消订单 8',
      displayPrompt: '取消订单 ORD-8',
      label: '取消本人订单',
      authRequired: true,
    })
  })

  it('uses actual paid amount only after payment succeeds', () => {
    const wrapper = mount(OrderCard, {
      props: {
        order: {
          orderNo: 'ORD-PAID',
          status: 1,
          paymentStatus: 1,
          finalAmount: 180,
        },
      },
    })

    expect(wrapper.text()).toContain('实付金额¥180')
    expect(wrapper.text()).not.toContain('订单金额¥180')
  })

  it('degrades missing fields and hides cancellation for non-pending orders', () => {
    const wrapper = mount(OrderCard, {
      props: { order: { status: 4, paymentStatus: null } },
    })

    expect(wrapper.text()).toContain('订单号待确认')
    expect(wrapper.text()).toContain('创建时间待确认')
    expect(wrapper.text()).toContain('支付状态未知')
    expect(wrapper.text()).toContain('金额待确认')
    expect(wrapper.text()).not.toContain('取消订单')
  })
})
