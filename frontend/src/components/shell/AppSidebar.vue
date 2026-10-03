<script setup lang="ts">
import { ChevronDown, ClipboardList, LogIn, MessageSquarePlus, ShoppingCart, Sparkles, X } from '@lucide/vue'
import { nextTick, ref, watch } from 'vue'

import type { HealthStatus } from '../../composables/useHealthPoll'
import { customerErrorMessage } from '../../lib/http'
import { useChatStore } from '../../stores/chat'
import { useSessionStore } from '../../stores/session'
import { useViewStore } from '../../stores/view'
import IdentityAvatar from '../common/IdentityAvatar.vue'

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
const usernameInput = ref<HTMLInputElement | null>(null)
const confirmNewChat = ref(false)

// 登录按需展开，并直接定位到用户名。
watch(() => session.pendingAction, (action) => {
  if (action && !session.isAuthenticated) view.loginPanelOpen = true
}, { immediate: true })
watch(() => view.loginPanelOpen, async (open) => {
  if (open && !session.isAuthenticated) {
    await nextTick()
    usernameInput.value?.focus()
  }
})
const requestNewChat = (): void => {
  if (chat.hasConversation) confirmNewChat.value = true
  else void chat.clearConversation()
}
const startNewChat = async (): Promise<void> => {
  await chat.clearConversation()
  confirmNewChat.value = false
  view.closeSidebar()
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
    loginError.value = customerErrorMessage(error, '登录失败，请检查账号信息。')
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
  emit('announce', '本次未继续操作，您仍保持登录状态。')
}

const logout = async (): Promise<void> => {
  await chat.clearConversation()
  session.clear()
  view.loginPanelOpen = false
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
    <header class="brand"><IdentityAvatar /><div><strong>OrderMate</strong><small>智能电商客服</small></div><button type="button" aria-label="关闭功能栏" @click="emit('close')"><X :size="20" aria-hidden="true" /></button></header>
    <button class="new-chat" type="button" @click="requestNewChat"><MessageSquarePlus :size="18" aria-hidden="true" />新建会话</button>
    <section class="quick" aria-labelledby="quick-title">
      <h2 id="quick-title">快捷操作</h2>
      <button type="button" :disabled="!chat.canSend" @click="runPrompt('推荐 100 元以内有货的商品', '商品推荐')"><Sparkles :size="18" aria-hidden="true" />商品推荐</button>
      <button type="button" :disabled="!chat.canSend" @click="runPrompt('查看我的购物车', '查看购物车', true)"><ShoppingCart :size="18" aria-hidden="true" />查看购物车</button>
      <button type="button" :disabled="!chat.canSend" @click="runPrompt('查看我的订单', '查看订单', true)"><ClipboardList :size="18" aria-hidden="true" />查看订单</button>
    </section>
    <div v-if="confirmNewChat" class="clear-confirm" role="group" aria-label="确认新建会话">
      <p>新建会话将清空当前对话，是否继续？</p>
      <div><button class="secondary" type="button" @click="confirmNewChat = false">保留对话</button><button class="primary" type="button" @click="startNewChat">确认新建</button></div>
    </div>
    <section class="account" aria-labelledby="account-title">
      <h2 id="account-title">账号</h2>
      <template v-if="session.isAuthenticated">
        <div class="account-identity"><IdentityAvatar kind="user" :username="session.username" /><div><small>已登录</small><strong>{{ session.username ?? '当前用户' }}</strong></div></div>
        <button class="secondary" type="button" @click="logout">退出登录</button>
      </template>
      <template v-else>
        <button class="account-entry" type="button" :aria-expanded="view.loginPanelOpen" aria-controls="sidebar-login" @click="view.loginPanelOpen = !view.loginPanelOpen">
          <LogIn :size="18" aria-hidden="true" /><span>登录账号</span><ChevronDown :size="16" aria-hidden="true" :class="{ rotated: view.loginPanelOpen }" />
        </button>
        <p v-if="!view.loginPanelOpen">登录后可查看个人购物车与订单。</p>
      <form v-if="view.loginPanelOpen" id="sidebar-login" @submit.prevent="submitLogin">
        <p>登录后可查看个人购物车与订单。</p>
        <label>用户名<input ref="usernameInput" v-model="username" autocomplete="username" placeholder="请输入用户名" /></label>
        <label>密码<input v-model="password" type="password" autocomplete="current-password" placeholder="请输入密码" /></label>
        <p v-if="session.pendingAction" class="pending">登录后继续“{{ session.pendingAction.label }}”</p>
        <p v-if="loginError" class="error" role="alert">{{ loginError }}</p>
        <button class="primary" type="submit" :disabled="loggingIn || !username.trim() || !password">{{ loggingIn ? '登录中…' : '登录' }}</button>
      </form>
      </template>
      <div v-if="session.isAuthenticated && session.pendingAction" class="pending-action" role="status">
        <p>登录成功，是否继续“{{ session.pendingAction.label }}”？</p>
        <div>
          <button type="button" class="secondary" @click="cancelPendingAction">暂不继续</button>
          <button type="button" class="primary" :disabled="!chat.canSend" @click="continuePendingAction">继续{{ session.pendingAction.label }}</button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
/* 第一版：侧栏减少卡片层级，账号按需展开。 */
.sidebar-content { display: flex; flex-direction: column; gap: var(--space-5); height: 100%; padding: var(--space-5); overflow-y: auto; color: var(--color-ink); background: var(--color-surface); border-right: 1px solid var(--color-line); }
.brand { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-3); }
.brand div { display: grid; flex: 1; gap: var(--space-1); }.brand strong { font-size: var(--text-lg); font-weight: 650; }.brand small { color: var(--color-muted); font-size: var(--text-xs); }.brand button { display: grid; width: var(--control-height-md); place-items: center; color: var(--color-muted); background: transparent; border: 0; }
.new-chat { order: 1; display: flex; align-items: center; justify-content: center; gap: var(--space-2); color: var(--color-primary-ink); background: var(--color-primary-soft); border: 1px solid transparent; }
.quick { order: 2; display: grid; gap: var(--space-2); }.quick button { display: flex; align-items: center; gap: var(--space-3); padding-inline: var(--space-3); color: var(--color-muted); text-align: start; background: transparent; border: 1px solid transparent; }.quick button svg { flex-shrink: 0; }.quick button:hover:not(:disabled) { color: var(--color-primary-ink); background: var(--color-primary-soft); }
h2 { margin-bottom: var(--space-2); color: var(--color-muted); font-size: var(--text-xs); font-weight: 500; }
.account { order: 4; display: grid; gap: var(--space-3); margin-top: auto; padding-top: var(--space-5); border-top: 1px solid var(--color-line); }
.account-identity { display: flex; align-items: center; gap: var(--space-3); min-width: 0; }.account-identity > div { display: grid; min-width: 0; }.account-identity small { color: var(--color-muted); }.account-identity strong { overflow-wrap: anywhere; }
.account p, .clear-confirm p { color: var(--color-muted); font-size: var(--text-sm); }
.account-entry { display: flex; align-items: center; gap: var(--space-2); padding-inline: var(--space-3); color: var(--color-ink); background: var(--color-surface-subtle); border: 1px solid var(--color-line); }.account-entry span { flex: 1; text-align: left; }.rotated { transform: rotate(180deg); }
form, label { display: grid; gap: var(--space-2); } form { gap: var(--space-3); } label { color: var(--color-muted); font-size: var(--text-sm); }
input { width: 100%; min-height: var(--control-height-md); padding-inline: var(--space-3); color: var(--color-ink); background: var(--color-surface); border: 1px solid var(--color-line-strong); border-radius: var(--radius-sm); }
button { min-height: var(--control-height-md); border-radius: var(--radius-sm); font-weight: 500; transition: background var(--duration-fast) var(--ease-standard); }
.primary { color: var(--color-on-primary); background: var(--color-primary); border: 1px solid var(--color-primary); }.primary:hover:not(:disabled) { background: var(--color-primary-hover); }
.secondary { color: var(--color-muted); background: var(--color-surface); border: 1px solid var(--color-line); }
.pending-action { display: grid; gap: var(--space-3); padding-top: var(--space-3); border-top: 1px solid var(--color-line); }.pending-action > div, .clear-confirm > div { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-2); }
.clear-confirm { order: 3; display: grid; gap: var(--space-3); padding: var(--space-3); background: var(--color-surface-subtle); border: 1px solid var(--color-line); border-radius: var(--radius-md); }
.error { color: var(--color-danger) !important; }.pending { padding: var(--space-2); color: var(--color-primary-ink) !important; background: var(--color-primary-soft); border-radius: var(--radius-sm); }
button:disabled { opacity: 0.55; }
@media (min-width: 901px) { .brand button { display: none; } }
</style>
