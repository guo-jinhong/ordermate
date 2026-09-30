import { describe, expect, it, vi } from 'vitest'

import { clearConversation, confirmAction, sendChat, streamChat } from './chat'

function jsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('chat api', () => {
  it.each([
    {
      name: 'chat',
      call: (fetchImpl: typeof fetch) =>
        sendChat({ message: '你好', session_id: 'session-1' }, 'jwt', { fetchImpl }),
      path: '/chat',
    },
    {
      name: 'confirm',
      call: (fetchImpl: typeof fetch) =>
        confirmAction(
          { session_id: 'session-1', confirmation_token: 'confirm-1', approved: true },
          'jwt',
          { fetchImpl },
        ),
      path: '/confirm',
    },
    {
      name: 'clear conversation',
      call: (fetchImpl: typeof fetch) =>
        clearConversation({ session_id: 'session-1' }, 'jwt', { fetchImpl }),
      path: '/conversation/clear',
    },
  ])('uses Authorization and omits compatibility token fields for $name', async ({ call, path }) => {
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(input).toBe(path)
      expect(init?.method).toBe('POST')
      expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer jwt')
      expect(JSON.parse(String(init?.body))).not.toHaveProperty('access_token')
      return jsonResponse({})
    }) as typeof fetch

    await call(fetchImpl)
  })

  it('opens the SSE endpoint with the requested abort signal', async () => {
    const controller = new AbortController()
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const headers = new Headers(init?.headers)
      expect(input).toBe('/chat/stream')
      expect(headers.get('Accept')).toBe('text/event-stream')
      expect(headers.get('Authorization')).toBe('Bearer jwt')
      expect(init?.signal).toBe(controller.signal)
      expect(JSON.parse(String(init?.body))).toEqual({ message: '查询订单', session_id: 'session-1' })
      return new Response(null, { status: 200 })
    }) as typeof fetch

    await expect(
      streamChat({ message: '查询订单', session_id: 'session-1' }, 'jwt', {
        fetchImpl,
        signal: controller.signal,
      }),
    ).resolves.toBeInstanceOf(Response)
  })
})
