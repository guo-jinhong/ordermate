<script setup lang="ts">
import { CircleAlert, RefreshCw } from '@lucide/vue'
import { computed } from 'vue'
import { customerCopy } from '../../lib/catalogCopy'
import IdentityAvatar from '../common/IdentityAvatar.vue'
import StatusPill from '../common/StatusPill.vue'
import ConfirmationCard from '../confirm/ConfirmationCard.vue'
import ResultList from '../results/ResultList.vue'
import type { AssistantMessage as AssistantMessageModel } from '../../types/chat'
import type { PromptAction } from '../../types/chat'

const props = withDefaults(defineProps<{ message: AssistantMessageModel; canRetry?: boolean; busy?: boolean }>(), { canRetry: false, busy: false })
const hasCards = computed(() => ['product', 'cart', 'order'].includes(props.message.results.kind)
  && !(props.message.results.kind === 'product' && props.message.results.summaryOnly)
  && !props.message.confirmation && props.message.streamPhase === 'done')
const emit = defineEmits<{
  prompt: [action: PromptAction]
  confirm: [approved: boolean]
  verify: []
  retry: []
}>()
</script>

<template>
  <article class="message" aria-label="OrderMate 的消息">
    <header><IdentityAvatar size="sm" /><strong>OrderMate</strong><small>AI 助手</small></header>
    <p v-if="!hasCards && message.text" class="answer">{{ customerCopy(message.text) }}</p>
    <div v-if="message.status?.tone === 'error'" class="error-state" role="alert">
      <CircleAlert :size="18" aria-hidden="true" />
      <p>{{ message.status.text }}</p>
      <button v-if="canRetry" type="button" @click="emit('retry')"><RefreshCw :size="15" aria-hidden="true" />重新发送</button>
    </div>
    <StatusPill
      v-else-if="message.status"
      :label="message.status.text"
      :tone="message.status.tone"
    />
    <ResultList :payload="message.results" :busy="busy" @prompt="emit('prompt', $event)" />
    <details v-if="hasCards && message.text" class="answer-details">
      <summary>查看助手说明</summary>
      <p class="answer">{{ customerCopy(message.text) }}</p>
    </details>
    <ConfirmationCard
      v-if="message.confirmation"
      :confirmation="message.confirmation"
      :phase="message.confirmationPhase"
      :busy="busy"
      :result="message.confirmationResult"
      @confirm="emit('confirm', $event)"
      @verify="emit('verify')"
    />
  </article>
</template>

<style scoped>
.message {
  display: grid;
  gap: var(--space-2);
  min-width: 0;
  width: 100%;
  max-width: var(--content-width);
  padding: var(--space-3) 0;
  background: transparent;
  border: 0;
  border-radius: var(--radius-lg) var(--radius-lg) var(--radius-lg) var(--radius-sm);
  box-shadow: none;
}

header { display: flex; align-items: center; gap: var(--space-2); color: var(--color-navy); }
header strong { font-size: 13px; }
header :deep(.identity-avatar) { width: 24px; height: 24px; }
header small { color: var(--color-muted); font-size: var(--text-xs); font-weight: 500; }
.answer { line-height: var(--leading-relaxed); white-space: pre-wrap; }
.error-state { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); padding: var(--space-3); color: var(--color-danger); background: var(--color-danger-soft); border: 1px solid color-mix(in srgb, var(--color-danger) 22%, var(--color-line)); border-radius: var(--radius-md); }
.error-state p { flex: 1 1 12rem; }
.error-state button { display: inline-flex; align-items: center; gap: var(--space-1); min-height: var(--control-height-sm); padding-inline: var(--space-2); color: var(--color-danger); background: var(--color-surface); border: 1px solid currentColor; border-radius: var(--radius-sm); font-weight: 700; }
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
