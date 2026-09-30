import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { Confirmation } from '../../types/api'
import ConfirmationCard from './ConfirmationCard.vue'

const confirmation: Confirmation = {
  token: 'confirm-1',
  action: 'cancel_order',
  description: '取消订单 101',
  arguments: { order_id: 101 },
}

describe('ConfirmationCard', () => {
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
        result: { message: '已取消，数据没有被修改。', data: null },
      },
    })

    expect(wrapper.find('button').exists()).toBe(false)
    expect(wrapper.get('[data-tone="neutral"]').text()).toContain('数据没有被修改')
  })

  it('uses generic copy for an unknown action', () => {
    const wrapper = mount(ConfirmationCard, {
      props: {
        confirmation: { ...confirmation, action: 'future_action' as Confirmation['action'] },
        phase: 'pending',
        result: null,
      },
    })

    expect(wrapper.text()).toContain('确认执行这项操作')
    expect(wrapper.text()).toContain('服务端已锁定本次操作内容')
  })
})
