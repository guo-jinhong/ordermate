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
    expect(wrapper.emitted('announce')).toContainEqual(['已取消继续操作，你仍然保持登录状态。'])
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

  it('shows and fills the demo login credentials', async () => {
    const wrapper = mount(AppSidebar, {
      props: { healthStatus: 'online' },
    })

    expect(wrapper.text()).toContain('体验账号')
    expect(wrapper.text()).toContain('testuser')
    expect(wrapper.text()).toContain('password')

    await wrapper.get('.demo-account button').trigger('click')

    expect((wrapper.get('input[autocomplete="username"]').element as HTMLInputElement).value).toBe('testuser')
    expect((wrapper.get('input[autocomplete="current-password"]').element as HTMLInputElement).value).toBe('password')
    expect(wrapper.emitted('announce')).toContainEqual(['已填入体验账号，可以直接登录。'])
  })
})
