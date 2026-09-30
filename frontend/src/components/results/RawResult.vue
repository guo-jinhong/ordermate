<script setup lang="ts">
import { computed } from 'vue'

import { redactSensitive } from '../../lib/redact'

const props = defineProps<{ value: unknown }>()

const formatted = computed(() => {
  try {
    return JSON.stringify(redactSensitive(props.value), null, 2)
  } catch {
    return '返回数据无法格式化。'
  }
})
</script>

<template>
  <details class="raw-result">
    <summary>查看未识别数据</summary>
    <pre>{{ formatted }}</pre>
  </details>
</template>

<style scoped>
.raw-result {
  padding: var(--space-3);
  background: var(--color-surface-subtle);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-md);
}

summary {
  color: var(--color-primary-ink);
  cursor: pointer;
  font-weight: 700;
}

pre {
  max-height: 18rem;
  margin: var(--space-3) 0 0;
  overflow: auto;
  color: var(--color-ink);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
