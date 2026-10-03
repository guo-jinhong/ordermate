import { defineStore } from 'pinia'

export type ViewMode = 'customer' | 'developer'

export const useViewStore = defineStore('view', {
  state: () => ({
    viewMode: 'customer' as ViewMode,
    sidebarOpen: false,
    loginPanelOpen: false,
  }),

  getters: {
    inspectorOpen: (state): boolean => state.viewMode === 'developer',
  },

  actions: {
    openAccount(): void {
      this.loginPanelOpen = true
      this.openSidebar()
    },
    setViewMode(mode: ViewMode): void {
      this.viewMode = mode
      if (mode === 'developer') this.sidebarOpen = false
    },

    openSidebar(): void {
      this.viewMode = 'customer'
      this.sidebarOpen = true
    },

    closeSidebar(): void {
      this.sidebarOpen = false
    },

    closeOverlays(): void {
      this.sidebarOpen = false
      this.viewMode = 'customer'
    },
  },
})
