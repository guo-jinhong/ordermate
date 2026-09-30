import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useInspectorStore } from '../../stores/inspector'
import { useSessionStore } from '../../stores/session'
import AgentInspector from './AgentInspector.vue'

describe('AgentInspector', () => {
  beforeEach(() => {
    sessionStorage.clear()
    setActivePinia(createPinia())
  })

  it('renders a complete, redacted timeline using business labels', () => {
    const inspector = useInspectorStore()
    const session = useSessionStore()
    session.sessionId = 'session-demo'
    inspector.startRun('run-1', '查看我的购物车', 100)
    inspector.recordEvent('run-1', { type: 'progress', data: { message: '正在查询' } }, 120)
    inspector.recordEvent('run-1', {
      type: 'tool',
      data: {
        name: 'get_cart',
        outcome: 'success',
        arguments: { access_token: 'secret-token' },
      },
    }, 150)
    inspector.finishRun('run-1', 'done', 180)

    const wrapper = mount(AgentInspector, { props: { modelLabel: '本地演示模式' } })

    expect(wrapper.text()).toContain('查看我的购物车')
    expect(wrapper.text()).toContain('浏览器观测时长80 ms')
    expect(wrapper.text()).toContain('处理进度')
    expect(wrapper.text()).toContain('读取购物车')
    expect(wrapper.text()).toContain('[已脱敏]')
    expect(wrapper.text()).not.toContain('get_cart')
    expect(wrapper.text()).not.toContain('secret-token')
    expect(wrapper.text()).toContain('模型：本地演示模式')
    expect(wrapper.text()).toContain('会话：session-demo')
  })
})
