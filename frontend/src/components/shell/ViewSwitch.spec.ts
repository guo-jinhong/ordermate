import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useViewStore } from '../../stores/view'
import ViewSwitch from './ViewSwitch.vue'

describe('ViewSwitch', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('moves selection and DOM focus with arrow keys', async () => {
    const wrapper = mount(ViewSwitch, { attachTo: document.body })
    const tabs = wrapper.findAll('[role="tab"]')
    ;(tabs[0]!.element as HTMLElement).focus()

    await tabs[0]!.trigger('keydown', { key: 'ArrowRight' })

    expect(useViewStore().viewMode).toBe('developer')
    expect(document.activeElement).toBe(tabs[1]!.element)
    expect(tabs[1]!.attributes('tabindex')).toBe('0')
    wrapper.unmount()
  })

  it('supports Home and End navigation', async () => {
    const wrapper = mount(ViewSwitch, { attachTo: document.body })
    const tabs = wrapper.findAll('[role="tab"]')

    await tabs[0]!.trigger('keydown', { key: 'End' })
    expect(document.activeElement).toBe(tabs[1]!.element)

    await tabs[1]!.trigger('keydown', { key: 'Home' })
    expect(document.activeElement).toBe(tabs[0]!.element)
    wrapper.unmount()
  })
})
