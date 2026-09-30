import { describe, expect, it, vi } from 'vitest'

import { fetchHealth } from './system'

describe('system api', () => {
  it('loads the lightweight Agent health endpoint', async () => {
    const health = {
      status: 'ok',
      model_configured: false,
      agent_mode: 'demo',
      serving_mode: 'demo',
      embedding_mode: 'lexical',
      backend_base_url: 'http://backend.test/api',
    }
    const fetchImpl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(input).toBe('/health')
      expect(init?.method).toBeUndefined()
      return new Response(JSON.stringify(health), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }) as typeof fetch

    await expect(fetchHealth(fetchImpl)).resolves.toEqual(health)
  })
})
