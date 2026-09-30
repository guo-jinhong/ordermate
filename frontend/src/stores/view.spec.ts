import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useViewStore } from './view'

describe('view store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('starts in the customer view with overlays closed', () => {
    const store = useViewStore()

    expect(store.viewMode).toBe('customer')
    expect(store.sidebarOpen).toBe(false)
    expect(store.inspectorOpen).toBe(false)
  })

  it('keeps the sidebar and developer inspector mutually exclusive', () => {
    const store = useViewStore()

    store.openSidebar()
    expect(store.sidebarOpen).toBe(true)
    expect(store.viewMode).toBe('customer')

    store.setViewMode('developer')
    expect(store.sidebarOpen).toBe(false)
    expect(store.inspectorOpen).toBe(true)

    store.openSidebar()
    expect(store.sidebarOpen).toBe(true)
    expect(store.inspectorOpen).toBe(false)
  })

  it('closes all overlay state together', () => {
    const store = useViewStore()
    store.setViewMode('developer')

    store.closeOverlays()

    expect(store.viewMode).toBe('customer')
    expect(store.sidebarOpen).toBe(false)
  })
})
