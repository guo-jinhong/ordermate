<script setup lang="ts">
import { CircleAlert, PackageCheck, TriangleAlert } from '@lucide/vue'
import { computed, onMounted, onUnmounted, ref, useId } from 'vue'
import { customerCopy } from '../../lib/catalogCopy'

import { confirmationPresentation } from '../../lib/labels'
import type { Confirmation } from '../../types/api'
import type { AssistantMessage, ConfirmationPhase } from '../../types/chat'
import ConfirmFacts from './ConfirmFacts.vue'
import OperationResult from './OperationResult.vue'

const props = defineProps<{
  confirmation: Confirmation
  phase: ConfirmationPhase
  result: AssistantMessage['confirmationResult']
  busy?: boolean
}>()
const emit = defineEmits<{ confirm: [approved: boolean]; verify: [] }>()
const titleId = useId()
const presentation = computed(() => confirmationPresentation(props.confirmation.action))
const terminal = computed(() => ['executed', 'cancelled', 'failed', 'unknown'].includes(props.phase))
const now = ref(Date.now())
const expiresAt = computed(() => props.confirmation.expires_at ? Date.parse(props.confirmation.expires_at) : NaN)
const expired = computed(() => Number.isFinite(expiresAt.value) && now.value >= expiresAt.value)
const remaining = computed(() => Math.max(0, Math.ceil((expiresAt.value - now.value) / 1000)))
const syncTime = () => { now.value = Date.now() }
let timer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  timer = setInterval(syncTime, 1000)
  document.addEventListener('visibilitychange', syncTime)
  window.addEventListener('focus', syncTime)
})
onUnmounted(() => {
  if (timer != null) clearInterval(timer)
  document.removeEventListener('visibilitychange', syncTime)
  window.removeEventListener('focus', syncTime)
})
function submit(approved: boolean) {
  syncTime()
  if (!expired.value && !props.busy && props.phase === 'pending') emit('confirm', approved)
}
</script>

<template>
  <section
    class="confirmation-card"
    :data-tone="presentation.tone"
    role="alertdialog"
    aria-modal="false"
    :aria-labelledby="titleId"
  >
    <header>
      <span class="icon" aria-hidden="true">
        <TriangleAlert v-if="presentation.tone === 'danger'" :size="19" />
        <PackageCheck v-else-if="presentation.tone === 'primary'" :size="19" />
        <CircleAlert v-else :size="19" />
      </span>
      <div>
        <span class="badge">{{ presentation.badge }}</span>
        <h3 :id="titleId">{{ presentation.title }}</h3>
      </div>
    </header>
    <p class="description">{{ customerCopy(confirmation.description) }}</p>
    <ConfirmFacts :action="confirmation.action" :args="confirmation.arguments" />
    <p class="impact"><strong>确认后：</strong>{{ presentation.impact }}</p>
    <p v-if="phase === 'pending' && Number.isFinite(expiresAt)" role="status">
      {{ expired ? '本次确认已过期，请重新发起操作。' : `此确认将在 ${remaining} 秒后失效，未确认不会自动操作。` }}
    </p>

    <OperationResult
      v-if="terminal"
      :action="confirmation.action"
      :phase="phase"
      :message="result?.message ? customerCopy(result.message) : null"
      :data="result?.data ?? null"
    />
    <footer v-if="phase === 'unknown'">
      <button type="button" :disabled="busy" @click="emit('verify')">{{ busy ? '正在处理…' : '核实操作结果' }}</button>
    </footer>
    <footer v-else-if="!terminal">
      <button
        type="button"
        :disabled="busy || phase === 'submitting' || expired"
        @click="submit(false)"
      >
        先不操作
      </button>
      <button
        class="confirm"
        type="button"
        :disabled="busy || phase === 'submitting' || expired"
        @click="submit(true)"
      >
        {{ phase === 'submitting' ? '正在提交…' : presentation.confirmLabel }}
      </button>
    </footer>
  </section>
</template>

<style scoped>
.confirmation-card { display: grid; gap: var(--space-3); padding: var(--space-4); background: var(--color-surface); border: 1px solid var(--color-warning); border-inline-start-width: 4px; border-radius: var(--radius-lg); }.confirmation-card[data-tone="danger"] { border-color: var(--color-danger); }.confirmation-card[data-tone="primary"] { border-color: var(--color-primary); }
header { display: flex; align-items: center; gap: var(--space-3); }.icon { display: grid; width: 2.25rem; height: 2.25rem; place-items: center; color: var(--color-on-primary); background: var(--color-warning); border-radius: var(--radius-pill); font-weight: 900; }[data-tone="danger"] .icon { background: var(--color-danger); }[data-tone="primary"] .icon { background: var(--color-primary); }
header > div { display: grid; gap: var(--space-1); }.badge { width: fit-content; padding: var(--space-1) var(--space-2); color: var(--color-warning); background: var(--color-warning-soft); border-radius: var(--radius-pill); font-size: var(--text-xs); font-weight: 800; }[data-tone="danger"] .badge { color: var(--color-danger); background: var(--color-danger-soft); }[data-tone="primary"] .badge { color: var(--color-primary-ink); background: var(--color-primary-soft); }
h3 { color: var(--color-navy); font-size: var(--text-lg); }.description, .impact { color: var(--color-muted); line-height: var(--leading-relaxed); }.impact { padding: var(--space-3); background: var(--color-surface-subtle); border-radius: var(--radius-md); font-size: var(--text-sm); }.impact strong { color: var(--color-ink); }
footer { display: flex; justify-content: flex-end; gap: var(--space-2); }button { min-height: var(--control-height-md); padding-inline: var(--space-4); color: var(--color-ink); background: var(--color-surface); border: 1px solid var(--color-line-strong); border-radius: var(--radius-md); font-weight: 800; }.confirm { color: var(--color-on-primary); background: var(--color-danger); border-color: var(--color-danger); }[data-tone="warning"] .confirm { background: var(--color-warning); border-color: var(--color-warning); }[data-tone="primary"] .confirm { background: var(--color-primary); border-color: var(--color-primary); }button:disabled { cursor: wait; opacity: 0.55; }
@media (max-width: 680px) { footer { display: grid; grid-template-columns: 1fr 1fr; } }
</style>
