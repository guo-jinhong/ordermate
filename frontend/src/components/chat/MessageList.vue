<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

import { useChatStore } from '../../stores/chat'
import type { PromptAction } from '../../types/chat'
import AssistantMessage from './AssistantMessage.vue'
import UserMessage from './UserMessage.vue'

const chat = useChatStore()
const list = ref<HTMLElement | null>(null)
const followsLatestMessage = ref(true)
let previousMessageCount = chat.messages.length
const emit = defineEmits<{
  prompt: [action: PromptAction]
  confirm: [approved: boolean]
}>()

const updateFollowState = (): void => {
  const element = list.value
  if (!element) return
  const remaining = element.scrollHeight - element.scrollTop - element.clientHeight
  followsLatestMessage.value = remaining <= 48
}

watch(
  () => chat.messages,
  async () => {
    const messageWasAdded = chat.messages.length > previousMessageCount
    previousMessageCount = chat.messages.length
    if (!messageWasAdded && !followsLatestMessage.value) return

    await nextTick()
    const element = list.value
    if (!element) return
    element.scrollTo?.({
      // 长回复对齐开头；短回复沿用底部跟随，用户向上阅读时不抢滚动。
      top: (() => {
        const latest = element.lastElementChild as HTMLElement | null
        if (!latest || latest.getBoundingClientRect().height <= element.clientHeight) return element.scrollHeight
        return element.scrollTop + latest.getBoundingClientRect().top - element.getBoundingClientRect().top
      })(),
      behavior: 'auto',
    })
  },
  { deep: true, flush: 'post' },
)
</script>

<template>
  <section ref="list" class="message-list" aria-label="对话消息" @scroll.passive="updateFollowState">
    <template v-for="message in chat.messages" :key="message.id">
      <UserMessage v-if="message.role === 'user'" :text="message.text" />
      <AssistantMessage
        v-else-if="message.role === 'assistant'"
        :message="message"
        @prompt="emit('prompt', $event)"
        @confirm="emit('confirm', $event)"
      />
      <p v-else class="system-notice" role="status">{{ message.text }}</p>
    </template>
  </section>
</template>

<style scoped>
.message-list {
  display: grid;
  align-content: start;
  gap: var(--space-5);
  min-height: 0;
  padding: var(--space-6) clamp(var(--space-4), 4vw, var(--space-10));
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  overflow-anchor: none;
}
.system-notice {
  justify-self: center;
  padding: var(--space-2) var(--space-3);
  color: var(--color-muted);
  background: var(--color-surface-subtle);
  border-radius: var(--radius-pill);
  font-size: var(--text-sm);
}
</style>
