import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import RawResult from './RawResult.vue'

describe('RawResult', () => {
  it('renders unknown data in a disclosure', () => {
    const wrapper = mount(RawResult, { props: { value: { unexpected: true } } })

    expect(wrapper.get('summary').text()).toBe('查看未识别数据')
    expect(wrapper.get('pre').text()).toContain('"unexpected": true')
  })

  it('redacts sensitive fields before rendering', () => {
    const wrapper = mount(RawResult, {
      props: { value: { nested: { access_token: 'secret-jwt', result: 'ok' } } },
    })

    expect(wrapper.get('pre').text()).toContain('[已脱敏]')
    expect(wrapper.get('pre').text()).not.toContain('secret-jwt')
  })
})
