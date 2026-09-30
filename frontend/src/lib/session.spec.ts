import { beforeEach, describe, expect, it } from 'vitest'

import {
  clearStoredAuth,
  ensureSessionId,
  persistAuth,
  readStoredAuth,
  rotateSessionId,
  SESSION_STORAGE_KEYS,
} from './session'

describe('session helpers', () => {
  beforeEach(() => sessionStorage.clear())

  it('creates and then reuses a session id', () => {
    expect(ensureSessionId(sessionStorage, () => 'session-1')).toBe('session-1')
    expect(ensureSessionId(sessionStorage, () => 'session-2')).toBe('session-1')
  })

  it('rotates and persists the session id', () => {
    expect(rotateSessionId(sessionStorage, () => 'session-next')).toBe('session-next')
    expect(sessionStorage.getItem(SESSION_STORAGE_KEYS.sessionId)).toBe('session-next')
  })

  it('persists and clears auth without clearing the session id', () => {
    sessionStorage.setItem(SESSION_STORAGE_KEYS.sessionId, 'session-1')
    persistAuth('jwt', 'testuser', sessionStorage)
    expect(readStoredAuth(sessionStorage)).toEqual({ accessToken: 'jwt', username: 'testuser' })

    clearStoredAuth(sessionStorage)
    expect(readStoredAuth(sessionStorage)).toEqual({ accessToken: null, username: null })
    expect(sessionStorage.getItem(SESSION_STORAGE_KEYS.sessionId)).toBe('session-1')
  })
})
