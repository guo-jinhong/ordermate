<script setup lang="ts">
import { ArrowUp, RotateCcw, Square } from '@lucide/vue'
import { nextTick, onMounted, ref, watch } from 'vue'

import { useSessionStore } from '../../stores/session'
import { useChatStore } from '../../stores/chat'

const chat = useChatStore()
const session = useSessionStore()
const draft = ref('')
const textarea = ref<HTMLTextAreaElement | null>(null)
const failedDraft = ref('')

// 输入随内容增高；失败后允许恢复原文继续编辑。
const resize = (): void => {
  const element = textarea.value
  if (!element) return
  element.style.height = 'auto'
  element.style.height = `${Math.min(element.scrollHeight, 160)}px`
}
watch(draft, async () => { await nextTick(); resize() })
onMounted(resize)
watch(() => chat.lastError, (error) => { if (!error) failedDraft.value = '' })
const restoreDraft = async (): Promise<void> => {
  draft.value = failedDraft.value
  failedDraft.value = ''
  await nextTick()
  textarea.value?.focus()
}
const submit = async (): Promise<void> => {
  const message = draft.value.trim()
  if (!message || !chat.canSend) return
  draft.value = ''
  failedDraft.value = ''
  await chat.send(message)
  if (chat.lastError) failedDraft.value = message
  if (session.pendingAction && !session.isAuthenticated) return
  await nextTick()
  textarea.value?.focus()
}
const handleKeydown = (event: KeyboardEvent): void => {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  void submit()
}
</script>

<template>
  <form class="composer" aria-label="发送消息" @submit.prevent="submit">
    <div class="composer-content">
      <div v-if="failedDraft" class="draft-recovery" role="status">
        <span>发送失败，可以恢复原文修改后再发。</span>
        <button type="button" @click="restoreDraft"><RotateCcw :size="14" aria-hidden="true" />恢复内容</button>
      </div>
      <div class="input-shell">
        <label class="sr-only" for="chat-message">输入消息</label>
        <textarea id="chat-message" ref="textarea" v-model="draft" rows="1" maxlength="4000" placeholder="描述您想查找或处理的内容…" :disabled="chat.sending" aria-describedby="composer-hint" @keydown="handleKeydown" />
        <button v-if="chat.sending" class="cancel" type="button" aria-label="停止回复" title="停止回复" @click="chat.cancel('user')"><Square :size="16" aria-hidden="true" /></button>
        <button v-else class="send" type="submit" aria-label="发送" title="发送消息" :disabled="!draft.trim() || !chat.canSend"><ArrowUp :size="21" :stroke-width="2" aria-hidden="true" /></button>
      </div>
      <p id="composer-hint" class="hint sr-only"><span class="keyboard-hint">Enter 发送 · Shift + Enter 换行</span><span>重要操作会先请您确认</span></p>
    </div>
  </form>
</template>

<style scoped>
.composer { position: relative; z-index: 1; padding: var(--space-4) var(--space-6) max(var(--space-3), env(safe-area-inset-bottom)); background: var(--color-canvas); }
.composer-content { width: min(100%, var(--content-width)); margin-inline: auto; }
.input-shell { display: flex; align-items: flex-end; gap: var(--space-2); padding: var(--space-2); background: var(--color-surface); border: 1px solid var(--color-line-strong); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); transition: border-color var(--duration-fast) var(--ease-standard), box-shadow var(--duration-fast) var(--ease-standard); }
.input-shell:focus-within { border-color: var(--color-primary); box-shadow: var(--shadow-focus); }
textarea { flex: 1; min-width: 0; width: 100%; min-height: 2.75rem; max-height: 10rem; padding: 10px 8px; resize: none; overflow-y: auto; background: transparent; border: 0; border-radius: var(--radius-sm); line-height: 1.5; }
textarea:focus-visible { outline: none; box-shadow: none; }
.input-shell button { display: grid; flex: 0 0 auto; place-items: center; width: 2.625rem; height: 2.625rem; margin-bottom: 3px; border: 0; border-radius: var(--radius-md); transition: background var(--duration-fast) var(--ease-standard); }
.send { color: var(--color-on-primary); background: var(--color-primary); }.send:hover:not(:disabled) { background: var(--color-primary-hover); }.send:disabled { color: var(--color-subtle); background: var(--color-surface-subtle); }
.cancel { color: var(--color-primary-ink); background: var(--color-primary-soft); }
.hint { display: flex; justify-content: space-between; gap: var(--space-2); margin-top: var(--space-2); color: var(--color-muted); font-size: var(--text-xs); }
.draft-recovery { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-2); margin-bottom: var(--space-2); color: var(--color-muted); font-size: var(--text-sm); }.draft-recovery button { display: inline-flex; align-items: center; gap: var(--space-1); min-height: var(--control-height-sm); color: var(--color-primary-ink); background: transparent; border: 0; }
@media (max-width: 680px) { .composer { padding: 8px 12px max(8px, env(safe-area-inset-bottom)); }.hint { justify-content: center; }.keyboard-hint { display: none; } }
</style>
