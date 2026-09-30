<script setup lang="ts">
import StatusPill from '../common/StatusPill.vue'
import type { HealthStatus } from '../../composables/useHealthPoll'
import { useViewStore } from '../../stores/view'
import ViewSwitch from './ViewSwitch.vue'

withDefaults(defineProps<{ healthStatus: HealthStatus; inspectorEnabled?: boolean }>(), {
  inspectorEnabled: false,
})
const view = useViewStore()
</script>

<template>
  <header class="topbar">
    <button class="menu" type="button" aria-label="打开功能栏" :aria-expanded="view.sidebarOpen" @click="view.openSidebar()">菜单</button>
    <div class="title"><p>智能电商工作台</p><span>OrderMate 智能助手</span></div>
    <div class="actions">
      <StatusPill
        :label="healthStatus === 'online' ? '在线' : healthStatus === 'degraded' ? '降级可用' : healthStatus === 'checking' ? '检查中' : '离线'"
        :tone="healthStatus === 'online' ? 'success' : healthStatus === 'degraded' ? 'warning' : healthStatus === 'checking' ? 'loading' : 'error'"
      />
      <ViewSwitch v-if="inspectorEnabled" />
    </div>
  </header>
</template>

<style scoped>
.topbar { display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); min-height: 76px; padding: var(--space-3) var(--space-6); background: var(--color-surface-raised); border-bottom: 1px solid var(--color-line); }
.title p { color: var(--color-navy); font-weight: 800; }
.title span { color: var(--color-muted); font-size: var(--text-sm); }
.actions { display: flex; align-items: center; gap: var(--space-3); }
.menu { display: none; min-height: var(--control-height-md); padding-inline: var(--space-3); color: var(--color-primary-ink); background: var(--color-primary-soft); border: 1px solid var(--color-primary); border-radius: var(--radius-md); font-weight: 700; }
@media (max-width: 900px) { .menu { display: inline-flex; align-items: center; } }
@media (max-width: 680px) {
  .topbar { min-height: 68px; gap: var(--space-2); padding-inline: var(--space-4); }
  .title span { display: none; }
  .actions { gap: var(--space-2); }
  .actions :deep(.pill) { min-height: var(--control-height-sm); padding-inline: var(--space-2); }
}
@media (max-width: 420px) { .title { display: none; } }
</style>
