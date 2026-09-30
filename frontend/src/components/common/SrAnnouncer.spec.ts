import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SrAnnouncer from './SrAnnouncer.vue'

describe('SrAnnouncer', () => {
  it('exposes one atomic polite status region', () => {
    const wrapper = mount(SrAnnouncer, { props: { message: '回复已完成。' } })
    const status = wrapper.get('[role="status"]')

    expect(status.attributes('aria-live')).toBe('polite')
    expect(status.attributes('aria-atomic')).toBe('true')
    expect(status.text()).toBe('回复已完成。')
  })
})
