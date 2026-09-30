import { onMounted, onUnmounted, readonly, ref, shallowRef } from 'vue'
import type { DeepReadonly, Ref, ShallowRef } from 'vue'

import { fetchHealth } from '../api/system'
import type { HealthResponse } from '../types/api'

export type HealthStatus = 'checking' | 'online' | 'degraded' | 'offline'

export interface UseHealthPollOptions {
  intervalMs?: number
  load?: () => Promise<HealthResponse>
}

export interface UseHealthPoll {
  health: DeepReadonly<ShallowRef<HealthResponse | null>>
  status: DeepReadonly<Ref<HealthStatus>>
  error: DeepReadonly<Ref<string | null>>
  refresh: () => Promise<void>
  start: () => void
  stop: () => void
}

const DEFAULT_INTERVAL_MS = 30_000

export function useHealthPoll(options: UseHealthPollOptions = {}): UseHealthPoll {
  const health = shallowRef<HealthResponse | null>(null)
  const status = ref<HealthStatus>('checking')
  const error = ref<string | null>(null)
  const intervalMs = options.intervalMs ?? DEFAULT_INTERVAL_MS
  const load = options.load ?? fetchHealth

  let timer: ReturnType<typeof setInterval> | null = null
  let inFlight: Promise<void> | null = null
  let generation = 0

  const refresh = (): Promise<void> => {
    if (inFlight) return inFlight

    const requestGeneration = generation
    status.value = health.value ? status.value : 'checking'
    inFlight = load()
      .then((response) => {
        if (requestGeneration !== generation) return
        health.value = response
        status.value = response.status === 'degraded' ? 'degraded' : 'online'
        error.value = null
      })
      .catch((reason: unknown) => {
        if (requestGeneration !== generation) return
        status.value = 'offline'
        error.value = reason instanceof Error ? reason.message : '健康检查失败。'
      })
      .finally(() => {
        inFlight = null
      })

    return inFlight
  }

  const start = (): void => {
    if (timer) return
    generation += 1
    void refresh()
    timer = setInterval(() => void refresh(), intervalMs)
  }

  const stop = (): void => {
    generation += 1
    if (timer) clearInterval(timer)
    timer = null
  }

  onMounted(start)
  onUnmounted(stop)

  return {
    health: readonly(health),
    status: readonly(status),
    error: readonly(error),
    refresh,
    start,
    stop,
  }
}
