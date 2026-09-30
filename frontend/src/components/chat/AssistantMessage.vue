<script setup lang="ts">
import { computed } from 'vue'
import { customerCopy } from '../../lib/catalogCopy'
import StatusPill from '../common/StatusPill.vue'
import ConfirmationCard from '../confirm/ConfirmationCard.vue'
import ResultList from '../results/ResultList.vue'
import type { AssistantMessage as AssistantMessageModel } from '../../types/chat'
import type { PromptAction } from '../../types/chat'

const props = defineProps<{ message: AssistantMessageModel }>()
const hasCards = computed(() => ['product', 'cart', 'order'].includes(props.message.results.kind)
  && !props.message.confirmation && props.message.streamPhase === 'done')
const emit = defineEmits<{
  prompt: [action: PromptAction]
  confirm: [approved: boolean]
}>()
</script>

<template>
  <article class="message" aria-label="OrderMate 的消息">
    <header><span class="avatar" aria-hidden="true">AI</span><strong>OrderMate</strong></header>
    <details v-if="hasCards && message.text" class="answer-details">
      <summary>查看助手说明</summary>
      <p class="answer">{{ customerCopy(message.text) }}</p>
    </details>
    <p v-else-if="message.text" class="answer">{{ customerCopy(message.text) }}</p>
    <StatusPill
      v-if="message.status"
      :label="message.status.text"
      :tone="message.status.tone"
    />
    <p v-if="message.reference" class="reference">
      已结合{{ message.reference.source }}：{{ message.reference.value }}
    </p>
    <ResultList :payload="message.results" @prompt="emit('prompt', $event)" />
    <ConfirmationCard
      v-if="message.confirmation"
      :confirmation="message.confirmation"
      :phase="message.confirmationPhase"
      :result="message.confirmationResult"
      @confirm="emit('confirm', $event)"
    />
  </article>
</template>

<style scoped>
.message {
  display: grid;
  gap: var(--space-3);
  max-width: 46rem;
  padding: var(--space-4);
  background: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-lg) var(--radius-lg) var(--radius-lg) var(--radius-sm);
  box-shadow: var(--shadow-sm);
}

header { display: flex; align-items: center; gap: var(--space-2); color: var(--color-navy); }
.avatar {
  display: grid;
  width: 1.75rem;
  height: 1.75rem;
  place-items: center;
  color: var(--color-on-primary);
  background: var(--color-ai);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: 800;
}
.answer { line-height: var(--leading-relaxed); white-space: pre-wrap; }
.answer-details summary { cursor: pointer; color: var(--color-muted); font-size: var(--text-sm); }
.answer-details[open] .answer { margin-top: var(--space-2); }
.reference {
  padding: var(--space-2) var(--space-3);
  color: var(--color-primary-ink);
  background: var(--color-primary-soft);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
}
</style>
