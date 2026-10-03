import type {
  ChatRequest,
  ChatResponse,
  ClearConversationRequest,
  ClearConversationResponse,
  ConfirmRequest,
  ConfirmResponse,
} from '../types/api'
import { fetchJson, HttpError } from '../lib/http'

export type ChatRequestPayload = Omit<ChatRequest, 'access_token'>
export type ClearConversationPayload = Omit<ClearConversationRequest, 'access_token'>
export type ConfirmPayload = Omit<ConfirmRequest, 'access_token'>

export interface ChatApiOptions {
  fetchImpl?: typeof fetch
  signal?: AbortSignal
}

export async function sendChat(
  request: ChatRequestPayload,
  accessToken: string | null,
  options: ChatApiOptions = {},
): Promise<ChatResponse> {
  return fetchJson<ChatResponse>('/chat', {
    method: 'POST',
    body: JSON.stringify(request),
    accessToken,
    ...options,
  })
}

export async function streamChat(
  request: ChatRequestPayload,
  accessToken: string | null,
  options: ChatApiOptions = {},
): Promise<Response> {
  const fetchImpl = options.fetchImpl ?? fetch
  const headers = new Headers({
    Accept: 'text/event-stream',
    'Content-Type': 'application/json',
  })
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)

  const init: RequestInit = {
    method: 'POST',
    headers,
    body: JSON.stringify(request),
  }
  if (options.signal) init.signal = options.signal

  return fetchImpl('/chat/stream', init)
}

// 手动及异常恢复共用只读入口，不提交确认写请求。
export async function fetchOperationStatus(
  token: string, sessionId: string, accessToken: string, options: ChatApiOptions = {},
): Promise<Omit<ConfirmResponse, 'status'> & { status: ConfirmResponse['status'] | 'prepared' }> {
  return fetchJson('/operations/' + encodeURIComponent(token) + '?session_id=' + encodeURIComponent(sessionId), {
    accessToken, ...options, signal: options.signal ?? AbortSignal.timeout(10_000),
  })
}

export async function confirmAction(
  request: ConfirmPayload,
  accessToken: string | null,
  options: ChatApiOptions = {},
): Promise<ConfirmResponse> {
  try {
    return await fetchJson<ConfirmResponse>('/confirm', {
      method: 'POST',
      body: JSON.stringify(request),
      accessToken,
      ...options,
    })
  } catch (error) {
    // 回执丢失只查操作日志，绝不重发确认写请求。
    const uncertain = !(error instanceof HttpError) || error.status >= 500
    if (uncertain && accessToken) {
      try {
        const result = await fetchJson<Omit<ConfirmResponse, 'status'> & { status: ConfirmResponse['status'] | 'prepared' }>(
          '/operations/' + encodeURIComponent(request.confirmation_token) +
          '?session_id=' + encodeURIComponent(request.session_id),
          { accessToken, ...(options.fetchImpl ? { fetchImpl: options.fetchImpl } : {}), signal: AbortSignal.timeout(10_000) },
        )
        if (result.status !== 'prepared') return { ...result, status: result.status }
      } catch { /* 保留原始错误，UI 将其标为待核实。 */ }
    }
    throw error
  }
}

export async function clearConversation(
  request: ClearConversationPayload,
  accessToken: string | null,
  options: ChatApiOptions = {},
): Promise<ClearConversationResponse> {
  return fetchJson<ClearConversationResponse>('/conversation/clear', {
    method: 'POST',
    body: JSON.stringify(request),
    accessToken,
    ...options,
  })
}

// 写请求成功后只读回完整快照，不再次提交写操作。
export async function fetchCart(accessToken: string): Promise<unknown> {
  return fetchJson<unknown>('/cart', { accessToken, signal: AbortSignal.timeout(10_000) })
}
