import { computed, onScopeDispose, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  clearConversation as requestClearConversation,
  confirmAction as requestConfirmAction,
} from '../api/chat'
import { useChatStream } from '../composables/useChatStream'
import { resolveResultPayload } from '../lib/guards'
import { catalogQuery, customerCopy } from '../lib/catalogCopy'
import { HttpError } from '../lib/http'
import { toolStatusCopy } from '../lib/labels'
import type { ChatResponse } from '../types/api'
import type { AssistantMessage, ChatMessage } from '../types/chat'
import type { StreamEvent } from '../types/stream'
import { useInspectorStore } from './inspector'
import { useSessionStore } from './session'

const RATE_LIMIT_BACKOFF_MS = 5_000

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
    status: { text: '正在连接 Agent…', tone: 'loading' },
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
  const messages = ref<ChatMessage[]>([])
  const activeRunId = ref<string | null>(null)
  const sending = ref(false)
  const lastError = ref<string | null>(null)
  const backoffUntil = ref<number | null>(null)
  let backoffTimer: ReturnType<typeof setTimeout> | null = null

  const hasConversation = computed(() => messages.value.length > 0)
  const latestAssistant = computed(() =>
    [...messages.value].reverse().find(
      (message): message is AssistantMessage => message.role === 'assistant',
    ) ?? null,
  )
  const canSend = computed(
    () => !sending.value && (backoffUntil.value == null || backoffUntil.value <= Date.now()),
  )

  function assistantFor(runId: string): AssistantMessage | null {
    return messages.value.find(
      (message): message is AssistantMessage =>
        message.role === 'assistant' && message.runId === runId,
    ) ?? null
  }

  function finalizeRun(runId: string, response: ChatResponse): void {
    if (runId !== activeRunId.value) return
    const assistant = assistantFor(runId)
    if (!assistant) return

    assistant.text = response.answer
    assistant.reference = response.reference
    assistant.results = resolveResultPayload(response.data, response.tool_calls)
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
        assistant.status = { text: event.data.error ?? '业务工具执行失败。', tone: 'error' }
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

  async function send(text: string, displayText?: string): Promise<void> {
    const prompt = text.trim()
    if (!prompt || !canSend.value) return
    const visiblePrompt = customerCopy(displayText?.trim() || prompt)

    const runId = crypto.randomUUID()
    messages.value.push(
      { id: messageId('user'), role: 'user', text: visiblePrompt, at: Date.now() },
      emptyAssistant(runId),
    )
    activeRunId.value = runId
    sending.value = true
    lastError.value = null
    inspector.startRun(runId, prompt)

    try {
      const response = await stream.send({
        message: catalogQuery(prompt),
        sessionId: session.sessionId,
        accessToken: session.accessToken,
        runId,
      })
      if (response) finalizeRun(runId, response)
    } catch (error: unknown) {
      if (error instanceof HttpError && error.status === 401) session.clear()
      if (error instanceof HttpError && error.status === 429) setBackoff()
      failRun(runId, error instanceof Error ? error.message : '消息发送失败，请稍后重试。')
    }
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

  async function confirm(approved: boolean): Promise<void> {
    const assistant = latestAssistant.value
    const confirmation = assistant?.confirmation
    if (!assistant || !confirmation || assistant.confirmationPhase !== 'pending') return

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

      if (response.status === 'executed' && response.data != null) {
        assistant.results = resolveResultPayload(response.data, [
          {
            name: confirmation.action,
            arguments: confirmation.arguments,
            outcome: 'success',
          },
        ])
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : '确认操作失败，请稍后重试。'
      assistant.confirmationPhase = 'failed'
      assistant.confirmationResult = { message, data: null }
      lastError.value = message
      if (error instanceof HttpError && error.status === 401) session.clear()
      if (error instanceof HttpError && error.status === 429) setBackoff()
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
      messages.value = []
      lastError.value = null
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
    lastError,
    backoffUntil,
    hasConversation,
    latestAssistant,
    canSend,
    send,
    cancel,
    applyStreamEvent,
    finalizeRun,
    failRun,
    confirm,
    clearConversation,
  }
})
