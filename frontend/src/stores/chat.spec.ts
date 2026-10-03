import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { clearConversation, confirmAction, fetchCart, fetchOperationStatus, streamChat } from '../api/chat'
import { HttpError } from '../lib/http'
import type { AssistantMessage } from '../types/chat'
import { useChatStore } from './chat'
import { useViewStore } from './view'
import { useSessionStore } from './session'

vi.mock('../api/chat', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/chat')>()
  return {
    ...original,
    clearConversation: vi.fn(),
    confirmAction: vi.fn(),
    streamChat: vi.fn(),
    fetchCart: vi.fn(),
    fetchOperationStatus: vi.fn(),
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
  it('manual verification of persisted null clear-cart success clears the old display', async () => {
    const session = useSessionStore()
    session.$patch({ accessToken: 'jwt', authStatus: 'authenticated' })
    const store = useChatStore()
    const old = assistant('old-run')
    old.id = 'old-cart'
    old.results = { kind: 'cart', items: [{ cartId: 71, quantity: 1, price: 99 }] }
    const pending = pendingAssistant('clear_cart')
    pending.confirmationPhase = 'unknown'
    store.messages.push(old, pending)
    vi.mocked(fetchOperationStatus).mockResolvedValue({ status: 'executed', message: '已核实成功', data: null })
    await store.verifyOperation(pending.id)
    expect(store.messages[0]).toMatchObject({ results: { kind: 'cart', items: [] } })
    expect(store.latestAssistant?.confirmationPhase).toBe('executed')
    expect(confirmActionMock).not.toHaveBeenCalled()
  })
  it('manually verifies unknown results without resubmitting confirmation', async () => {
    const session = useSessionStore()
    session.$patch({ accessToken: 'jwt', authStatus: 'authenticated' })
    const store = useChatStore()
    const message = pendingAssistant()
    message.confirmationPhase = 'unknown'
    store.messages.push(message)
    vi.mocked(fetchOperationStatus).mockResolvedValue({ status: 'executed', message: '订单已取消', data: { id: 8, status: 4 } })
    await store.verifyOperation(message.id)
    expect(fetchOperationStatus).toHaveBeenCalledWith(message.confirmation!.token, session.sessionId, 'jwt')
    expect(confirmActionMock).not.toHaveBeenCalled()
    expect(store.latestAssistant?.confirmationPhase).toBe('executed')
  })

  it('failed verification keeps the result unknown and permits another read', async () => {
    const session = useSessionStore()
    session.$patch({ accessToken: 'jwt', authStatus: 'authenticated' })
    const store = useChatStore()
    const message = pendingAssistant()
    message.confirmationPhase = 'unknown'
    store.messages.push(message)
    vi.mocked(fetchOperationStatus).mockRejectedValue(new TypeError('network'))
    await store.verifyOperation(message.id)
    expect(store.latestAssistant?.confirmationPhase).toBe('unknown')
    expect(store.canSend).toBe(true)
    expect(confirmActionMock).not.toHaveBeenCalled()
  })
  it('rejects a locally expired card before sending its token', async () => {
    const session = useSessionStore()
    session.$patch({ accessToken: 'jwt', authStatus: 'authenticated' })
    const store = useChatStore()
    const message = pendingAssistant()
    message.confirmation!.expires_at = new Date(Date.now() - 1000).toISOString()
    store.messages.push(message)
    await store.confirm(true, message.id)
    expect(confirmActionMock).not.toHaveBeenCalled()
    expect(store.latestAssistant?.confirmationResult?.message).toContain('已过期')
  })
  it('preserves an unknown write result without enabling another submission', async () => {
    const session = useSessionStore()
    session.$patch({ accessToken: 'jwt', authStatus: 'authenticated' })
    const store = useChatStore()
    store.messages.push(pendingAssistant())
    confirmActionMock.mockResolvedValue({ status: 'unknown', message: '请查询订单，勿重复提交。', data: null })
    await store.confirm(true)
    await store.confirm(true)
    expect(confirmActionMock).toHaveBeenCalledTimes(1)
    expect(store.latestAssistant?.confirmationPhase).toBe('unknown')
  })
  beforeEach(() => {
    sessionStorage.clear()
    vi.clearAllMocks()
    setActivePinia(createPinia())
  })

  it('updates the existing cart only from successful verified data', () => {
    const store = useChatStore()
    const old = assistant('old-run')
    old.id = 'old-cart'
    old.results = { kind: 'cart', items: [{ cartId: 71, price: 99, quantity: 1 }] }
    const current = assistant('update-run')
    current.id = 'current'
    store.messages.push(old, current)
    store.activeRunId = 'update-run'
    store.finalizeRun('update-run', { answer: '数量已改为2件', data: [{ cartId: 71, price: 99, quantity: 2 }], tool_calls: [{ name: 'update_cart', arguments: {}, outcome: 'success' }], confirmation: null, reference: null })
    expect(store.messages[0]).toMatchObject({ results: { kind: 'cart', items: [{ quantity: 2 }] } })
    expect(store.latestAssistant?.results.kind).toBe('none')
    expect(store.latestAssistant?.text).toBe('数量已改为2件')
  })

  it('does not overwrite the cart when a write result is unverified', () => {
    const store = useChatStore()
    const old = assistant('old-run')
    old.id = 'old-cart'
    old.results = { kind: 'cart', items: [{ cartId: 71, price: 99, quantity: 1 }] }
    const current = assistant('update-run')
    current.id = 'current'
    store.messages.push(old, current)
    store.activeRunId = 'update-run'
    store.finalizeRun('update-run', { answer: '无法核实', data: null, tool_calls: [{ name: 'update_cart', arguments: {}, outcome: 'error' }], confirmation: null, reference: null })
    expect(store.messages[0]).toMatchObject({ results: { kind: 'cart', items: [{ quantity: 1 }] } })
  })

  it.each([
    ['商品多少钱', false],
    ['推荐100元以内的商品，多少钱', false],
    ['总商品数量有多少', true],
    ['库存有几件商品', true],
  ])('classifies statistics without hiding price search cards: %s', async (prompt, summaryOnly) => {
    streamChatMock.mockResolvedValue(streamResponse(frame('result', {
      answer: '查询结果', data: [{ id: 1, name: '测试商品', price: 99, stock: 10 }],
      tool_calls: [{ name: 'search_products', arguments: {}, outcome: 'success' }], confirmation: null, reference: null,
    })))
    const store = useChatStore()
    await store.send(prompt)
    const results = store.latestAssistant!.results
    expect(results.kind).toBe('product')
    expect(results.kind === 'product' && !!results.summaryOnly).toBe(summaryOnly)
  })

  it.each(['executed', 'cancelled', 'unknown'] as const)('handles null clear-cart receipt only when executed: %s', async status => {
    const session = useSessionStore()
    session.$patch({ accessToken: 'jwt', authStatus: 'authenticated' })
    const store = useChatStore()
    const old = assistant('old-run')
    old.id = 'old-cart'
    old.results = { kind: 'cart', items: [{ cartId: 71, quantity: 1, price: 99 }] }
    const pending = pendingAssistant('clear_cart')
    pending.preserveScroll = true
    store.messages.push(old, pending)
    confirmActionMock.mockResolvedValue({ status, message: '操作回执', data: null })
    await store.confirm(true)
    expect(store.messages[0]).toMatchObject({ results: { kind: 'cart', items: status === 'executed' ? [] : [{ cartId: 71 }] } })
    expect(store.latestAssistant?.confirmationPhase).toBe(status)
    expect(store.messages[0]).toMatchObject({ results: status === 'unknown' ? { stale: true } : { feedback: '操作回执' } })
  })

  it('preserves the existing cart when clearing fails', async () => {
    const session = useSessionStore()
    session.$patch({ accessToken: 'jwt', authStatus: 'authenticated' })
    const store = useChatStore()
    const old = assistant('old-run')
    old.id = 'old-cart'
    old.results = { kind: 'cart', items: [{ cartId: 71, quantity: 1, price: 99 }] }
    store.messages.push(old, pendingAssistant('clear_cart'))
    confirmActionMock.mockRejectedValue(new Error('connection failed'))
    await store.confirm(true)
    expect(store.messages[0]).toMatchObject({ results: { items: [{ cartId: 71 }] } })
    expect(store.latestAssistant?.confirmationPhase).toBe('unknown')
  })

  it('updates existing panels when a verified mutation is followed by get_cart', () => {
    const store = useChatStore()
    const old = assistant('old-run')
    old.id = 'old-cart'
    old.results = { kind: 'cart', items: [{ cartId: 71, quantity: 1, price: 99 }] }
    const current = assistant('update-run')
    current.id = 'current'
    store.messages.push(old, current)
    store.activeRunId = 'update-run'
    store.finalizeRun('update-run', { answer: '已更新', data: [{ cartId: 71, quantity: 2, price: 99 }],
      tool_calls: [{ name: 'update_cart', arguments: {}, outcome: 'success' }, { name: 'get_cart', arguments: {}, outcome: 'success' }], confirmation: null, reference: null })
    expect(store.messages[0]).toMatchObject({ results: { items: [{ quantity: 2 }] } })
    expect(store.latestAssistant?.results.kind).toBe('none')
  })

  it('sends anonymous public chat even with the legacy global login flag', async () => {
    const session = useSessionStore()
    session.chatLoginRequired = true
    const store = useChatStore()
    streamChatMock.mockResolvedValue(streamResponse(frame('result', { answer: '推荐结果', tool_calls: [], data: null, confirmation: null, reference: null })))
    await store.send('推荐手机')
    expect(streamChatMock).toHaveBeenCalledOnce()
    expect(store.messages).toHaveLength(2)
    expect(session.pendingAction).toBeNull()
    expect(useViewStore().loginPanelOpen).toBe(false)
  })

  it.each([true, false])('syncs an existing cart after add without replaying the write: read success=%s', async success => {
    const session = useSessionStore()
    session.$patch({ accessToken: 'jwt', authStatus: 'authenticated' })
    const store = useChatStore()
    const old = assistant('old-run')
    old.id = 'old-cart'
    old.results = { kind: 'cart', items: [{ cartId: 71, productId: 8, quantity: 1, price: 99 }] }
    store.messages.push(old)
    if (success) vi.mocked(fetchCart).mockResolvedValue([{ cartId: 71, productId: 8, quantity: 2, price: 99 }, { cartId: 72, productId: 2, quantity: 1, price: 2999 }])
    else vi.mocked(fetchCart).mockRejectedValue(new Error('read unavailable'))
    streamChatMock.mockResolvedValue(streamResponse(frame('result', { answer: '已加购', tool_calls: [{ name: 'add_to_cart', arguments: {}, outcome: 'success' }], data: { cartId: 71, productId: 8, quantity: 2 }, confirmation: null, reference: null })))
    await store.send('加入购物车')
    expect(streamChatMock).toHaveBeenCalledOnce()
    expect(fetchCart).toHaveBeenCalledWith('jwt')
    const cart = store.messages[0] as AssistantMessage
    expect(cart.results).toMatchObject(success ? { kind: 'cart', stale: false, items: [{ quantity: 2 }, { cartId: 72 }] } : { kind: 'cart', stale: true, items: [{ quantity: 1 }] })
    expect(store.latestAssistant?.results.kind).toBe('none')
    expect(store.canSend).toBe(true)
  })

  it('disables stale cart mutations after an unverified add receipt', async () => {
    const store = useChatStore()
    const old = assistant('old-run')
    old.id = 'old-cart'
    old.results = { kind: 'cart', items: [{ cartId: 71, quantity: 1, price: 99 }] }
    store.messages.push(old)
    streamChatMock.mockResolvedValue(streamResponse(frame('result', { answer: '结果未知', tool_calls: [{ name: 'add_to_cart', arguments: {}, outcome: 'error' }], data: null, confirmation: null, reference: null })))
    await store.send('加入购物车')
    expect(store.messages[0]).toMatchObject({ results: { stale: true, items: [{ quantity: 1 }] } })
    expect(fetchCart).not.toHaveBeenCalled()
    expect(streamChatMock).toHaveBeenCalledOnce()
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

  it('retries a failed reply without duplicating the visible request', async () => {
    streamChatMock
      .mockResolvedValueOnce(new Response(null, { status: 503 }))
      .mockResolvedValueOnce(streamResponse(frame('result', {
        answer: '已找到订单',
        tool_calls: [],
        confirmation: null,
        data: null,
        reference: null,
      })))
    const store = useChatStore()

    await store.send('查看订单 8 的详情', '查看订单 ORD-8 的详情')
    expect(store.latestAssistant?.status?.text).toBe('服务暂时不可用，请稍后重试。')

    await store.retryLast()

    expect(store.messages).toHaveLength(2)
    expect(store.messages[0]).toMatchObject({ text: '查看订单 ORD-8 的详情' })
    expect(store.latestAssistant).toMatchObject({ text: '已找到订单', streamPhase: 'done' })
    expect(streamChatMock.mock.calls[1]?.[0]).toMatchObject({ message: '查看订单 8 的详情' })
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

  it('confirms the clicked older message and preserves the latest query', async () => {
    const session = useSessionStore()
    session.$patch({ accessToken: 'jwt', authStatus: 'authenticated' })
    const store = useChatStore()
    const removal = { ...pendingAssistant(), id: 'remove-message' }
    removal.confirmation = { token: 'remove-token', action: 'remove_from_cart', description: '移除书籍', arguments: { cart_id: 71 } }
    const latest = { ...assistant('query'), id: 'query-message', streamPhase: 'done' as const }
    store.messages.push(removal, latest)
    confirmActionMock.mockResolvedValue({ status: 'executed', message: '已移除书籍', data: [] })

    await store.confirm(true, removal.id)

    expect(confirmActionMock).toHaveBeenCalledWith({ session_id: session.sessionId, confirmation_token: 'remove-token', approved: true }, 'jwt')
    expect(store.messages[0]).toMatchObject({ confirmationPhase: 'executed', results: { kind: 'empty', emptyKind: 'cart' } })
    expect(store.latestAssistant?.id).toBe('query-message')
    expect(store.latestAssistant?.confirmationResult).toBeNull()
  })

  it('does not fall back to another action when the clicked message is missing', async () => {
    const session = useSessionStore()
    session.$patch({ accessToken: 'jwt', authStatus: 'authenticated' })
    const store = useChatStore()
    store.messages.push(pendingAssistant())
    await store.confirm(true, 'missing-message')
    expect(confirmActionMock).not.toHaveBeenCalled()
  })

  it('treats a rejected confirmation as a normal cancelled result', async () => {
    confirmActionMock.mockResolvedValue({
      status: 'cancelled',
      message: '已放弃本次操作，购物车和订单保持不变。',
      data: null,
    })
    const session = useSessionStore()
    session.$patch({ accessToken: 'jwt', authStatus: 'authenticated' })
    const store = useChatStore()
    store.messages.push(pendingAssistant('clear_cart'))

    await store.confirm(false)

    expect(store.latestAssistant?.confirmationPhase).toBe('cancelled')
    expect(store.latestAssistant?.confirmationResult?.message).toContain('购物车和订单保持不变')
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
