import { onScopeDispose, ref } from 'vue'
import type { Ref } from 'vue'

import { streamChat } from '../api/chat'
import { HttpError, normalizeErrorDetail } from '../lib/http'
import { flushSseBuffer, parseSseChunk } from '../lib/sse'
import type { ChatResponse } from '../types/api'
import type { RunPhase } from '../types/chat'
import type { StreamEvent } from '../types/stream'

export type ChatCancelReason = 'user' | 'rotate'

export interface SendChatStreamInput {
  message: string
  sessionId: string
  accessToken: string | null
  runId: string
}

export interface UseChatStream {
  send: (input: SendChatStreamInput) => Promise<ChatResponse | null>
  cancel: (reason?: ChatCancelReason) => void
  phase: Ref<RunPhase>
  events: Ref<StreamEvent[]>
  cancelReason: Ref<ChatCancelReason | null>
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

async function httpErrorFrom(response: Response): Promise<HttpError> {
  let payload: unknown = null
  const contentType = response.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) {
    try {
      payload = await response.json()
    } catch {
      payload = null
    }
  } else {
    try {
      const detail = await response.text()
      payload = detail ? { detail } : null
    } catch {
      payload = null
    }
  }

  const code = isRecord(payload) && typeof payload.error === 'string' ? payload.error : null
  return new HttpError(normalizeErrorDetail(payload, response.status), response.status, code, payload)
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError'
}

export function useChatStream(
  onEvent: (runId: string, event: StreamEvent) => void,
): UseChatStream {
  const phase = ref<RunPhase>('done')
  const events = ref<StreamEvent[]>([])
  const cancelReason = ref<ChatCancelReason | null>(null)
  let activeController: AbortController | null = null

  const deliver = (runId: string, event: StreamEvent): ChatResponse | null => {
    if (event.type !== 'progress') events.value.push(event)
    onEvent(runId, event)
    if (event.type === 'error') throw new Error(event.data.detail)
    return event.type === 'result' ? event.data : null
  }

  const send = async (input: SendChatStreamInput): Promise<ChatResponse | null> => {
    if (activeController) activeController.abort()

    const controller = new AbortController()
    activeController = controller
    cancelReason.value = null
    events.value = []
    phase.value = 'connecting'

    try {
      const response = await streamChat(
        { message: input.message, session_id: input.sessionId },
        input.accessToken,
        { signal: controller.signal },
      )
      if (!response.ok) throw await httpErrorFrom(response)
      if (!response.body) throw new Error('浏览器未提供可读取的流式响应。')

      phase.value = 'streaming'
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let result: ChatResponse | null = null

      while (true) {
        const chunk = await reader.read()
        if (activeController !== controller || controller.signal.aborted) return null
        if (chunk.done) break

        const parsed = parseSseChunk(buffer, decoder.decode(chunk.value, { stream: true }))
        buffer = parsed.buffer
        for (const event of parsed.events) {
          result = deliver(input.runId, event) ?? result
        }
      }

      const tail = `${decoder.decode()}${buffer}`
      for (const event of flushSseBuffer(tail)) {
        result = deliver(input.runId, event) ?? result
      }

      if (!result) throw new Error('流式响应意外结束。')
      phase.value = 'done'
      return result
    } catch (error: unknown) {
      if (controller.signal.aborted || isAbortError(error)) {
        if (activeController === controller) phase.value = 'cancelled'
        return null
      }
      if (activeController === controller) phase.value = 'error'
      throw error
    } finally {
      if (activeController === controller) activeController = null
    }
  }

  const cancel = (reason: ChatCancelReason = 'user'): void => {
    if (!activeController) return
    cancelReason.value = reason
    phase.value = 'cancelled'
    activeController.abort()
  }

  onScopeDispose(() => cancel('rotate'))

  return { send, cancel, phase, events, cancelReason }
}
