import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { AssistantMessage as AssistantMessageModel } from '../../types/chat'
import AssistantMessage from './AssistantMessage.vue'

function message(overrides: Partial<AssistantMessageModel> = {}): AssistantMessageModel {
  return {
    id: 'assistant-1',
    role: 'assistant',
    runId: 'run-1',
    at: 1,
    text: '这是回答',
    status: null,
    reference: null,
    results: { kind: 'none' },
    confirmation: null,
    confirmationPhase: 'pending',
    confirmationResult: null,
    streamPhase: 'done',
    ...overrides,
  }
}

describe('AssistantMessage', () => {
  it('collapses duplicate prose while preserving the full explanation', () => {
    const wrapper = mount(AssistantMessage, { props: { message: message({
      text: 'Wireless Headphones 的说明和注意事项',
      results: { kind: 'product', items: [{ id: 1, name: 'Wireless Headphones' }], context: {} },
    }) } })
    expect(wrapper.get('details').attributes('open')).toBeUndefined()
    expect(wrapper.get('details .answer').text()).toBe('无线降噪耳机 的说明和注意事项')
    expect(wrapper.get('h4').text()).toBe('无线降噪耳机')
  })
  it('keeps reference metadata out of customer replies', () => {
    const wrapper = mount(AssistantMessage, {
      props: {
        message: message({
          reference: { type: 'product', value: '上一件商品', source: '上下文指代' },
        }),
      },
    })

    expect(wrapper.text()).toContain('这是回答')
    expect(wrapper.text()).not.toContain('上下文指代')
    expect(wrapper.text()).not.toContain('上一件商品')
  })

  it('renders streaming status and raw fallback data', () => {
    const wrapper = mount(AssistantMessage, {
      props: {
        message: message({
          text: '',
          status: { text: 'Agent 正在处理', tone: 'loading' },
          results: { kind: 'raw', value: { custom: 1 } },
          streamPhase: 'streaming',
        }),
      },
    })

    expect(wrapper.text()).toContain('Agent 正在处理')
    expect(wrapper.text()).toContain('查看未识别数据')
  })

  it('offers retry for the latest failed response', async () => {
    const wrapper = mount(AssistantMessage, {
      props: {
        canRetry: true,
        message: message({
          status: { text: '服务暂时不可用，请稍后重试。', tone: 'error' },
          streamPhase: 'error',
        }),
      },
    })

    await wrapper.get('button').trigger('click')
    expect(wrapper.get('[role="alert"]').text()).toContain('服务暂时不可用')
    expect(wrapper.emitted('retry')).toEqual([[]])
  })

  it('forwards a confirmation decision from the confirmation card', async () => {
    const wrapper = mount(AssistantMessage, {
      props: {
        message: message({
          confirmation: {
            token: 'confirm-1',
            action: 'pay_order',
            description: '支付订单 88',
            arguments: { order_id: 88 },
          },
        }),
      },
    })

    await wrapper.get('button.confirm').trigger('click')

    expect(wrapper.emitted('confirm')).toEqual([[true]])
  })
})
