<script setup lang="ts">
import { ArrowUpRight, ClipboardList, Info, LifeBuoy, ShoppingCart, Sparkles } from '@lucide/vue'
import type { Component } from 'vue'

import type { PromptAction } from '../../types/chat'
import IdentityAvatar from '../common/IdentityAvatar.vue'

withDefaults(defineProps<{ authenticated: boolean; busy?: boolean; loginRequired?: boolean }>(), { busy: false, loginRequired: false })
const emit = defineEmits<{ prompt: [action: PromptAction] }>()

const capabilities: Array<PromptAction & { icon: Component; description: string }> = [
  {
    icon: Sparkles,
    label: '智能商品推荐',
    description: '根据预算和需求筛选',
    prompt: '推荐 100 元以内有货的商品',
    authRequired: false,
  },
  {
    icon: ShoppingCart,
    label: '管理购物车',
    description: '查看商品、数量和金额',
    prompt: '查看我的购物车',
    authRequired: true,
  },
  {
    icon: ClipboardList,
    label: '查询我的订单',
    description: '了解订单和支付状态',
    prompt: '查询我的最近订单',
    authRequired: true,
  },
  {
    icon: LifeBuoy,
    label: '售后服务',
    description: '咨询规则并安全处理',
    prompt: '介绍一下取消订单规则',
    authRequired: false,
  },
]
</script>

<template>
  <section class="welcome" aria-labelledby="welcome-title">
    <IdentityAvatar size="lg" />
    <p class="eyebrow">OrderMate 智能客服</p>
    <h1 id="welcome-title">有什么可以帮您？</h1>
    <p class="intro">我可以理解您的预算和需求，帮助您搜索商品、管理购物车和查询订单。</p>

    <div class="capabilities" aria-label="常用能力">
      <button
        v-for="capability in capabilities"
        :key="capability.label"
        class="capability"
        type="button"
        :disabled="busy"
        @click="emit('prompt', capability)"
      >
        <span class="capability-icon" aria-hidden="true"><component :is="capability.icon" :size="20" :stroke-width="1.9" /></span>
        <span class="capability-copy">
          <strong>{{ capability.label }}</strong>
          <small>{{ capability.description }}</small>
        </span>
        <span v-if="capability.authRequired && !authenticated" class="lock">需登录</span>
        <ArrowUpRight v-else class="arrow" :size="17" aria-hidden="true" />
      </button>
    </div>

    <p class="auth-note">
      <Info :size="16" aria-hidden="true" />
      {{ authenticated ? '账号已登录，购物车和订单功能可以直接使用。' : '普通聊天、商品推荐和售后规则咨询可以直接使用；购物车和订单功能需要先登录。' }}
    </p>
  </section>
</template>

<style scoped>
.welcome {
  position: relative;
  display: grid;
  align-content: center;
  justify-items: center;
  gap: var(--space-3);
  min-height: 0;
  padding: var(--space-8) var(--space-6);
  overflow-y: auto;
  text-align: center;
  background: var(--color-canvas);
}
.eyebrow { color: var(--color-primary-ink); font-size: var(--text-xs); font-weight: 600; letter-spacing: 0.08em; }
h1 { color: var(--color-navy); font-size: var(--text-2xl); font-weight: 600; letter-spacing: -0.03em; }
.intro { max-width: 32rem; color: var(--color-muted); }
.capabilities { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-3); width: min(100%, var(--content-width)); margin-top: var(--space-4); }
.capability { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: var(--space-3); min-height: 5.25rem; padding: var(--space-4); text-align: left; background: var(--color-surface); border: 1px solid var(--color-line); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); transition: border-color var(--duration-fast) var(--ease-standard), box-shadow var(--duration-fast) var(--ease-standard), transform var(--duration-fast) var(--ease-standard); }
.capability:disabled { opacity: 0.6; }.capability:hover:not(:disabled) { border-color: var(--color-primary); box-shadow: var(--shadow-md); transform: translateY(-2px); }
.capability-icon { display: grid; place-items: center; width: 2.5rem; height: 2.5rem; color: var(--color-primary-ink); background: var(--color-primary-soft); border-radius: var(--radius-md); }
.capability-copy { display: grid; gap: var(--space-1); }
.capability-copy strong { color: var(--color-navy); }
.capability-copy small { color: var(--color-muted); font-size: var(--text-sm); }
.arrow { color: var(--color-subtle); }
.lock { padding: var(--space-1) var(--space-2); color: var(--color-muted); background: var(--color-surface-subtle); border-radius: var(--radius-pill); font-size: var(--text-xs); font-weight: 600; white-space: nowrap; }
.auth-note { display: flex; align-items: center; justify-content: center; gap: var(--space-2); margin-top: var(--space-2); color: var(--color-muted); font-size: var(--text-sm); }
.auth-note svg { flex: 0 0 auto; color: var(--color-primary-ink); }

@media (max-width: 680px) {
  .welcome { align-content: start; gap: var(--space-2); padding: var(--space-6) var(--space-4); }
  .capabilities { gap: var(--space-2); margin-top: var(--space-3); }
  .capability { grid-template-columns: minmax(0, 1fr) auto; align-content: start; min-height: 6.25rem; gap: var(--space-2); padding: var(--space-3); }
  .capability-icon { grid-column: 1; width: 2rem; height: 2rem; }
  .capability-copy { grid-column: 1 / -1; }
  .arrow, .lock { grid-column: 2; grid-row: 1; align-self: center; }
  .capability-copy small { font-size: var(--text-xs); }
}
@media (max-width: 420px) {
  .capability { min-height: 6.25rem; }
  .capability-copy small { font-size: var(--text-xs); line-height: 1.4; }
  .auth-note { align-items: flex-start; text-align: left; }
}
</style>
