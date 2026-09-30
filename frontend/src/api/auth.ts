import type { AuthSessionResponse, LoginRequest, LoginResponse } from '../types/api'
import { fetchJson } from '../lib/http'

export async function login(
  credentials: LoginRequest,
  fetchImpl: typeof fetch = fetch,
): Promise<LoginResponse> {
  return fetchJson<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(credentials),
    fetchImpl,
  })
}

export async function restoreSession(
  accessToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<AuthSessionResponse> {
  return fetchJson<AuthSessionResponse>('/auth/session', {
    method: 'POST',
    accessToken,
    fetchImpl,
  })
}
