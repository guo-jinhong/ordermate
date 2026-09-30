import type {
  ChatRequest,
  ChatResponse,
  ClearConversationRequest,
  ClearConversationResponse,
  ConfirmRequest,
  ConfirmResponse,
} from '../types/api'
import { fetchJson } from '../lib/http'

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

export async function confirmAction(
  request: ConfirmPayload,
  accessToken: string | null,
  options: ChatApiOptions = {},
): Promise<ConfirmResponse> {
  return fetchJson<ConfirmResponse>('/confirm', {
    method: 'POST',
    body: JSON.stringify(request),
    accessToken,
    ...options,
  })
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
