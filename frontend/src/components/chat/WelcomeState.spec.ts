import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import WelcomeState from './WelcomeState.vue'

describe('WelcomeState', () => {
  it('renders four capabilities and emits a structured authenticated action', async () => {
    const wrapper = mount(WelcomeState, { props: { authenticated: false } })

    expect(wrapper.findAll('.capability')).toHaveLength(4)
    expect(wrapper.text()).toContain('购物车和订单功能需要先登录')

    await wrapper.findAll('.capability').at(1)!.trigger('click')
    expect(wrapper.emitted('prompt')?.[0]).toEqual([
      expect.objectContaining({
        label: '管理购物车',
        prompt: '查看我的购物车',
        authRequired: true,
      }),
    ])
  })
})
