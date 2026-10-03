import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useChatStore } from '../../stores/chat'
import ComposerBox from './ComposerBox.vue'

describe('ComposerBox recovery and keyboard input', () => {
  beforeEach(() => { sessionStorage.clear(); setActivePinia(createPinia()) })

  it('restores a failed message for editing without sending it again', async () => {
    const chat = useChatStore()
    const send = vi.spyOn(chat, 'send').mockImplementation(async () => { chat.lastError = '连接失败' })
    const wrapper = mount(ComposerBox)
    await wrapper.get('textarea').setValue('查询订单')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.get('textarea').element.value).toBe('')
    await wrapper.get('.draft-recovery button').trigger('click')
    expect(wrapper.get('textarea').element.value).toBe('查询订单')
    expect(send).toHaveBeenCalledOnce()
    expect(wrapper.find('.draft-recovery').exists()).toBe(false)
    wrapper.unmount()
  })

  it('does not submit while using a Chinese input method or Shift+Enter', async () => {
    const send = vi.spyOn(useChatStore(), 'send').mockResolvedValue()
    const wrapper = mount(ComposerBox)
    await wrapper.get('textarea').setValue('测试输入')
    await wrapper.get('textarea').trigger('keydown', { key: 'Enter', isComposing: true })
    await wrapper.get('textarea').trigger('keydown', { key: 'Enter', shiftKey: true })
    expect(send).not.toHaveBeenCalled()
    await wrapper.get('textarea').trigger('keydown', { key: 'Enter' })
    expect(send).toHaveBeenCalledWith('测试输入')
    wrapper.unmount()
  })
})
