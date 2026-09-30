<script setup lang="ts">
import type { PromptAction } from '../../types/chat'

defineProps<{ authenticated: boolean }>()
const emit = defineEmits<{ prompt: [action: PromptAction] }>()

const capabilities: Array<PromptAction & { icon: string; description: string }> = [
  {
    icon: '◇',
    label: '智能商品推荐',
    description: '根据预算和需求筛选',
    prompt: '推荐 100 元以内有库存的商品',
    authRequired: false,
  },
  {
    icon: '＋',
    label: '管理购物车',
    description: '查看商品、数量和金额',
    prompt: '查看我的购物车',
    authRequired: true,
  },
  {
    icon: '▤',
    label: '查询我的订单',
    description: '了解订单和支付状态',
    prompt: '查询我的最近订单',
    authRequired: true,
  },
  {
    icon: '?',
    label: '售后服务',
    description: '咨询规则并安全处理',
    prompt: '介绍一下取消订单规则',
    authRequired: false,
  },
]
</script>

<template>
  <section class="welcome" aria-labelledby="welcome-title">
    <div class="assistant-mark" aria-hidden="true"><span>AI</span><i /></div>
    <p class="eyebrow">OrderMate AI Commerce</p>
    <h1 id="welcome-title">今天想买些什么？</h1>
    <p class="intro">我可以理解你的预算和需求，帮助你搜索商品、管理购物车和查询订单。</p>

    <div class="capabilities" aria-label="常用能力">
      <button
        v-for="capability in capabilities"
        :key="capability.label"
        class="capability"
        type="button"
        @click="emit('prompt', capability)"
      >
        <span class="capability-icon" aria-hidden="true">{{ capability.icon }}</span>
        <span class="capability-copy">
          <strong>{{ capability.label }}</strong>
          <small>{{ capability.description }}</small>
        </span>
        <span v-if="capability.authRequired && !authenticated" class="lock">需登录</span>
        <span v-else class="arrow" aria-hidden="true">↗</span>
      </button>
    </div>

    <p class="auth-note">
      <span aria-hidden="true">i</span>
      {{ authenticated ? '账号已登录，购物车和订单功能可以直接使用。' : '商品搜索可以直接使用；购物车和订单功能需要先登录。' }}
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
  background-image:
    linear-gradient(rgba(79, 124, 255, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(79, 124, 255, 0.035) 1px, transparent 1px);
  background-size: 32px 32px;
}
.assistant-mark { position: relative; display: grid; place-items: center; width: 3.75rem; height: 3.75rem; color: var(--color-on-primary); background: linear-gradient(145deg, var(--color-primary), var(--color-ai)); border: 6px solid rgba(255, 255, 255, 0.82); border-radius: var(--radius-xl); box-shadow: var(--shadow-md); font-weight: 900; }
.assistant-mark i { position: absolute; right: -0.2rem; bottom: -0.2rem; width: 0.8rem; height: 0.8rem; background: var(--color-success); border: 3px solid var(--color-surface); border-radius: var(--radius-pill); }
.eyebrow { color: var(--color-primary); font-size: var(--text-xs); font-weight: 800; letter-spacing: 0.14em; text-transform: uppercase; }
h1 { color: var(--color-navy); font-size: var(--text-2xl); }
.intro { max-width: 40rem; color: var(--color-muted); }
.capabilities { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-3); width: min(100%, 44rem); margin-top: var(--space-3); }
.capability { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: var(--space-3); min-height: 5.25rem; padding: var(--space-4); text-align: left; background: var(--color-surface); border: 1px solid var(--color-line); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); transition: border-color var(--duration-fast) var(--ease-standard), box-shadow var(--duration-fast) var(--ease-standard), transform var(--duration-fast) var(--ease-standard); }
.capability:hover { border-color: var(--color-primary); box-shadow: var(--shadow-md); transform: translateY(-1px); }
.capability-icon { display: grid; place-items: center; width: 2.5rem; height: 2.5rem; color: var(--color-primary); background: var(--color-primary-soft); border-radius: var(--radius-md); font-size: var(--text-lg); font-weight: 900; }
.capability-copy { display: grid; gap: var(--space-1); }
.capability-copy strong { color: var(--color-navy); }
.capability-copy small { color: var(--color-muted); font-size: var(--text-sm); }
.arrow { color: var(--color-subtle); }
.lock { padding: var(--space-1) var(--space-2); color: var(--color-warning-hover); background: var(--color-warning-soft); border-radius: var(--radius-pill); font-size: var(--text-xs); font-weight: 800; white-space: nowrap; }
.auth-note { display: flex; align-items: center; justify-content: center; gap: var(--space-2); margin-top: var(--space-2); color: var(--color-muted); font-size: var(--text-sm); }
.auth-note > span { display: grid; place-items: center; width: 1.1rem; height: 1.1rem; color: var(--color-primary); background: var(--color-primary-soft); border-radius: var(--radius-pill); font-size: var(--text-xs); font-weight: 900; }

@media (max-width: 680px) {
  .welcome { align-content: start; padding: var(--space-6) var(--space-4); }
  .assistant-mark { width: 3.25rem; height: 3.25rem; }
  .capabilities { grid-template-columns: 1fr; }
  .capability { min-height: 4.5rem; }
}
</style>
