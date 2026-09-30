import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import OperationResult from './OperationResult.vue'

describe('OperationResult', () => {
  it('renders executed as success', () => {
    const wrapper = mount(OperationResult, {
      props: { phase: 'executed', message: '订单已创建', data: { order_id: 1 } },
    })

    expect(wrapper.attributes('data-tone')).toBe('success')
    expect(wrapper.text()).toContain('订单已创建')
  })

  it('renders cancellation as a neutral normal result', () => {
    const wrapper = mount(OperationResult, {
      props: { phase: 'cancelled', message: null, data: null },
    })

    expect(wrapper.attributes('data-tone')).toBe('neutral')
    expect(wrapper.text()).toContain('数据没有被修改')
    expect(wrapper.text()).not.toContain('失败')
  })

  it('renders failures separately from cancellation', () => {
    const wrapper = mount(OperationResult, {
      props: { phase: 'failed', message: '确认已失效', data: null },
    })

    expect(wrapper.attributes('data-tone')).toBe('error')
    expect(wrapper.text()).toContain('确认已失效')
  })
})
