import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { clearConversation, confirmAction, streamChat } from '../api/chat'
import { HttpError } from '../lib/http'
import type { AssistantMessage } from '../types/chat'
import { useChatStore } from './chat'
import { useSessionStore } from './session'

vi.mock('../api/chat', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/chat')>()
  return {
    ...original,
    clearConversation: vi.fn(),
    confirmAction: vi.fn(),
    streamChat: vi.fn(),
  }
})

const streamChatMock = vi.mocked(streamChat)
const clearConversationMock = vi.mocked(clearConversation)
const confirmActionMock = vi.mocked(confirmAction)

function frame(type: string, data: unknown): string {
  return `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`
}

function streamResponse(content: string): Response {
  const encoder = new TextEncoder()
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(content))
        controller.close()
      },
    }),
    { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
  )
}

function assistant(runId: string): AssistantMessage {
  return {
    id: 'assistant-1',
    role: 'assistant',
    runId,
    at: 1,
    text: '',
    status: null,
    reference: null,
    results: { kind: 'none' },
    confirmation: null,
    confirmationPhase: 'pending',
    confirmationResult: null,
    streamPhase: 'streaming',
  }
}

function pendingAssistant(action: 'cancel_order' | 'clear_cart' = 'cancel_order'): AssistantMessage {
  return {
    ...assistant('run-confirm'),
    streamPhase: 'done',
    confirmation: {
      token: 'confirmation-token',
      action,
      description: '即将执行高风险操作',
      arguments: action === 'cancel_order' ? { order_id: 8 } : {},
    },
    confirmationPhase: 'pending',
  }
}

describe('chat store', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.clearAllMocks()
    setActivePinia(createPinia())
  })

  it('runs a complete stream and keeps unknown data as a raw result', async () => {
    const response = {
      answer: '处理完成',
      tool_calls: [],
      confirmation: null,
      data: { unexpected: true },
      reference: null,
    }
    streamChatMock.mockResolvedValue(
      streamResponse(frame('started', { message: '开始' }) + frame('result', response)),
    )
    const store = useChatStore()

    await store.send('  帮我处理  ')

    expect(store.messages[0]).toMatchObject({ role: 'user', text: '帮我处理' })
    expect(store.latestAssistant).toMatchObject({
      text: '处理完成',
      streamPhase: 'done',
      results: { kind: 'raw', value: { unexpected: true } },
    })
    expect(store.sending).toBe(false)
    expect(store.activeRunId).toBeNull()
  })

  it('shows a friendly order number while sending the internal order id to the Agent', async () => {
    streamChatMock.mockResolvedValue(
      streamResponse(frame('result', {
        answer: '已找到订单',
        tool_calls: [],
        confirmation: null,
        data: null,
        reference: null,
      })),
    )
    const store = useChatStore()

    await store.send('查看订单 8 的详情', '查看订单 ORD-8 的详情')

    expect(store.messages[0]).toMatchObject({
      role: 'user',
      text: '查看订单 ORD-8 的详情',
    })
    expect(streamChatMock.mock.calls[0]?.[0]).toMatchObject({
      message: '查看订单 8 的详情',
    })
  })

  it('drops events from an old run id', () => {
    const store = useChatStore()
    store.activeRunId = 'run-current'
    store.messages.push(assistant('run-current'))

    store.applyStreamEvent('run-old', { type: 'progress', data: { message: '旧请求写回' } })

    expect(store.latestAssistant?.status).toBeNull()
    expect(store.latestAssistant?.streamPhase).toBe('streaming')
  })

  it('cancels an active request without presenting an error', async () => {
    streamChatMock.mockImplementation(
      (_request, _token, options) =>
        new Promise((_resolve, reject) => {
          options?.signal?.addEventListener('abort', () =>
            reject(new DOMException('aborted', 'AbortError')),
          )
        }),
    )
    const store = useChatStore()
    const request = store.send('停止这次回答')

    store.cancel('user')
    await request

    expect(store.latestAssistant).toMatchObject({
      streamPhase: 'cancelled',
      status: { text: '已停止生成。', tone: 'warning' },
    })
    expect(store.lastError).toBeNull()
  })

  it('clears the old server session, rotates locally, and resets messages', async () => {
    clearConversationMock.mockResolvedValue({ status: 'cleared', cleared: true })
    const session = useSessionStore()
    const store = useChatStore()
    const previousSessionId = session.sessionId
    store.messages.push({ id: 'user-1', role: 'user', text: '旧消息', at: 1 })

    await expect(store.clearConversation()).resolves.toBe(true)

    expect(clearConversationMock).toHaveBeenCalledWith(
      { session_id: previousSessionId },
      null,
    )
    expect(session.sessionId).not.toBe(previousSessionId)
    expect(store.messages).toEqual([])
  })

  it('prevents confirmation re-entry while submitting', async () => {
    const request: { resolve?: (value: { status: 'executed'; message: string; data: unknown }) => void } = {}
    confirmActionMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          request.resolve = resolve
        }),
    )
    const session = useSessionStore()
    session.$patch({ accessToken: 'jwt', authStatus: 'authenticated' })
    const store = useChatStore()
    store.messages.push(pendingAssistant())

    const first = store.confirm(true)
    const second = store.confirm(true)

    expect(store.latestAssistant?.confirmationPhase).toBe('submitting')
    expect(confirmActionMock).toHaveBeenCalledTimes(1)
    expect(confirmActionMock).toHaveBeenCalledWith(
      {
        session_id: session.sessionId,
        confirmation_token: 'confirmation-token',
        approved: true,
      },
      'jwt',
    )
    if (!request.resolve) throw new Error('确认请求未启动。')
    request.resolve({ status: 'executed', message: '订单已取消。', data: { orderNo: 'ORD-8', status: 4 } })
    await Promise.all([first, second])
    expect(store.latestAssistant?.confirmationPhase).toBe('executed')
    expect(store.latestAssistant?.results.kind).toBe('order')
  })

  it('treats a rejected confirmation as a normal cancelled result', async () => {
    confirmActionMock.mockResolvedValue({
      status: 'cancelled',
      message: '已放弃本次操作，数据没有被修改。',
      data: null,
    })
    const session = useSessionStore()
    session.$patch({ accessToken: 'jwt', authStatus: 'authenticated' })
    const store = useChatStore()
    store.messages.push(pendingAssistant('clear_cart'))

    await store.confirm(false)

    expect(store.latestAssistant?.confirmationPhase).toBe('cancelled')
    expect(store.latestAssistant?.confirmationResult?.message).toContain('数据没有被修改')
    expect(store.lastError).toBeNull()
  })

  it('marks an expired confirmation as failed without retrying the token', async () => {
    confirmActionMock.mockRejectedValue(
      new HttpError('确认已失效或已使用。', 404, null, { detail: '确认已失效或已使用。' }),
    )
    const session = useSessionStore()
    session.$patch({ accessToken: 'jwt', authStatus: 'authenticated' })
    const store = useChatStore()
    store.messages.push(pendingAssistant())

    await store.confirm(true)
    await store.confirm(true)

    expect(store.latestAssistant?.confirmationPhase).toBe('failed')
    expect(store.latestAssistant?.confirmationResult?.message).toBe('确认已失效或已使用。')
    expect(confirmActionMock).toHaveBeenCalledTimes(1)
  })

  it('clears invalid auth and applies rate-limit backoff on confirmation failures', async () => {
    const session = useSessionStore()
    session.$patch({ accessToken: 'jwt', authStatus: 'authenticated' })
    const store = useChatStore()
    store.messages.push(pendingAssistant())
    confirmActionMock.mockRejectedValueOnce(
      new HttpError('登录状态无效。', 401, null, { detail: '登录状态无效。' }),
    )

    await store.confirm(true)
    expect(session.accessToken).toBeNull()

    session.$patch({ accessToken: 'jwt', authStatus: 'authenticated' })
    store.messages.push(pendingAssistant('clear_cart'))
    confirmActionMock.mockRejectedValueOnce(
      new HttpError('请求过于频繁', 429, 'rate_limited', {
        error: 'rate_limited',
        detail: '请求过于频繁',
      }),
    )
    await store.confirm(true)

    expect(store.backoffUntil).not.toBeNull()
    expect(store.canSend).toBe(false)
  })
})
