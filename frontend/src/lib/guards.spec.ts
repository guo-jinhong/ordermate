import { describe, expect, it } from 'vitest'

import type { ToolCallRecord } from '@/types/api'

import { normalizeResultRecords, resolveResultPayload } from './guards'

function tool(name: string): ToolCallRecord {
  return { name, arguments: {}, outcome: 'success' }
}

describe('resolveResultPayload', () => {
  it('prefers the tool name over field sniffing', () => {
    const result = resolveResultPayload(
      [{ orderNo: 'ORD-1', name: '商品', price: 100 }],
      [tool('search_products')],
    )

    expect(result.kind).toBe('product')
  })

  it('recognizes update_cart_items as cart data', () => {
    expect(resolveResultPayload([], [tool('update_cart_items')])).toEqual({
      kind: 'empty',
      emptyKind: 'cart',
    })
  })

  it('recognizes refund_order as order data', () => {
    expect(resolveResultPayload([], [tool('refund_order')])).toEqual({
      kind: 'empty',
      emptyKind: 'order',
    })
  })

  it('sniffs in order, cart, product priority', () => {
    const result = resolveResultPayload(
      [{ orderNo: 'ORD-1', productId: 1, productName: '商品', quantity: 1, name: '商品', price: 1 }],
      [],
    )

    expect(result.kind).toBe('order')
  })

  it('returns raw for unrecognized non-null data', () => {
    const value = { futureShape: true }

    expect(resolveResultPayload(value, [])).toEqual({ kind: 'raw', value })
  })

  it.each([null, undefined])('returns none for %s', (value) => {
    expect(resolveResultPayload(value, [])).toEqual({ kind: 'none' })
  })

  it('unwraps a content array', () => {
    expect(normalizeResultRecords({ content: [{ name: '手机', price: 2999 }] })).toEqual([
      { name: '手机', price: 2999 },
    ])
    expect(resolveResultPayload({ content: [{ name: '手机', price: 2999 }] }, []).kind).toBe(
      'product',
    )
  })

  it('keeps product search arguments as rendering context', () => {
    const result = resolveResultPayload(
      [{ name: '手机', price: 2999 }],
      [{ name: 'search_products', arguments: { keyword: '手机', max_price: 3000 }, outcome: 'success' }],
    )

    expect(result).toMatchObject({
      kind: 'product',
      context: { keyword: '手机', max_price: 3000 },
    })
  })
})
