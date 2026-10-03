import { describe, expect, it } from 'vitest'

import type { ConfirmationAction } from '@/types/api'

import {
  confirmationPresentation,
  emptyResultCopy,
  streamEventLabel,
  toolBusinessLabel,
  toolStatusCopy,
} from './labels'

describe('business labels', () => {
  it('maps known tools and hides unknown internal names', () => {
    expect(toolBusinessLabel('refund_order')).toBe('申请订单退款')
    expect(toolBusinessLabel('internal_future_tool')).toBe('处理您的请求')
  })

  it('provides status copy for each outcome class', () => {
    expect(toolStatusCopy('cancel_order', 'confirmation_required')).toMatchObject({ status: '等待确认', tone: 'warning' })
    expect(toolStatusCopy('search_products', 'success').tone).toBe('success')
    expect(toolStatusCopy('search_products', 'error').tone).toBe('error')
    expect(toolStatusCopy('search_products', 'clarification_needed').tone).toBe('warning')
  })

  it('maps stream events to readable timeline labels', () => {
    expect(streamEventLabel('progress')).toBe('处理进度')
    expect(streamEventLabel('confirmation_required')).toBe('等待用户确认')
  })

  it('covers all eight confirmation actions', () => {
    const actions: ConfirmationAction[] = [
      'cancel_order', 'refund_order', 'update_cart', 'update_cart_items',
      'remove_from_cart', 'clear_cart', 'create_order', 'pay_order',
    ]

    expect(actions.map((action) => confirmationPresentation(action).confirmLabel)).toHaveLength(8)
    expect(confirmationPresentation('refund_order').title).toContain('退款')
  })

  it('provides safe generic confirmation copy for future actions', () => {
    expect(confirmationPresentation('future_action')).toMatchObject({
      title: '确认进行这项操作？',
      confirmLabel: '确认操作',
    })
  })

  it('provides all empty-state variants', () => {
    expect(emptyResultCopy('product').title).toContain('商品')
    expect(emptyResultCopy('cart').title).toContain('购物车')
    expect(emptyResultCopy('order').title).toContain('订单')
  })
})
