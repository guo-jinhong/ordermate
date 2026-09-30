<script setup lang="ts">
import { computed } from 'vue'

import type { ConfirmationPhase } from '../../types/chat'

const props = defineProps<{
  phase: ConfirmationPhase
  message: string | null
  data: unknown
}>()

const presentation = computed(() => {
  if (props.phase === 'executed') {
    return { title: '操作已完成', tone: 'success', fallback: '操作已经成功执行。' }
  }
  if (props.phase === 'cancelled') {
    return { title: '操作已取消', tone: 'neutral', fallback: '已放弃本次操作，数据没有被修改。' }
  }
  return { title: '操作未完成', tone: 'error', fallback: '操作执行失败，请重新发起。' }
})
</script>

<template>
  <section class="operation-result" :data-tone="presentation.tone">
    <span class="mark" aria-hidden="true">{{ phase === 'executed' ? '✓' : phase === 'cancelled' ? '—' : '!' }}</span>
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
