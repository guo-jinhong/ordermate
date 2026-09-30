<script setup lang="ts">
import { ref } from 'vue'

import { useChatStore } from '../../stores/chat'

const chat = useChatStore()
const draft = ref('')

const submit = async (): Promise<void> => {
  const message = draft.value.trim()
  if (!message || !chat.canSend) return
  draft.value = ''
  await chat.send(message)
}

const handleKeydown = (event: KeyboardEvent): void => {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  void submit()
}
</script>

<template>
  <form class="composer" aria-label="发送消息" @submit.prevent="submit">
    <label class="sr-only" for="chat-message">输入消息</label>
    <textarea id="chat-message" v-model="draft" rows="2" maxlength="4000" placeholder="描述你想查找或处理的内容…" :disabled="chat.sending" @keydown="handleKeydown" />
    <button v-if="chat.sending" class="cancel" type="button" @click="chat.cancel('user')">停止</button>
    <button v-else class="send" type="submit" :disabled="!draft.trim() || !chat.canSend">发送</button>
  </form>
</template>

<style scoped>
.composer { position: relative; z-index: 1; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--space-3); padding: var(--space-4) clamp(var(--space-4), 4vw, var(--space-10)); background: var(--color-surface-raised); border-top: 1px solid var(--color-line); }
textarea { width: 100%; min-height: 3.25rem; max-height: 10rem; padding: var(--space-3) var(--space-4); resize: vertical; background: var(--color-surface); border: 1px solid var(--color-line-strong); border-radius: var(--radius-lg); }
button { align-self: end; min-width: 5rem; min-height: var(--control-height-md); padding-inline: var(--space-4); border-radius: var(--radius-md); font-weight: 800; }
.send { color: var(--color-on-primary); background: var(--color-primary); border: 1px solid var(--color-primary); }
.send:hover:not(:disabled) { background: var(--color-primary-hover); }
.cancel { color: var(--color-danger); background: var(--color-danger-soft); border: 1px solid var(--color-danger); }
button:disabled { opacity: 0.55; }
</style>
