import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App.vue'

describe('App', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            status: 'ok',
            model_configured: false,
            agent_mode: 'demo',
            backend_base_url: 'http://backend.test/api',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )
  })

  afterEach(() => vi.unstubAllGlobals())

  it('mounts the usable OrderMate workspace', () => {
    const wrapper = mount(App, { global: { plugins: [createPinia()] } })

    expect(wrapper.get('h1').text()).toBe('今天想买些什么？')
    expect(wrapper.text()).toContain('OrderMate')
    expect(wrapper.get('textarea').attributes('placeholder')).toContain('描述你想查找')
    expect(wrapper.get('.skip-link').attributes('href')).toBe('#workspace')
    expect(wrapper.get('main').attributes('id')).toBe('workspace')
    wrapper.unmount()
  })
})
