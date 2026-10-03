<script setup lang="ts">
import { LogIn, Menu } from '@lucide/vue'

import StatusPill from '../common/StatusPill.vue'
import IdentityAvatar from '../common/IdentityAvatar.vue'
import type { HealthStatus } from '../../composables/useHealthPoll'
import { useSessionStore } from '../../stores/session'
import { useViewStore } from '../../stores/view'
import ViewSwitch from './ViewSwitch.vue'

withDefaults(defineProps<{ healthStatus: HealthStatus; inspectorEnabled?: boolean }>(), {
  inspectorEnabled: false,
})
const view = useViewStore()
const session = useSessionStore()
</script>

<template>
  <header class="topbar">
    <button class="menu" type="button" aria-label="打开功能栏" :aria-expanded="view.sidebarOpen" @click="view.openSidebar()"><Menu :size="21" aria-hidden="true" /></button>
    <div class="title"><p><span class="desktop-title">OrderMate 智能助手</span><span class="mobile-title">OrderMate</span></p><small>商品、订单与售后，一站式帮您处理</small></div>
    <div class="actions">
      <StatusPill
        :label="healthStatus === 'online' ? '在线' : healthStatus === 'degraded' ? '降级可用' : healthStatus === 'checking' ? '检查中' : '离线'"
        :tone="healthStatus === 'online' ? 'success' : healthStatus === 'degraded' ? 'warning' : healthStatus === 'checking' ? 'loading' : 'error'"
      />
      <button class="account-trigger" type="button" :aria-label="session.isAuthenticated ? '打开账号菜单' : '打开登录面板'" @click="view.openAccount()">
        <IdentityAvatar v-if="session.isAuthenticated" kind="user" :username="session.username" size="sm" />
        <template v-else><LogIn :size="18" aria-hidden="true" /><span>登录</span></template>
      </button>
      <ViewSwitch v-if="inspectorEnabled" />
    </div>
  </header>
</template>

<style scoped>
.topbar { display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); min-height: 72px; padding: var(--space-3) var(--space-6); background: var(--color-surface); border-bottom: 1px solid var(--color-line); }
.title p { color: var(--color-navy); font-weight: 600; }
.title small { color: var(--color-muted); font-size: var(--text-sm); }
.mobile-title { display: none; }
.actions { display: flex; align-items: center; gap: var(--space-3); }
.menu { display: none; width: var(--control-height-md); height: var(--control-height-md); align-items: center; justify-content: center; color: var(--color-primary-ink); background: var(--color-primary-soft); border: 1px solid var(--color-line); border-radius: var(--radius-md); }
.account-trigger { display: inline-flex; min-height: var(--control-height-md); align-items: center; gap: var(--space-1); padding-inline: var(--space-2); color: var(--color-primary-ink); background: var(--color-primary-soft); border: 1px solid var(--color-line); border-radius: var(--radius-md); font-weight: 700; }
@media (max-width: 900px) { .menu, .account-trigger { display: inline-flex; } }
@media (max-width: 680px) {
  .topbar { min-height: 64px; gap: var(--space-2); padding-inline: var(--space-3); }
  .desktop-title, .title small { display: none; }
  .mobile-title { display: inline; }
  .actions { gap: var(--space-2); }
  .actions :deep(.pill) { min-height: var(--control-height-sm); padding-inline: var(--space-2); }
}
@media (max-width: 360px) { .title p { font-size: var(--text-sm); } .account-trigger { padding-inline: var(--space-1); } }
</style>
