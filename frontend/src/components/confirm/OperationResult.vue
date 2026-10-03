<script setup lang="ts">
import { Check, Minus, X } from '@lucide/vue'
import { computed } from 'vue'

import type { ConfirmationPhase } from '../../types/chat'

const props = defineProps<{
  action?: string
  phase: ConfirmationPhase
  message: string | null
  data: unknown
}>()

const presentation = computed(() => {
  if (props.phase === 'executed') {
    return { title: '操作已完成', tone: 'success', fallback: '已为您完成这次操作。' }
  }
  if (props.phase === 'cancelled') {
    const fallback = props.action === 'cancel_order' ? '本次未操作，您的订单未取消。'
      : props.action === 'create_order' ? '本次未下单。'
        : props.action === 'pay_order' ? '本次未支付，订单保持不变。'
          : props.action?.includes('cart') ? '本次未操作，购物车保持不变。'
            : '本次未操作，购物车和订单保持不变。'
    return { title: '本次未操作', tone: 'neutral', fallback }
  }
  if (props.phase === 'unknown') {
    return { title: '暂时无法确认操作结果', tone: 'neutral', fallback: '请先查看购物车或订单确认结果，暂时不要重复提交。' }
  }
  return { title: '操作未完成', tone: 'error', fallback: '这次操作未完成，请稍后再试。' }
})
</script>

<template>
  <section class="operation-result" :data-tone="presentation.tone">
    <span class="mark" aria-hidden="true"><Check v-if="phase === 'executed'" :size="17" /><Minus v-else-if="phase === 'cancelled'" :size="17" /><X v-else :size="17" /></span>
    <div>
      <strong>{{ presentation.title }}</strong>
      <p>{{ message || presentation.fallback }}</p>
    </div>
  </section>
</template>

<style scoped>
.operation-result { display: flex; align-items: flex-start; gap: var(--space-3); padding: var(--space-3); border: 1px solid var(--color-line); border-radius: var(--radius-md); }.mark { display: grid; flex: 0 0 auto; width: 1.75rem; height: 1.75rem; place-items: center; border-radius: var(--radius-pill); font-weight: 900; }.operation-result div { display: grid; gap: var(--space-1); }.operation-result p { color: var(--color-muted); font-size: var(--text-sm); }
[data-tone="success"] { background: var(--color-success-soft); border-color: var(--color-success); }[data-tone="success"] .mark { color: var(--color-on-primary); background: var(--color-success); }
[data-tone="neutral"] { background: var(--color-surface-subtle); }[data-tone="neutral"] .mark { color: var(--color-ink); background: var(--color-line); }
[data-tone="error"] { background: var(--color-danger-soft); border-color: var(--color-danger); }[data-tone="error"] .mark { color: var(--color-on-primary); background: var(--color-danger); }
</style>
