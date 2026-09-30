import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useChatStore } from '../../stores/chat'
import type { AssistantMessage } from '../../types/chat'
import AppShell from './AppShell.vue'

function assistant(overrides: Partial<AssistantMessage> = {}): AssistantMessage {
  return {
    id: 'assistant-1',
    role: 'assistant',
    runId: 'run-1',
    at: 1,
    text: '回答',
    status: null,
    reference: null,
    results: { kind: 'none' },
    confirmation: null,
    confirmationPhase: 'pending',
    confirmationResult: null,
    streamPhase: 'connecting',
    ...overrides,
  }
}

describe('AppShell focus management', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      status: 'ok',
      model_configured: false,
      agent_mode: 'demo',
      backend_base_url: 'http://backend.test/api',
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))
  })

  afterEach(() => {
    document.body.innerHTML = ''
    vi.unstubAllGlobals()
  })

  it('focuses the mobile sidebar and restores focus after Escape', async () => {
    const wrapper = mount(AppShell, {
      attachTo: document.body,
      global: { plugins: [createPinia()] },
    })
    const trigger = wrapper.get('button[aria-label="打开功能栏"]')
    ;(trigger.element as HTMLElement).focus()
    await trigger.trigger('click')
    await flushPromises()

    expect(document.activeElement).toBe(wrapper.get('button[aria-label="关闭功能栏"]').element)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()

    expect(document.activeElement).toBe(trigger.element)
    expect(wrapper.find('.backdrop').exists()).toBe(false)
    wrapper.unmount()
  })

  it('traps reverse Tab inside an open drawer', async () => {
    const wrapper = mount(AppShell, {
      attachTo: document.body,
      global: { plugins: [createPinia()] },
    })
    const trigger = wrapper.get('button[aria-label="打开功能栏"]')
    ;(trigger.element as HTMLElement).focus()
    await trigger.trigger('click')
    await flushPromises()

    const close = wrapper.get('button[aria-label="关闭功能栏"]')
    ;(close.element as HTMLElement).focus()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true }))

    expect(document.activeElement).toBe(wrapper.get('.new-chat').element)
    wrapper.unmount()
  })

  it('announces reply completion and confirmation states', async () => {
    const pinia = createPinia()
    const wrapper = mount(AppShell, {
      attachTo: document.body,
      global: { plugins: [pinia] },
    })
    const chat = useChatStore(pinia)
    const reply = assistant()
    chat.messages.push(reply)
    ;(chat.messages[0] as AssistantMessage).streamPhase = 'done'
    await flushPromises()

    expect(wrapper.get('[role="status"].sr-only').text()).toBe('回复已完成。')

    const pending = assistant({
      id: 'assistant-2',
      runId: 'run-2',
      streamPhase: 'done',
      confirmation: {
        token: 'confirm-1',
        action: 'clear_cart',
        description: '清空当前购物车',
        arguments: {},
      },
    })
    chat.messages.push(pending)
    await flushPromises()
    expect(wrapper.get('[role="status"].sr-only').text()).toBe('需要确认：清空当前购物车')

    const pendingMessage = chat.messages[1] as AssistantMessage
    pendingMessage.confirmationPhase = 'cancelled'
    pendingMessage.confirmationResult = { message: '数据没有被修改。', data: null }
    await flushPromises()
    expect(wrapper.get('[role="status"].sr-only').text()).toBe('操作已取消：数据没有被修改。')
    wrapper.unmount()
  })
})
