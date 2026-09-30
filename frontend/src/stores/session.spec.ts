import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { login, restoreSession } from '../api/auth'
import { SESSION_STORAGE_KEYS } from '../lib/session'
import { useSessionStore } from './session'

vi.mock('../api/auth', () => ({
  login: vi.fn(),
  restoreSession: vi.fn(),
}))

const loginMock = vi.mocked(login)
const restoreSessionMock = vi.mocked(restoreSession)

describe('session store', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.clearAllMocks()
    setActivePinia(createPinia())
  })

  it('hydrates stored auth and reuses the existing session id', () => {
    sessionStorage.setItem(SESSION_STORAGE_KEYS.token, 'stored-jwt')
    sessionStorage.setItem(SESSION_STORAGE_KEYS.username, 'stored-user')
    sessionStorage.setItem(SESSION_STORAGE_KEYS.sessionId, 'session-1')

    const store = useSessionStore()

    expect(store.$state).toMatchObject({
      accessToken: 'stored-jwt',
      username: 'stored-user',
      sessionId: 'session-1',
      authStatus: 'checking',
    })
    expect(store.isAuthenticated).toBe(false)
  })

  it('logs in and persists the authenticated state', async () => {
    loginMock.mockResolvedValue({ access_token: 'fresh-jwt', token_type: 'bearer' })
    const store = useSessionStore()

    await store.login('testuser', 'password')

    expect(loginMock).toHaveBeenCalledWith({ username: 'testuser', password: 'password' })
    expect(store.isAuthenticated).toBe(true)
    expect(store.username).toBe('testuser')
    expect(sessionStorage.getItem(SESSION_STORAGE_KEYS.token)).toBe('fresh-jwt')
  })

  it('keeps a pending action available when login fails', async () => {
    loginMock.mockRejectedValue(new Error('invalid credentials'))
    const store = useSessionStore()
    store.requestLoginForAction('查看我的订单', '订单查询')

    await expect(store.login('testuser', 'wrong')).rejects.toThrow('invalid credentials')

    expect(store.authStatus).toBe('anonymous')
    expect(store.pendingAction).toEqual({ prompt: '查看我的订单', label: '订单查询' })
    expect(sessionStorage.getItem(SESSION_STORAGE_KEYS.token)).toBeNull()
  })

  it('restores valid auth and clears invalid auth without changing the session id', async () => {
    sessionStorage.setItem(SESSION_STORAGE_KEYS.token, 'stored-jwt')
    sessionStorage.setItem(SESSION_STORAGE_KEYS.sessionId, 'session-1')
    restoreSessionMock.mockResolvedValueOnce({ authenticated: true, username: 'testuser' })
    const store = useSessionStore()

    await expect(store.restore()).resolves.toBe(true)
    expect(store.isAuthenticated).toBe(true)
    expect(store.username).toBe('testuser')

    restoreSessionMock.mockRejectedValueOnce(new Error('expired'))
    await expect(store.restore()).resolves.toBe(false)
    expect(store.authStatus).toBe('anonymous')
    expect(store.accessToken).toBeNull()
    expect(store.sessionId).toBe('session-1')
    expect(sessionStorage.getItem(SESSION_STORAGE_KEYS.sessionId)).toBe('session-1')
  })

  it('rotates the session and consumes a pending action only once', () => {
    const store = useSessionStore()
    const previousSessionId = store.sessionId
    store.requestLoginForAction('清空购物车', '购物车操作')

    expect(store.consumePendingAction()).toEqual({ prompt: '清空购物车', label: '购物车操作' })
    expect(store.consumePendingAction()).toBeNull()
    expect(store.rotateSession()).not.toBe(previousSessionId)
    expect(sessionStorage.getItem(SESSION_STORAGE_KEYS.sessionId)).toBe(store.sessionId)
  })
})
