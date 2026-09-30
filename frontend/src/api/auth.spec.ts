import { describe, expect, it, vi } from 'vitest'

import { login, restoreSession } from './auth'

function jsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('auth api', () => {
  it('sends credentials only to the login endpoint', async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(input).toBe('/auth/login')
      expect(init?.method).toBe('POST')
      expect(JSON.parse(String(init?.body))).toEqual({ username: 'demo', password: 'secret' })
      expect(new Headers(init?.headers).has('Authorization')).toBe(false)
      return jsonResponse({ access_token: 'jwt', token_type: 'bearer' })
    }) as typeof fetch

    await expect(login({ username: 'demo', password: 'secret' }, fetchImpl)).resolves.toEqual({
      access_token: 'jwt',
      token_type: 'bearer',
    })
  })

  it('restores a session with Authorization and no token body', async () => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(input).toBe('/auth/session')
      expect(init?.body).toBeUndefined()
      expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer jwt')
      return jsonResponse({ authenticated: true, username: 'demo' })
    }) as typeof fetch

    await expect(restoreSession('jwt', fetchImpl)).resolves.toEqual({
      authenticated: true,
      username: 'demo',
    })
  })
})
