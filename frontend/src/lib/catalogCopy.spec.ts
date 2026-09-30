import { describe, expect, it } from 'vitest'
import { catalogQuery, customerCopy } from './catalogCopy'

describe('demo catalog copy', () => {
  it('keeps localized names usable in subsequent product requests', () => {
    const request = '将「Wireless Headphones」加入购物车，数量 2 件'
    expect(customerCopy(request)).toBe('将「无线降噪耳机」加入购物车，数量 2 件')
    expect(catalogQuery(customerCopy(request))).toBe(request)
    expect(customerCopy('iQOO Neo9 · ¥2,999')).toBe('iQOO Neo9 · ¥2,999')
  })
})
