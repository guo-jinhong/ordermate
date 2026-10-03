import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useChatStore } from '../../stores/chat'
import { useSessionStore } from '../../stores/session'
import { useViewStore } from '../../stores/view'
import AppSidebar from './AppSidebar.vue'

describe('AppSidebar', () => {
  beforeEach(() => {
    sessionStorage.clear()
    setActivePinia(createPinia())
  })

  it('holds an authenticated prompt until the user explicitly continues', async () => {
    const session = useSessionStore()
    const view = useViewStore()
    const chat = useChatStore()
    session.accessToken = 'token'
    session.username = 'demo'
    session.authStatus = 'authenticated'
    session.requestLoginForAction('查看我的购物车', '查看购物车')
    view.openSidebar()
    const send = vi.spyOn(chat, 'send').mockResolvedValue()
    const wrapper = mount(AppSidebar, {
      props: { healthStatus: 'online' },
    })

    expect(wrapper.text()).toContain('是否继续“查看购物车”')
    expect(send).not.toHaveBeenCalled()

    await wrapper.get('.pending-action .primary').trigger('click')

    expect(send).toHaveBeenCalledWith('查看我的购物车')
    expect(session.pendingAction).toBeNull()
    expect(view.sidebarOpen).toBe(false)
    expect(wrapper.emitted('announce')).toContainEqual(['继续查看购物车。'])
  })

  it('allows the user to decline continuation without logging out', async () => {
    const session = useSessionStore()
    session.accessToken = 'token'
    session.username = 'demo'
    session.authStatus = 'authenticated'
    session.requestLoginForAction('查看我的订单', '查看订单')
    const wrapper = mount(AppSidebar, {
      props: { healthStatus: 'online' },
    })

    await wrapper.get('.pending-action .secondary').trigger('click')

    expect(session.pendingAction).toBeNull()
    expect(session.isAuthenticated).toBe(true)
    expect(wrapper.emitted('announce')).toContainEqual(['本次未继续操作，您仍保持登录状态。'])
  })

  it('gates protected quick actions and emits close requests', async () => {
    const session = useSessionStore()
    const wrapper = mount(AppSidebar, {
      props: { healthStatus: 'offline' },
    })
    const cartButton = wrapper.findAll('.quick button').find(
      (button) => button.text() === '查看购物车',
    )

    await cartButton!.trigger('click')
    await wrapper.get('button[aria-label="关闭功能栏"]').trigger('click')

    expect(session.pendingAction?.prompt).toBe('查看我的购物车')
    expect(wrapper.emitted('announce')).toContainEqual(['请先登录，登录后可继续查看购物车。'])
    expect(wrapper.emitted('close')).toEqual([[]])
  })

  it('preserves the conversation until a new chat is confirmed', async () => {
    const chat = useChatStore()
    chat.messages = [{ id: 'existing', role: 'user', text: '已有对话', at: Date.now() }]
    const clear = vi.spyOn(chat, 'clearConversation').mockResolvedValue(true)
    const wrapper = mount(AppSidebar, { props: { healthStatus: 'online' } })
    await wrapper.get('.new-chat').trigger('click')
    expect(clear).not.toHaveBeenCalled()
    await wrapper.get('.clear-confirm .secondary').trigger('click')
    expect(clear).not.toHaveBeenCalled()
    await wrapper.get('.new-chat').trigger('click')
    await wrapper.get('.clear-confirm .primary').trigger('click')
    expect(clear).toHaveBeenCalledOnce()
  })

  it('opens the login panel on demand without publishing credentials', async () => {
    const wrapper = mount(AppSidebar, {
      props: { healthStatus: 'online' },
    })

    expect(wrapper.text()).toContain('登录后可查看个人购物车与订单')
    expect(wrapper.text()).not.toContain('testuser')
    expect(wrapper.text()).not.toContain('password')
    expect(wrapper.find('input').exists()).toBe(false)
    await wrapper.get('.account-entry').trigger('click')
    expect(wrapper.get('.account-entry').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('input[autocomplete="username"]').attributes('placeholder')).toBe('请输入用户名')
    expect(wrapper.get('input[autocomplete="current-password"]').attributes('placeholder')).toBe('请输入密码')
  })
})
