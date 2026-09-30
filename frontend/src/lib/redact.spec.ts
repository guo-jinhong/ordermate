import { describe, expect, it } from 'vitest'

import { redactSensitive } from './redact'

describe('redactSensitive', () => {
  it('redacts sensitive keys inside nested objects and arrays', () => {
    const result = redactSensitive({
      password: 'secret',
      nested: [{ authorization: 'Bearer token' }, { safe: 'visible' }],
    })

    expect(result).toEqual({
      password: '[已脱敏]',
      nested: [{ authorization: '[已脱敏]' }, { safe: 'visible' }],
    })
  })

  it('matches sensitive keys case-insensitively', () => {
    expect(redactSensitive({ Access_Token: 'jwt', API_KEY: 'key' })).toEqual({
      Access_Token: '[已脱敏]',
      API_KEY: '[已脱敏]',
    })
  })

  it('does not mutate the source value', () => {
    const source = { nested: { token: 'jwt', safe: true } }
    const result = redactSensitive(source)

    expect(source).toEqual({ nested: { token: 'jwt', safe: true } })
    expect(result).not.toBe(source)
    expect((result as { nested: unknown }).nested).not.toBe(source.nested)
  })
})
