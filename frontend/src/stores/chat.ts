import { computed, onScopeDispose, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  clearConversation as requestClearConversation,
  confirmAction as requestConfirmAction,
  fetchCart,
  fetchOperationStatus,
} from '../api/chat'
import { useChatStream } from '../composables/useChatStream'
import { isCartRecord, resolveResultPayload } from '../lib/guards'
import { catalogQuery, customerCopy } from '../lib/catalogCopy'
import { customerErrorMessage, HttpError } from '../lib/http'
import { toolStatusCopy } from '../lib/labels'
import type { ChatResponse } from '../types/api'
import type { AssistantMessage, ChatMessage } from '../types/chat'
import type { StreamEvent } from '../types/stream'
import { useInspectorStore } from './inspector'
import { useViewStore } from './view'
import { useSessionStore } from './session'

const RATE_LIMIT_BACKOFF_MS = 5_000

// 金额询问中的“多少钱”不属于商品数量统计。
function isQuantityQuery(prompt: string): boolean {
  const quantityText = prompt.replace(/多少钱|多少元/g, '')
  return /多少|几[件种个]|总数|总数量|总商品数量|商品总数量|(?:商品|库存|购物车)(?:的)?数量|数量(?:是多少|有多少)/.test(quantityText)
}

function isMutationPrompt(prompt: string): boolean {
  return /修改|改为|增加|减少|加入|移除|清空/.test(prompt)
}

function messageId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`
}

function emptyAssistant(runId: string): AssistantMessage {
  return {
    id: messageId('assistant'),
    role: 'assistant',
    runId,
    at: Date.now(),
    text: '',
    status: { text: '正在为您连接…', tone: 'loading' },
    reference: null,
    results: { kind: 'none' },
    confirmation: null,
    confirmationPhase: 'pending',
    confirmationResult: null,
    streamPhase: 'connecting',
  }
}

export const useChatStore = defineStore('chat', () => {
  const session = useSessionStore()
  const inspector = useInspectorStore()
  const view = useViewStore()
  const messages = ref<ChatMessage[]>([])
  const activeRunId = ref<string | null>(null)
  const sending = ref(false)
  const cartSyncing = ref(false)
  let cartSyncPromise: Promise<void> | null = null
  const lastError = ref<string | null>(null)
  const backoffUntil = ref<number | null>(null)
  let lastSubmitted: { prompt: string; displayText: string | undefined; preserveScroll?: boolean } | null = null
  let backoffTimer: ReturnType<typeof setTimeout> | null = null

  const hasConversation = computed(() => messages.value.length > 0)
  const latestAssistant = computed(() =>
    [...messages.value].reverse().find(
      (message): message is AssistantMessage => message.role === 'assistant',
    ) ?? null,
  )
  const operationVerifying = ref(false)
  const confirmationSubmitting = computed(() => messages.value.some(
    message => message.role === 'assistant' && message.confirmationPhase === 'submitting',
  ))
  const canSend = computed(
    () => !sending.value && !cartSyncing.value && !operationVerifying.value && !confirmationSubmitting.value && (backoffUntil.value == null || backoffUntil.value <= Date.now()),
  )

  function assistantFor(runId: string): AssistantMessage | null {
    return messages.value.find(
      (message): message is AssistantMessage =>
        message.role === 'assistant' && message.runId === runId,
    ) ?? null
  }

  // 仅使用后端核验过的完整购物车更新旧面板，不对写请求做乐观更新。
  function refreshCartPanels(data: unknown, action: string | undefined, currentId: string): boolean {
    if (!['update_cart', 'update_cart_items', 'remove_from_cart', 'clear_cart', 'get_cart'].includes(action ?? '')
      || !Array.isArray(data) || !data.every(isCartRecord)) return false
    let updated = false
    for (const message of messages.value) {
      if (message.role !== 'assistant' || message.id === currentId || message.results.kind !== 'cart') continue
      message.results = { ...message.results, items: data, preserveState: true, stale: false }
      updated = true
    }
    return updated
  }

  function cartFeedback(text: string, stale?: boolean): void {
    for (const message of messages.value) {
      if (message.role === 'assistant' && message.results.kind === 'cart') {
        message.results.feedback = text
        if (stale != null) message.results.stale = stale
      }
    }
  }

  async function syncAddedCart(currentId: string): Promise<void> {
    const token = session.accessToken
    const sessionId = session.sessionId
    if (!token) { cartFeedback('购物车待刷新，请登录后刷新。', true); return }
    cartSyncing.value = true
    cartFeedback('正在更新购物车…', true)
    try {
      const snapshot = await fetchCart(token)
      if (session.accessToken !== token || session.sessionId !== sessionId) return
      if (!Array.isArray(snapshot) || !snapshot.every(isCartRecord)) throw new Error('Invalid cart snapshot')
      refreshCartPanels(snapshot, 'get_cart', currentId)
      cartFeedback('购物车已更新。', false)
    } catch {
      if (session.accessToken === token && session.sessionId === sessionId) {
        cartFeedback('商品已加入购物车，页面暂时无法更新，请刷新购物车查看。', true)
      }
    } finally {
      cartSyncing.value = false
    }
  }

  function finalizeRun(runId: string, response: ChatResponse): void {
    if (runId !== activeRunId.value) return
    const assistant = assistantFor(runId)
    if (!assistant) return

    assistant.text = response.answer
    assistant.reference = response.reference
    assistant.results = resolveResultPayload(response.data, response.tool_calls)
    const lastTool = response.tool_calls.at(-1)
    const mutationTool = lastTool?.name === 'get_cart'
      ? [...response.tool_calls].reverse().find(call => ['update_cart', 'update_cart_items', 'remove_from_cart'].includes(call.name) && call.outcome === 'success')
      : lastTool
    const prompt = lastSubmitted?.prompt ?? ''
    if (!response.confirmation && lastTool?.outcome === 'success'
      && mutationTool?.outcome === 'success'
      && (mutationTool.name !== 'get_cart' || assistant.preserveScroll)
      && refreshCartPanels(response.data, mutationTool.name, assistant.id)) {
      assistant.results = { kind: 'none' }
    } else if (assistant.results.kind === 'cart' && !isMutationPrompt(prompt)
      && (isQuantityQuery(prompt) || /合计|总价|总金额|多少钱/.test(prompt))) {
      assistant.results.summaryOnly = true
    }
    if (assistant.results.kind === 'product' && assistant.results.context.detail !== true
      && !isMutationPrompt(prompt) && isQuantityQuery(prompt) && /商品|库存/.test(prompt)) {
      assistant.results.summaryOnly = true
    }
    if (lastTool?.name === 'get_cart' && lastTool.outcome === 'success' && !response.confirmation) {
      refreshCartPanels(response.data, 'get_cart', assistant.id)
    }
    if (assistant.preserveScroll) cartFeedback(response.answer)
    if (lastTool?.name === 'add_to_cart' && lastTool.outcome === 'success' && !response.confirmation) {
      // 加购回执只包含单个商品，不将它当成整个购物车。
      assistant.results = { kind: 'none' }
      if (messages.value.some(message => message.role === 'assistant' && message.id !== assistant.id && message.results.kind === 'cart')) {
        cartSyncPromise = syncAddedCart(assistant.id)
      }
    } else if (lastTool?.name === 'add_to_cart' && lastTool.outcome === 'error' && !response.confirmation) {
      cartFeedback('暂时无法确认商品是否已加入，请刷新购物车查看，暂时不要重复添加。', true)
    } else if (lastTool?.outcome === 'error' && ['update_cart', 'update_cart_items', 'remove_from_cart', 'clear_cart'].includes(lastTool.name) && !response.confirmation) {
      cartFeedback('暂时无法确认操作结果，请刷新购物车查看，暂时不要重复提交。', true)
    }
    assistant.confirmation = response.confirmation
    assistant.confirmationPhase = 'pending'
    assistant.status = null
    assistant.streamPhase = 'done'
    sending.value = false
    activeRunId.value = null
    inspector.finishRun(runId, 'done')
  }

  function failRun(runId: string, message: string): void {
    if (runId !== activeRunId.value) return
    const assistant = assistantFor(runId)
    if (assistant) {
      assistant.status = { text: message, tone: 'error' }
      assistant.streamPhase = 'error'
    }
    if (assistant?.preserveScroll) cartFeedback(`${message} 请刷新购物车后继续操作。`, true)
    lastError.value = message
    sending.value = false
    activeRunId.value = null
    inspector.finishRun(runId, 'error')
  }

  function applyStreamEvent(runId: string, event: StreamEvent): void {
    if (runId !== activeRunId.value) return
    const assistant = assistantFor(runId)
    if (!assistant) return
    inspector.recordEvent(runId, event)

    switch (event.type) {
      case 'started':
      case 'progress':
        assistant.status = { text: event.data.message, tone: 'loading' }
        assistant.streamPhase = 'streaming'
        break
      case 'reference':
        assistant.reference = event.data
        break
      case 'clarification':
        assistant.status = {
          text: event.data.message ?? '需要补充信息后才能继续。',
          tone: 'warning',
        }
        break
      case 'tool_error':
        assistant.status = { text: event.data.error ?? '暂时无法处理您的请求，请稍后再试。', tone: 'error' }
        break
      case 'tool':
        {
          const copy = toolStatusCopy(event.data.name, event.data.outcome)
          assistant.status = { text: copy.message, tone: copy.tone }
        }
        break
      case 'result':
        finalizeRun(runId, event.data)
        break
      case 'error':
        failRun(runId, event.data.detail)
        break
      case 'llm_trace':
      case 'confirmation_required':
        break
    }
  }

  const stream = useChatStream(applyStreamEvent)

  function setBackoff(): void {
    const until = Date.now() + RATE_LIMIT_BACKOFF_MS
    backoffUntil.value = until
    if (backoffTimer) clearTimeout(backoffTimer)
    backoffTimer = setTimeout(() => {
      if (backoffUntil.value === until) backoffUntil.value = null
    }, RATE_LIMIT_BACKOFF_MS)
  }

  async function send(text: string, displayText?: string, options: { preserveScroll?: boolean } = {}): Promise<void> {
    const prompt = text.trim()
    if (!prompt || !canSend.value) return
    // 公共聊天可匿名发送；个人数据和写操作继续由后端工具鉴权。
    const visiblePrompt = customerCopy(displayText?.trim() || prompt)
    lastSubmitted = { prompt, displayText, preserveScroll: options.preserveScroll ?? false }

    const runId = crypto.randomUUID()
    messages.value.push(
      { id: messageId('user'), role: 'user', text: visiblePrompt, at: Date.now(), preserveScroll: options.preserveScroll ?? false },
      { ...emptyAssistant(runId), preserveScroll: options.preserveScroll ?? false },
    )
    activeRunId.value = runId
    sending.value = true
    lastError.value = null
    inspector.startRun(runId, prompt)
    if (options.preserveScroll) cartFeedback('正在更新购物车…')

    try {
      const response = await stream.send({
        message: catalogQuery(prompt),
        sessionId: session.sessionId,
        accessToken: session.accessToken,
        runId,
      })
      if (response) finalizeRun(runId, response)
      if (cartSyncPromise) { await cartSyncPromise; cartSyncPromise = null }
    } catch (error: unknown) {
      if (error instanceof HttpError && error.status === 401) {
        session.clear()
        session.requestLoginForAction(prompt, '重新发送消息', displayText)
        view.openAccount()
      }
      if (error instanceof HttpError && error.status === 429) setBackoff()
      failRun(runId, customerErrorMessage(error, '消息发送失败，请稍后重试。'))
    }
  }

  async function retryLast(): Promise<void> {
    if (!lastSubmitted || !canSend.value) return
    const latest = messages.value.at(-1)
    const previous = messages.value.at(-2)
    if (latest?.role !== 'assistant' || latest.streamPhase !== 'error' || previous?.role !== 'user') return
    const { prompt, displayText, preserveScroll } = lastSubmitted
    messages.value.splice(-2)
    await send(prompt, displayText, { preserveScroll: preserveScroll ?? false })
  }

  function cancel(reason: 'user' | 'rotate' = 'user'): void {
    const runId = activeRunId.value
    if (!runId) return
    stream.cancel(reason)
    const assistant = assistantFor(runId)
    if (assistant) {
      assistant.status = { text: reason === 'user' ? '已停止生成。' : '会话已切换。', tone: 'warning' }
      assistant.streamPhase = 'cancelled'
    }
    sending.value = false
    activeRunId.value = null
    inspector.finishRun(runId, 'cancelled')
  }

  async function confirm(approved: boolean, targetMessageId?: string): Promise<void> {
    if (sending.value || operationVerifying.value || confirmationSubmitting.value) return
    // 确认卡片绑定所属消息，继续聊天后也不会确认错操作。
    const assistant = targetMessageId == null ? latestAssistant.value : messages.value.find(
      (message): message is AssistantMessage => message.role === 'assistant' && message.id === targetMessageId,
    )
    const confirmation = assistant?.confirmation
    if (!assistant || !confirmation || assistant.confirmationPhase !== 'pending') return
    if (confirmation.expires_at && Date.now() >= Date.parse(confirmation.expires_at)) {
      assistant.confirmationPhase = 'failed'
      assistant.confirmationResult = { message: '本次确认已过期，请重新发起操作。', data: null }
      lastError.value = assistant.confirmationResult.message
      return
    }

    if (!session.accessToken) {
      assistant.confirmationPhase = 'failed'
      assistant.confirmationResult = { message: '登录状态已失效，请重新登录。', data: null }
      lastError.value = assistant.confirmationResult.message
      return
    }

    assistant.confirmationPhase = 'submitting'
    assistant.confirmationResult = null

    try {
      const response = await requestConfirmAction(
        {
          session_id: session.sessionId,
          confirmation_token: confirmation.token,
          approved,
        },
        session.accessToken,
      )
      assistant.confirmationPhase = response.status
      assistant.confirmationResult = { message: response.message, data: response.data }
      lastError.value = null

      // 清空成功的接口返回 null，执行成功回执对应完整的空购物车。
      if (response.status === 'executed' && (response.data != null || confirmation.action === 'clear_cart')) {
        const resultData = confirmation.action === 'clear_cart' && response.data == null ? [] : response.data
        const updatedCart = refreshCartPanels(resultData, confirmation.action, assistant.id)
        assistant.results = updatedCart ? { kind: 'none' } : resolveResultPayload(resultData, [
          {
            name: confirmation.action,
            arguments: confirmation.arguments,
            outcome: 'success',
          },
        ])
      }
      if (assistant.preserveScroll) cartFeedback(response.message)
      if (response.status === 'unknown' && ['clear_cart', 'remove_from_cart', 'update_cart', 'update_cart_items'].includes(confirmation.action)) {
        cartFeedback('暂时无法确认操作结果，请刷新购物车查看，暂时不要重复提交。', true)
      }
    } catch (error: unknown) {
      const uncertain = !(error instanceof HttpError) || error.status >= 500
      const message = uncertain
        ? '本次操作结果暂时无法确认，请先查看购物车或订单，暂时不要重复提交。'
        : customerErrorMessage(error, '本次操作未完成。')
      assistant.confirmationPhase = uncertain ? 'unknown' : 'failed'
      assistant.confirmationResult = { message, data: null }
      lastError.value = message
      if (assistant.preserveScroll) cartFeedback(message)
      if (error instanceof HttpError && error.status === 401) session.clear()
      if (error instanceof HttpError && error.status === 429) setBackoff()
    }
  }

  async function verifyOperation(targetMessageId: string): Promise<void> {
    if (!canSend.value) return
    const assistant = messages.value.find((message): message is AssistantMessage =>
      message.role === 'assistant' && message.id === targetMessageId)
    if (!assistant?.confirmation || assistant.confirmationPhase !== 'unknown') return
    if (!session.accessToken) {
      lastError.value = '请先登录后再核实操作结果。'
      return
    }
    const sessionId = session.sessionId
    operationVerifying.value = true
    try {
      const response = await fetchOperationStatus(assistant.confirmation.token, sessionId, session.accessToken)
      if (sessionId !== session.sessionId) return
      assistant.confirmationPhase = response.status === 'prepared' ? 'unknown' : response.status
      assistant.confirmationResult = { message: response.message, data: response.data }
      lastError.value = null
      if (response.status === 'executed' && (response.data != null || assistant.confirmation.action === 'clear_cart')) {
        const resultData = assistant.confirmation.action === 'clear_cart' && response.data == null ? [] : response.data
        const updatedCart = refreshCartPanels(resultData, assistant.confirmation.action, assistant.id)
        assistant.results = updatedCart ? { kind: 'none' } : resolveResultPayload(resultData, [{
          name: assistant.confirmation.action, arguments: assistant.confirmation.arguments, outcome: 'success',
        }])
      }
    } catch (error: unknown) {
      if (sessionId !== session.sessionId) return
      const message = customerErrorMessage(error, '暂时无法核实操作结果，请稍后再查询，暂时不要重复提交。')
      assistant.confirmationResult = { message, data: null }
      lastError.value = message
      if (error instanceof HttpError && error.status === 401) session.clear()
      if (error instanceof HttpError && error.status === 429) setBackoff()
    } finally {
      operationVerifying.value = false
    }
  }

  async function clearConversation(): Promise<boolean> {
    cancel('rotate')
    const previousSessionId = session.sessionId
    let serverCleared = false
    try {
      const response = await requestClearConversation(
        { session_id: previousSessionId },
        session.accessToken,
      )
      serverCleared = response.cleared
    } catch {
      serverCleared = false
    } finally {
      session.rotateSession()
      cartSyncing.value = false
      messages.value = []
      lastError.value = null
      lastSubmitted = null
      inspector.reset()
    }
    return serverCleared
  }

  onScopeDispose(() => {
    if (backoffTimer) clearTimeout(backoffTimer)
    stream.cancel('rotate')
  })

  return {
    messages,
    activeRunId,
    sending,
    cartSyncing,
    lastError,
    backoffUntil,
    hasConversation,
    latestAssistant,
    canSend,
    send,
    retryLast,
    cancel,
    applyStreamEvent,
    finalizeRun,
    failRun,
    confirm,
    verifyOperation,
    clearConversation,
  }
})
