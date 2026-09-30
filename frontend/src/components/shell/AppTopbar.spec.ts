import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useViewStore } from '../../stores/view'
import AppTopbar from './AppTopbar.vue'

describe('AppTopbar', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders health state and opens the sidebar accessibly', async () => {
    const wrapper = mount(AppTopbar, { props: { healthStatus: 'online' } })
    const menu = wrapper.get('button[aria-label="打开功能栏"]')

    expect(wrapper.text()).toContain('在线')
    expect(menu.attributes('aria-expanded')).toBe('false')

    await menu.trigger('click')

    expect(useViewStore().sidebarOpen).toBe(true)
    expect(menu.attributes('aria-expanded')).toBe('true')
  })

  it('shows degraded services as available instead of offline', () => {
    const wrapper = mount(AppTopbar, { props: { healthStatus: 'degraded' } })

    expect(wrapper.text()).toContain('降级可用')
    expect(wrapper.text()).not.toContain('离线')
  })

  it('hides the developer inspector entry by default', () => {
    const wrapper = mount(AppTopbar, { props: { healthStatus: 'online' } })

    expect(wrapper.text()).not.toContain('调试')
    expect(wrapper.find('[role="tablist"]').exists()).toBe(false)
  })
})
