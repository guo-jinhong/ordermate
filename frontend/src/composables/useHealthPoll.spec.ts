import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { HealthResponse } from '../types/api'
import { useHealthPoll } from './useHealthPoll'

const healthyResponse: HealthResponse = {
  status: 'ok',
  model_configured: false,
  agent_mode: 'demo',
  serving_mode: 'demo',
  embedding_mode: 'lexical',
  backend_base_url: 'http://backend.test/api',
}

const degradedResponse: HealthResponse = {
  ...healthyResponse,
  status: 'degraded',
  serving_mode: 'demo_fallback',
  fallback_reason: 'ConnectionError',
}

function mountHealthPoll(load: () => Promise<HealthResponse>, intervalMs = 30_000) {
  const holder: { poll?: ReturnType<typeof useHealthPoll> } = {}
  const wrapper = mount(
    defineComponent({
      setup() {
        holder.poll = useHealthPoll({ load, intervalMs })
        return () => h('div')
      },
    }),
  )

  if (!holder.poll) throw new Error('健康轮询未初始化。')
  return { poll: holder.poll, wrapper }
}

describe('useHealthPoll', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('checks immediately and exposes an online response', async () => {
    const load = vi.fn().mockResolvedValue(healthyResponse)
    const { poll, wrapper } = mountHealthPoll(load)

    await flushPromises()

    expect(load).toHaveBeenCalledTimes(1)
    expect(poll.status.value).toBe('online')
    expect(poll.health.value).toEqual(healthyResponse)
    expect(poll.error.value).toBeNull()
    wrapper.unmount()
  })

  it('marks failures offline and recovers on the next refresh', async () => {
    const load = vi
      .fn<() => Promise<HealthResponse>>()
      .mockRejectedValueOnce(new Error('network unavailable'))
      .mockResolvedValueOnce(healthyResponse)
    const { poll, wrapper } = mountHealthPoll(load)

    await flushPromises()
    expect(poll.status.value).toBe('offline')
    expect(poll.error.value).toBe('network unavailable')

    await poll.refresh()
    expect(poll.status.value).toBe('online')
    expect(poll.error.value).toBeNull()
    wrapper.unmount()
  })

  it('exposes dependency degradation without treating the Agent as offline', async () => {
    const load = vi.fn().mockResolvedValue(degradedResponse)
    const { poll, wrapper } = mountHealthPoll(load)

    await flushPromises()

    expect(poll.status.value).toBe('degraded')
    expect(poll.health.value?.serving_mode).toBe('demo_fallback')
    wrapper.unmount()
  })

  it('polls on the configured interval without overlapping slow requests', async () => {
    vi.useFakeTimers()
    const request: { resolve?: (value: HealthResponse) => void } = {}
    const load = vi.fn(
      () =>
        new Promise<HealthResponse>((resolve) => {
          request.resolve = resolve
        }),
    )
    const { wrapper } = mountHealthPoll(load, 1_000)

    await vi.advanceTimersByTimeAsync(3_000)
    expect(load).toHaveBeenCalledTimes(1)

    if (!request.resolve) throw new Error('健康检查请求未启动。')
    request.resolve(healthyResponse)
    await flushPromises()
    await vi.advanceTimersByTimeAsync(1_000)
    expect(load).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('stops polling when the owner unmounts', async () => {
    vi.useFakeTimers()
    const load = vi.fn().mockResolvedValue(healthyResponse)
    const { wrapper } = mountHealthPoll(load, 1_000)
    await flushPromises()

    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(3_000)

    expect(load).toHaveBeenCalledTimes(1)
  })
})
