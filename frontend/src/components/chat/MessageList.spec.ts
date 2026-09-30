import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'

import { useChatStore } from '../../stores/chat'
import MessageList from './MessageList.vue'

describe('MessageList scroll behavior', () => {
  it('keeps the reader position during updates and follows again at the bottom', async () => {
    const pinia = createPinia()
    const wrapper = mount(MessageList, { global: { plugins: [pinia] } })
    const chat = useChatStore(pinia)
    const element = wrapper.get('.message-list').element as HTMLElement
    const scrollTo = vi.fn()

    Object.defineProperties(element, {
      clientHeight: { configurable: true, value: 300 },
      scrollHeight: { configurable: true, value: 1_000 },
      scrollTop: { configurable: true, writable: true, value: 700 },
      scrollTo: { configurable: true, value: scrollTo },
    })

    const message = { id: 'user-1', role: 'user' as const, text: '第一条消息', at: 1 }
    chat.messages.push(message)
    await flushPromises()
    expect(scrollTo).toHaveBeenCalledWith({ top: 1_000, behavior: 'auto' })

    element.scrollTop = 200
    await wrapper.get('.message-list').trigger('scroll')
    const callsWhileReading = scrollTo.mock.calls.length
    chat.messages[0]!.text = '流式更新后的消息'
    await flushPromises()
    expect(scrollTo).toHaveBeenCalledTimes(callsWhileReading)

    element.scrollTop = 700
    await wrapper.get('.message-list').trigger('scroll')
    chat.messages[0]!.text = '位于底部时继续更新'
    await flushPromises()
    expect(scrollTo).toHaveBeenLastCalledWith({ top: 1_000, behavior: 'auto' })

    // 长回复增长后保持其开头可见，而不是跳到最后一张卡片。
    vi.spyOn(element, 'getBoundingClientRect').mockReturnValue({ top: 100 } as DOMRect)
    vi.spyOn(element.lastElementChild!, 'getBoundingClientRect').mockReturnValue({ top: 150, height: 900 } as DOMRect)
    chat.messages[0]!.text = '包含多张结果卡片的长回复'
    await flushPromises()
    expect(scrollTo).toHaveBeenLastCalledWith({ top: 750, behavior: 'auto' })

    wrapper.unmount()
  })
})
