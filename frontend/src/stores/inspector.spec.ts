import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useInspectorStore } from './inspector'

describe('inspector store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('records the complete active-run timeline including progress', () => {
    const store = useInspectorStore()
    store.startRun('run-new', '查看购物车', 100)

    store.recordEvent('run-old', { type: 'started', data: { message: '旧请求' } }, 110)
    store.recordEvent('run-new', { type: 'progress', data: { message: '处理中' } }, 120)
    store.recordEvent(
      'run-new',
      { type: 'tool', data: { name: 'get_cart', outcome: 'success', arguments: {} } },
      130,
    )

    expect(store.phase).toBe('streaming')
    expect(store.query).toBe('查看购物车')
    expect(store.events.map(({ type }) => type)).toEqual(['progress', 'tool'])
    expect(store.toolCount).toBe(1)
  })

  it('redacts sensitive event payloads and records duration', () => {
    const store = useInspectorStore()
    store.startRun('run-1', '登录', 100)
    store.recordEvent(
      'run-1',
      {
        type: 'tool',
        data: { name: 'login', outcome: 'success', arguments: { access_token: 'secret' } },
      },
      150,
    )
    store.recordEvent(
      'run-1',
      {
        type: 'result',
        data: { answer: '完成', tool_calls: [], confirmation: null, data: null, reference: null },
      },
      180,
    )

    expect(store.events[0]?.data).toMatchObject({ arguments: { access_token: '[已脱敏]' } })
    expect(store.phase).toBe('done')
    expect(store.durationMs).toBe(80)
  })
})
