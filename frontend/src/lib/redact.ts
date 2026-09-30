const REDACTED = '[已脱敏]'
const SENSITIVE_KEY = /pass(?:word)?|token|secret|authorization|cookie|api[-_]?key|access[-_]?token/i

function redactValue(value: unknown, key: string, seen: WeakMap<object, unknown>): unknown {
  if (SENSITIVE_KEY.test(key)) return REDACTED
  if (Array.isArray(value)) {
    const existing = seen.get(value)
    if (existing) return existing
    const copy: unknown[] = []
    seen.set(value, copy)
    value.forEach((item) => copy.push(redactValue(item, '', seen)))
    return copy
  }
  if (value !== null && typeof value === 'object') {
    const existing = seen.get(value)
    if (existing) return existing
    const copy: Record<string, unknown> = {}
    seen.set(value, copy)
    Object.entries(value).forEach(([childKey, child]) => {
      copy[childKey] = redactValue(child, childKey, seen)
    })
    return copy
  }
  return value
}

export function redactSensitive(value: unknown): unknown {
  return redactValue(value, '', new WeakMap<object, unknown>())
}
