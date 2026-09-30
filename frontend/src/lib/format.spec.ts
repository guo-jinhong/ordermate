import { describe, expect, it } from 'vitest'

import { finiteAmount, finitePositiveInteger, formatCurrency, formatDateTime } from './format'

describe('format helpers', () => {
  it.each([null, undefined, '', Number.NaN, 'abc'])('degrades invalid amount %s', (value) => {
    expect(finiteAmount(value)).toBeNull()
    expect(formatCurrency(value)).toBe('价格待确认')
    expect(formatCurrency(value)).not.toContain('NaN')
  })

  it('rejects negative amounts and accepts zero', () => {
    expect(finiteAmount(-1)).toBeNull()
    expect(finiteAmount(0)).toBe(0)
    expect(formatCurrency('3000')).toContain('3,000')
  })

  it('only accepts positive integer quantities', () => {
    expect(finitePositiveInteger(2)).toBe(2)
    expect(finitePositiveInteger('3')).toBe(3)
    expect(finitePositiveInteger(1.5)).toBeNull()
    expect(finitePositiveInteger(0)).toBeNull()
  })

  it('degrades invalid dates', () => {
    expect(formatDateTime(null)).toBe('时间待确认')
    expect(formatDateTime('invalid')).toBe('时间待确认')
  })
})
