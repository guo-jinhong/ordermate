import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Confirmation } from '../../types/api'
import ConfirmationCard from './ConfirmationCard.vue'

const confirmation: Confirmation = {
  token: 'confirm-1',
  action: 'cancel_order',
  description: '取消订单 101',
  arguments: { order_id: 101 },
}

describe('ConfirmationCard', () => {
  afterEach(() => { vi.useRealTimers() })
  it('shows remaining time, expires and disables submission', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-02T00:00:00Z'))
    const wrapper = mount(ConfirmationCard, { props: {
      confirmation: { ...confirmation, expires_at: '2026-10-02T00:01:00Z' }, phase: 'pending', result: null,
    } })
    expect(wrapper.text()).toContain('60 秒后失效')
    await vi.advanceTimersByTimeAsync(60000)
    expect(wrapper.text()).toContain('已过期')
    expect(wrapper.findAll('button').every(button => button.attributes('disabled') !== undefined)).toBe(true)
    await wrapper.findAll('button')[1]!.trigger('click')
    expect(wrapper.emitted('confirm')).toBeUndefined()
    wrapper.unmount()
  })
  it('checks expiration again when returning from mobile background', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-02T00:00:00Z'))
    const wrapper = mount(ConfirmationCard, { props: {
      confirmation: { ...confirmation, expires_at: '2026-10-02T00:01:00Z' }, phase: 'pending', result: null,
    } })
    vi.setSystemTime(new Date('2026-10-02T00:02:00Z'))
    document.dispatchEvent(new Event('visibilitychange'))
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('已过期')
    expect(wrapper.findAll('button')[1]!.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
  it('offers only readonly verification for an unknown write result', async () => {
    const wrapper = mount(ConfirmationCard, { props: { confirmation, phase: 'unknown',
      result: { message: '请查询当前状态，勿重复提交。', data: null } } })
    expect(wrapper.text()).toContain('暂时无法确认操作结果')
    expect(wrapper.findAll('button')).toHaveLength(1)
    expect(wrapper.get('button').text()).toBe('核实操作结果')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('verify')).toHaveLength(1)
    expect(wrapper.emitted('confirm')).toBeUndefined()
    wrapper.unmount()
  })
  it('describes the operation and emits both decisions', async () => {
    const wrapper = mount(ConfirmationCard, {
      props: { confirmation, phase: 'pending', result: null },
    })
    const buttons = wrapper.findAll('button')

    expect(wrapper.attributes('role')).toBe('alertdialog')
    expect(wrapper.get(`#${wrapper.attributes('aria-labelledby')}`).text()).toContain('取消')
    expect(wrapper.text()).toContain('订单将变为已取消')

    await buttons[0]!.trigger('click')
    await buttons[1]!.trigger('click')
    expect(wrapper.emitted('confirm')).toEqual([[false], [true]])
  })

  it('disables both decisions while submitting', () => {
    const wrapper = mount(ConfirmationCard, {
      props: { confirmation, phase: 'submitting', result: null },
    })

    expect(wrapper.findAll('button')).toHaveLength(2)
    expect(wrapper.findAll('button').every((button) => button.attributes('disabled') !== undefined)).toBe(true)
    expect(wrapper.text()).toContain('正在提交')
  })

  it('replaces decisions with a neutral cancellation result', () => {
    const wrapper = mount(ConfirmationCard, {
      props: {
        confirmation,
        phase: 'cancelled',
        result: { message: '已取消，购物车和订单保持不变。', data: null },
      },
    })

    expect(wrapper.find('button').exists()).toBe(false)
    expect(wrapper.get('[data-tone="neutral"]').text()).toContain('购物车和订单保持不变')
  })

  it('uses generic copy for an unknown action', () => {
    const wrapper = mount(ConfirmationCard, {
      props: {
        confirmation: { ...confirmation, action: 'future_action' as Confirmation['action'] },
        phase: 'pending',
        result: null,
      },
    })

    expect(wrapper.text()).toContain('确认进行这项操作')
    expect(wrapper.text()).toContain('请查看上方操作内容')
  })
})
