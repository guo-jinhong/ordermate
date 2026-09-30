export const SESSION_STORAGE_KEYS = {
  token: 'ordermate_token',
  username: 'ordermate_username',
  sessionId: 'ordermate_session',
} as const

export interface StoredAuth {
  accessToken: string | null
  username: string | null
}

export type SessionIdFactory = () => string

function browserSessionStorage(): Storage {
  return globalThis.sessionStorage
}

export function createSessionId(factory: SessionIdFactory = () => crypto.randomUUID()): string {
  return factory()
}

export function ensureSessionId(
  storage: Storage = browserSessionStorage(),
  factory?: SessionIdFactory,
): string {
  const stored = storage.getItem(SESSION_STORAGE_KEYS.sessionId)?.trim()
  if (stored) return stored

  const sessionId = createSessionId(factory)
  storage.setItem(SESSION_STORAGE_KEYS.sessionId, sessionId)
  return sessionId
}

export function rotateSessionId(
  storage: Storage = browserSessionStorage(),
  factory?: SessionIdFactory,
): string {
  const sessionId = createSessionId(factory)
  storage.setItem(SESSION_STORAGE_KEYS.sessionId, sessionId)
  return sessionId
}

export function readStoredAuth(storage: Storage = browserSessionStorage()): StoredAuth {
  return {
    accessToken: storage.getItem(SESSION_STORAGE_KEYS.token),
    username: storage.getItem(SESSION_STORAGE_KEYS.username),
  }
}

export function persistAuth(
  accessToken: string,
  username: string | null,
  storage: Storage = browserSessionStorage(),
): void {
  storage.setItem(SESSION_STORAGE_KEYS.token, accessToken)
  if (username) storage.setItem(SESSION_STORAGE_KEYS.username, username)
  else storage.removeItem(SESSION_STORAGE_KEYS.username)
}

export function clearStoredAuth(storage: Storage = browserSessionStorage()): void {
  storage.removeItem(SESSION_STORAGE_KEYS.token)
  storage.removeItem(SESSION_STORAGE_KEYS.username)
}
