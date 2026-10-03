import { defineStore } from 'pinia'

import { login as requestLogin, restoreSession } from '../api/auth'
import {
  clearStoredAuth,
  ensureSessionId,
  persistAuth,
  readStoredAuth,
  rotateSessionId,
} from '../lib/session'

export type AuthStatus = 'anonymous' | 'checking' | 'authenticated'

export interface PendingAction {
  prompt: string
  displayPrompt?: string
  label: string
}

export const useSessionStore = defineStore('session', {
  state: () => {
    const stored = readStoredAuth()

    return {
      accessToken: stored.accessToken,
      username: stored.username,
      sessionId: ensureSessionId(),
      authStatus: (stored.accessToken ? 'checking' : 'anonymous') as AuthStatus,
      chatLoginRequired: false,
      pendingAction: null as PendingAction | null,
    }
  },

  getters: {
    isAuthenticated: (state): boolean =>
      state.authStatus === 'authenticated' && Boolean(state.accessToken),
  },

  actions: {
    async login(username: string, password: string): Promise<void> {
      this.authStatus = 'checking'

      try {
        const response = await requestLogin({ username, password })
        this.accessToken = response.access_token
        this.username = username
        this.authStatus = 'authenticated'
        persistAuth(response.access_token, username)
      } catch (error: unknown) {
        clearStoredAuth()
        this.accessToken = null
        this.username = null
        this.authStatus = 'anonymous'
        throw error
      }
    },

    async restore(): Promise<boolean> {
      if (!this.accessToken) {
        this.authStatus = 'anonymous'
        return false
      }

      this.authStatus = 'checking'

      try {
        const response = await restoreSession(this.accessToken)
        if (!response.authenticated) {
          this.clear()
          return false
        }

        this.username = response.username
        this.authStatus = 'authenticated'
        persistAuth(this.accessToken, response.username)
        return true
      } catch {
        this.clear()
        return false
      }
    },

    clear(): void {
      clearStoredAuth()
      this.accessToken = null
      this.username = null
      this.authStatus = 'anonymous'
      this.pendingAction = null
    },

    rotateSession(): string {
      const sessionId = rotateSessionId()
      this.sessionId = sessionId
      return sessionId
    },

    requestLoginForAction(prompt: string, label: string, displayPrompt?: string): void {
      this.pendingAction = displayPrompt
        ? { prompt, displayPrompt, label }
        : { prompt, label }
    },

    consumePendingAction(): PendingAction | null {
      const pendingAction = this.pendingAction
      this.pendingAction = null
      return pendingAction
    },
  },
})
