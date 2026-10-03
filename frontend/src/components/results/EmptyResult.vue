<script setup lang="ts">
import { PackageSearch, ReceiptText, ShoppingCart } from '@lucide/vue'
import { computed } from 'vue'

import { emptyResultCopy } from '../../lib/labels'
import type { PromptAction } from '../../types/chat'
import type { ResultKind } from '../../types/results'

const props = defineProps<{ kind: ResultKind }>()
const emit = defineEmits<{ prompt: [action: PromptAction] }>()

const copy = computed(() => emptyResultCopy(props.kind))
const prompts: Record<ResultKind, string> = {
  product: '推荐一些有货的商品',
  cart: '推荐一些有货的商品',
  order: '推荐一些商品',
}
</script>

<template>
  <section class="empty-result" :data-empty-kind="kind" role="status">
    <span class="mark" aria-hidden="true"><PackageSearch v-if="kind === 'product'" :size="18" /><ShoppingCart v-else-if="kind === 'cart'" :size="18" /><ReceiptText v-else :size="18" /></span>
    <div>
      <h3>{{ copy.title }}</h3>
      <p>{{ copy.description }}</p>
    </div>
    <button
      type="button"
      @click="emit('prompt', { prompt: prompts[kind], label: copy.actionLabel, authRequired: false })"
    >
      {{ copy.actionLabel }}
    </button>
  </section>
</template>

<style scoped>
.empty-result {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-4);
  background: var(--color-surface-subtle);
  border: 1px dashed var(--color-line-strong);
  border-radius: var(--radius-lg);
}

.mark {
  display: grid;
  width: 2.25rem;
  height: 2.25rem;
  place-items: center;
  color: var(--color-muted);
  background: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-pill);
  font-weight: 800;
}

h3 {
  color: var(--color-navy);
  font-size: var(--text-lg);
}

p {
  margin-top: var(--space-1);
  color: var(--color-muted);
  font-size: var(--text-sm);
}

button {
  min-height: var(--control-height-md);
  padding-inline: var(--space-4);
  color: var(--color-primary-ink);
  background: var(--color-primary-soft);
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-md);
  font-weight: 700;
}

button:hover {
  color: var(--color-on-primary);
  background: var(--color-primary);
}

@media (max-width: 680px) {
  .empty-result {
    grid-template-columns: auto minmax(0, 1fr);
  }

  button {
    grid-column: 1 / -1;
  }
}
</style>
