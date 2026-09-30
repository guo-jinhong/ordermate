<script setup lang="ts">
import { ref } from 'vue'

import type { HealthStatus } from '../../composables/useHealthPoll'
import { useChatStore } from '../../stores/chat'
import { useSessionStore } from '../../stores/session'
import { useViewStore } from '../../stores/view'
import StatusPill from '../common/StatusPill.vue'

defineProps<{ healthStatus: HealthStatus }>()
const emit = defineEmits<{
  announce: [message: string]
  close: []
}>()
const session = useSessionStore()
const chat = useChatStore()
const view = useViewStore()
const username = ref('')
const password = ref('')
const loginError = ref('')
const loggingIn = ref(false)

const fillDemoAccount = (): void => {
  username.value = 'testuser'
  password.value = 'password'
  loginError.value = ''
  emit('announce', '已填入体验账号，可以直接登录。')
}

const submitLogin = async (): Promise<void> => {
  if (!username.value.trim() || !password.value) return
  loggingIn.value = true
  loginError.value = ''
  try {
    await session.login(username.value.trim(), password.value)
    password.value = ''
    emit('announce', '登录成功。')
  } catch (error: unknown) {
    loginError.value = error instanceof Error ? error.message : '登录失败，请检查账号信息。'
    emit('announce', loginError.value)
  } finally {
    loggingIn.value = false
  }
}

const continuePendingAction = async (): Promise<void> => {
  const pending = session.consumePendingAction()
  if (!pending) return
  view.closeSidebar()
  emit('announce', `继续${pending.label}。`)
  if (pending.displayPrompt) {
    await chat.send(pending.prompt, pending.displayPrompt)
  } else {
    await chat.send(pending.prompt)
  }
}

const cancelPendingAction = (): void => {
  if (!session.consumePendingAction()) return
  emit('announce', '已取消继续操作，你仍然保持登录状态。')
}

const logout = async (): Promise<void> => {
  await chat.clearConversation()
  session.clear()
  emit('announce', '已退出登录。')
}

const runPrompt = async (prompt: string, label: string, authRequired = false): Promise<void> => {
  if (authRequired && !session.isAuthenticated) {
    session.requestLoginForAction(prompt, label)
    emit('announce', `请先登录，登录后可继续${label}。`)
    return
  }
  view.closeSidebar()
  await chat.send(prompt)
}
</script>

<template>
  <div class="sidebar-content">
    <header class="brand"><span aria-hidden="true">OM</span><div><strong>OrderMate</strong><small>AI 电商助手</small></div><button type="button" aria-label="关闭功能栏" @click="emit('close')">×</button></header>
    <section class="status-card" aria-label="服务状态">
      <StatusPill :label="healthStatus === 'online' ? '智能助手在线' : healthStatus === 'degraded' ? '服务降级' : healthStatus === 'checking' ? '正在连接' : '智能助手离线'" :tone="healthStatus === 'online' ? 'success' : healthStatus === 'checking' ? 'loading' : healthStatus === 'degraded' ? 'warning' : 'error'" />
    </section>
    <section class="account" aria-labelledby="account-title">
      <h2 id="account-title">账号</h2>
      <template v-if="session.isAuthenticated">
        <p>已登录：<strong>{{ session.username ?? '当前用户' }}</strong></p>
        <button class="secondary" type="button" @click="logout">退出登录</button>
      </template>
      <form v-else @submit.prevent="submitLogin">
        <div class="demo-account">
          <div><span>体验账号</span><strong>testuser</strong></div>
          <div><span>体验密码</span><strong>password</strong></div>
          <button type="button" @click="fillDemoAccount">一键填入</button>
        </div>
        <label>用户名<input v-model="username" autocomplete="username" placeholder="请输入 testuser" /></label>
        <label>密码<input v-model="password" type="password" autocomplete="current-password" placeholder="请输入 password" /></label>
        <p v-if="session.pendingAction" class="pending">登录后继续“{{ session.pendingAction.label }}”</p>
        <p v-if="loginError" class="error" role="alert">{{ loginError }}</p>
        <button class="primary" type="submit" :disabled="loggingIn || !username.trim() || !password">{{ loggingIn ? '登录中…' : '登录' }}</button>
      </form>
      <div v-if="session.isAuthenticated && session.pendingAction" class="pending-action" role="status">
        <p>登录成功，是否继续“{{ session.pendingAction.label }}”？</p>
        <div>
          <button type="button" class="secondary" @click="cancelPendingAction">暂不继续</button>
          <button type="button" class="primary" @click="continuePendingAction">继续执行</button>
        </div>
      </div>
    </section>
    <section class="quick" aria-labelledby="quick-title">
      <h2 id="quick-title">快捷操作</h2>
      <button type="button" @click="runPrompt('推荐 100 元以内有库存的商品', '商品推荐')">商品推荐</button>
      <button type="button" @click="runPrompt('查看我的购物车', '查看购物车', true)">查看购物车</button>
      <button type="button" @click="runPrompt('查看我的订单', '查看订单', true)">查看订单</button>
    </section>
    <button class="new-chat" type="button" @click="chat.clearConversation()">新建会话</button>
  </div>
</template>

<style scoped>
.sidebar-content { display: flex; flex-direction: column; gap: var(--space-5); height: 100%; padding: var(--space-5); overflow-y: auto; color: var(--color-on-dark); background: var(--color-navy); }
.brand { display: flex; align-items: center; gap: var(--space-3); }
.brand > span { display: grid; width: 2.5rem; height: 2.5rem; place-items: center; background: var(--color-primary); border-radius: var(--radius-md); font-weight: 900; }
@media (min-width: 901px) { .brand button { display: none; } }
.brand div { display: grid; flex: 1; }.brand small { color: var(--color-on-dark-muted); }.brand button { color: var(--color-on-dark); background: transparent; border: 0; font-size: var(--text-xl); }
.status-card, .account { display: grid; gap: var(--space-3); padding: var(--space-4); background: var(--color-navy-raised); border: 1px solid var(--color-navy-soft); border-radius: var(--radius-lg); }
.status-card p, .account p { color: var(--color-on-dark-muted); font-size: var(--text-sm); }
h2 { color: var(--color-on-dark-muted); font-size: var(--text-sm); text-transform: uppercase; letter-spacing: 0.08em; }
form, label { display: grid; gap: var(--space-2); } form { gap: var(--space-3); } label { color: var(--color-on-dark-muted); font-size: var(--text-sm); }
input { min-height: var(--control-height-md); padding-inline: var(--space-3); color: var(--color-on-dark); background: var(--color-navy); border: 1px solid var(--color-navy-soft); border-radius: var(--radius-md); }
.demo-account { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-2); padding: var(--space-3); background: color-mix(in srgb, var(--color-primary) 13%, transparent); border: 1px solid color-mix(in srgb, var(--color-primary) 45%, transparent); border-radius: var(--radius-md); }
.demo-account div { display: grid; gap: 2px; min-width: 0; }
.demo-account span { color: var(--color-on-dark-muted); font-size: var(--text-xs); }
.demo-account strong { color: var(--color-on-dark); font-size: var(--text-sm); overflow-wrap: anywhere; }
.demo-account button { grid-column: 1 / -1; min-height: var(--control-height-sm); color: var(--color-on-dark); background: transparent; border: 1px solid var(--color-primary); }
button { min-height: var(--control-height-md); border-radius: var(--radius-md); font-weight: 700; }
.primary { color: var(--color-on-primary); background: var(--color-primary); border: 1px solid var(--color-primary); }
.secondary, .new-chat { color: var(--color-on-dark); background: transparent; border: 1px solid var(--color-on-dark-muted); }
.pending-action { display: grid; gap: var(--space-3); padding-top: var(--space-3); border-top: 1px solid var(--color-navy-soft); }.pending-action > div { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-2); }
.quick { display: grid; gap: var(--space-2); }.quick button { padding-inline: var(--space-3); color: var(--color-on-dark); text-align: start; background: var(--color-navy-raised); border: 1px solid var(--color-navy-soft); }
.new-chat { margin-top: auto; }.error { color: var(--color-danger-soft) !important; }.pending { color: var(--color-warning-soft) !important; }
button:disabled { opacity: 0.55; }
</style>
