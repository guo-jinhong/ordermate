import { describe, expect, it, vi } from 'vitest'

import { fetchJson, HttpError, normalizeErrorDetail } from './http'

describe('normalizeErrorDetail', () => {
  it('normalizes standard and rate-limit error bodies', () => {
    expect(normalizeErrorDetail({ detail: '登录状态无效' }, 401)).toBe('登录状态无效')
    expect(normalizeErrorDetail({ error: 'rate_limited', detail: '请求过于频繁' }, 429)).toBe(
      '请求过于频繁',
    )
  })

  it('normalizes FastAPI validation arrays', () => {
    expect(
      normalizeErrorDetail(
        { detail: [{ loc: ['body', 'message'], msg: 'Field required', type: 'missing' }] },
        422,
      ),
    ).toBe('message：Field required')
  })
})

describe('fetchJson', () => {
  it('injects JSON headers and the Authorization token', async () => {
    const fetchImpl = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const headers = new Headers(init?.headers)
      expect(headers.get('Authorization')).toBe('Bearer jwt')
      expect(headers.get('Content-Type')).toBe('application/json')
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }) as typeof fetch

    await expect(
      fetchJson<{ ok: boolean }>('/health', {
        method: 'POST',
        body: '{}',
        accessToken: 'jwt',
        fetchImpl,
      }),
    ).resolves.toEqual({ ok: true })
  })

  it('throws an HttpError with normalized metadata', async () => {
    const fetchImpl = vi.fn(async () =>
      new Response(JSON.stringify({ error: 'rate_limited', detail: '请求过于频繁' }), {
        status: 429,
        headers: { 'Content-Type': 'application/json' },
      }),
    ) as typeof fetch

    const request = fetchJson('/chat', { fetchImpl })
    await expect(request).rejects.toMatchObject({
      name: 'HttpError',
      message: '请求过于频繁',
      status: 429,
      code: 'rate_limited',
    })
  })
})
