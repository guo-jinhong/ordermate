export interface FetchJsonOptions extends RequestInit {
  accessToken?: string | null
  fetchImpl?: typeof fetch
}

export class HttpError extends Error {
  readonly status: number
  readonly code: string | null
  readonly payload: unknown

  constructor(message: string, status: number, code: string | null, payload: unknown) {
    super(message)
    this.name = 'HttpError'
    this.status = status
    this.code = code
    this.payload = payload
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function validationMessage(item: unknown): string | null {
  if (!isRecord(item) || typeof item.msg !== 'string') return null

  const location = Array.isArray(item.loc)
    ? item.loc.filter((part): part is string | number =>
        typeof part === 'string' || typeof part === 'number',
      )
    : []
  const field = location.at(-1)
  return field == null ? item.msg : `${String(field)}：${item.msg}`
}

export function normalizeErrorDetail(payload: unknown, status?: number): string {
  if (status != null && status >= 500) {
    const detail = isRecord(payload) && typeof payload.detail === 'string' ? payload.detail : ''
    if (/重复提交|重复下单/.test(detail)) {
      return '本次操作结果暂时无法确认，请先查看购物车或订单，暂时不要重复提交。'
    }
    return '服务暂时不可用，请稍后重试。'
  }
  if (isRecord(payload)) {
    if (typeof payload.detail === 'string' && payload.detail.trim()) {
      return payload.detail
    }

    if (Array.isArray(payload.detail)) {
      const messages = payload.detail
        .map(validationMessage)
        .filter((message): message is string => message !== null)
      if (messages.length > 0) return messages.join('；')
    }

    if (typeof payload.message === 'string' && payload.message.trim()) {
      return payload.message
    }
  }

  if (status === 401) return '登录信息无效，请重新登录。'
  if (status === 403) return '当前账号没有权限执行此操作。'
  if (status === 429) return '操作太频繁，请稍后再试。'
  return '请求未完成，请稍后重试。'
}

export function customerErrorMessage(error: unknown, fallback = '请求未完成，请稍后重试。'): string {
  if (error instanceof TypeError) return '连接失败，请检查网络后重试。'
  return error instanceof Error ? error.message : fallback
}

async function readErrorPayload(response: Response): Promise<unknown> {
  const contentType = response.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) {
    try {
      return await response.json()
    } catch {
      return null
    }
  }

  try {
    const text = await response.text()
    return text ? { detail: text } : null
  } catch {
    return null
  }
}

export async function fetchJson<T>(
  input: RequestInfo | URL,
  options: FetchJsonOptions = {},
): Promise<T> {
  const { accessToken, fetchImpl = fetch, ...requestInit } = options
  const headers = new Headers(requestInit.headers)
  headers.set('Accept', 'application/json')
  if (requestInit.body != null && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)

  const response = await fetchImpl(input, { ...requestInit, headers })
  if (!response.ok) {
    const payload = await readErrorPayload(response)
    const code = isRecord(payload) && typeof payload.error === 'string' ? payload.error : null
    throw new HttpError(normalizeErrorDetail(payload, response.status), response.status, code, payload)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}
