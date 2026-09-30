<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, watch } from 'vue'

import { useChatAnnouncements } from '../../composables/useChatAnnouncements'
import { useFocusRestore } from '../../composables/useFocusRestore'
import { useHealthPoll } from '../../composables/useHealthPoll'
import { useSrAnnounce } from '../../composables/useSrAnnounce'
import { removeCredentialQueryParameters } from '../../lib/reference'
import { useSessionStore } from '../../stores/session'
import { useViewStore } from '../../stores/view'
import ChatView from '../../views/ChatView.vue'
import SrAnnouncer from '../common/SrAnnouncer.vue'
import AgentInspector from '../inspector/AgentInspector.vue'
import AppSidebar from './AppSidebar.vue'
import AppTopbar from './AppTopbar.vue'

const session = useSessionStore()
const view = useViewStore()
const healthPoll = useHealthPoll()
const { announcement, announce } = useSrAnnounce()
const { rememberTrigger, focusFirst, restoreFocus, trapFocus } = useFocusRestore()
useChatAnnouncements(announce)
const inspectorEnabled = import.meta.env.VITE_ENABLE_AGENT_INSPECTOR === 'true'
const modelLabel = computed(() => {
  const health = healthPoll.health.value
  if (!health || healthPoll.status.value === 'offline') return '服务暂不可用'
  if (health.serving_mode === 'demo_fallback') return '模型异常，已降级到本地模式'
  if (health.serving_mode === 'forced_demo') return '运维强制演示模式'
  if (health.agent_mode === 'demo') return '本地演示模式'
  return health.model_configured ? `真实模型 · ${health.llm_model ?? '已配置'}` : '模型待配置'
})

type Overlay = 'sidebar' | 'inspector'
const activeOverlay = computed<Overlay | null>(() => {
  if (view.sidebarOpen) return 'sidebar'
  if (inspectorEnabled && view.inspectorOpen) return 'inspector'
  return null
})

const overlayElement = (overlay: Overlay): HTMLElement | null => document.querySelector(
  overlay === 'sidebar' ? '.app-shell > .sidebar' : '.app-shell > .inspector-panel',
)

const isDrawer = (overlay: Overlay): boolean => {
  if (typeof window.matchMedia !== 'function') return false
  return window.matchMedia(overlay === 'sidebar' ? '(max-width: 900px)' : '(max-width: 1100px)').matches
}

watch(activeOverlay, async (current, previous) => {
  if (!current || current === previous) return
  rememberTrigger()
  await nextTick()
  if (isDrawer(current)) focusFirst(overlayElement(current))
})

const closeOverlay = (): void => {
  view.closeOverlays()
  void restoreFocus()
}

const handleEscape = (event: KeyboardEvent): void => {
  const overlay = activeOverlay.value
  if (!overlay) return
  if (event.key === 'Escape') {
    event.preventDefault()
    closeOverlay()
    return
  }
  if (isDrawer(overlay)) trapFocus(event, overlayElement(overlay))
}

onMounted(async () => {
  removeCredentialQueryParameters()
  window.addEventListener('keydown', handleEscape)
  if (session.accessToken) {
    const restored = await session.restore()
    void announce(restored ? '登录状态已恢复。' : '登录状态已失效，请重新登录。')
  }
})

onUnmounted(() => window.removeEventListener('keydown', handleEscape))
</script>

<template>
  <a class="skip-link" href="#workspace">跳到主要内容</a>
  <div class="app-shell" :data-view="inspectorEnabled ? view.viewMode : 'customer'" :data-sidebar-open="view.sidebarOpen">
    <aside class="sidebar" aria-label="功能栏"><AppSidebar :health-status="healthPoll.status.value" @announce="announce" @close="closeOverlay" /></aside>
    <section class="main-column"><AppTopbar :health-status="healthPoll.status.value" :inspector-enabled="inspectorEnabled" /><ChatView /></section>
    <AgentInspector
      v-if="inspectorEnabled && view.inspectorOpen"
      class="inspector-panel"
      :model-label="modelLabel"
      @close="closeOverlay"
    />
    <button v-if="view.sidebarOpen || (inspectorEnabled && view.inspectorOpen)" class="backdrop" type="button" aria-label="关闭覆盖面板" @click="closeOverlay" />
    <SrAnnouncer :message="announcement" />
  </div>
</template>

<style scoped>
.app-shell { display: grid; grid-template-columns: 280px minmax(0, 1fr); height: 100dvh; min-height: 0; overflow: hidden; }
.app-shell[data-view="developer"] { grid-template-columns: 280px minmax(0, 1fr) 360px; }
.sidebar, .main-column, .inspector-panel { min-height: 0; }.main-column { display: grid; grid-template-rows: auto minmax(0, 1fr); min-width: 0; overflow: hidden; }
.backdrop { display: none; }
@media (max-width: 1100px) {
  .app-shell[data-view="developer"] { grid-template-columns: 280px minmax(0, 1fr); }
  .inspector-panel { position: fixed; z-index: 40; inset-block: 0; inset-inline-end: 0; width: min(380px, 92vw); box-shadow: var(--shadow-lg); }
  .app-shell[data-view="developer"] .backdrop { display: block; position: fixed; z-index: 30; inset: 0; background: var(--color-backdrop); border: 0; }
}
@media (max-width: 900px) {
  .app-shell, .app-shell[data-view="developer"] { grid-template-columns: minmax(0, 1fr); }
  .sidebar { position: fixed; z-index: 50; inset-block: 0; inset-inline-start: 0; width: min(300px, 88vw); transform: translateX(-100%); transition: transform var(--duration-normal) var(--ease-standard); box-shadow: var(--shadow-lg); }
  .app-shell[data-sidebar-open="true"] .sidebar { transform: translateX(0); }
  .app-shell[data-sidebar-open="true"] .backdrop { display: block; position: fixed; z-index: 45; inset: 0; background: var(--color-backdrop); border: 0; }
}
</style>
