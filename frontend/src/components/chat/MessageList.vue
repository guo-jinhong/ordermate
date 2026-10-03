<script setup lang="ts">
import { ArrowDown } from '@lucide/vue'
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
  confirm: [approved: boolean, messageId: string]
}>()

const jumpToLatest = (): void => {
  list.value?.scrollTo?.({ top: list.value.scrollHeight, behavior: 'auto' })
  followsLatestMessage.value = true
}

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
    const latestMessage = chat.messages.at(-1)
    // 卡片内连续操作保持当前阅读位置；待确认操作仍滚动到确认卡片。
    if (latestMessage && latestMessage.role !== 'system' && latestMessage.preserveScroll && !(latestMessage.role === 'assistant' && latestMessage.confirmation && latestMessage.confirmationPhase === 'pending')) return
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
  <div class="message-area">
  <section ref="list" class="message-list" aria-label="对话消息" @scroll.passive="updateFollowState">
    <template v-for="message in chat.messages" :key="message.id">
      <UserMessage v-if="message.role === 'user'" :text="message.text" />
      <AssistantMessage
        v-else-if="message.role === 'assistant'"
        :message="message"
        :busy="!chat.canSend || chat.latestAssistant?.confirmationPhase === 'submitting'"
        :can-retry="message.id === chat.latestAssistant?.id && chat.canSend"
        @prompt="emit('prompt', $event)"
        @confirm="emit('confirm', $event, message.id)"
        @verify="chat.verifyOperation(message.id)"
        @retry="chat.retryLast()"
      />
      <p v-else class="system-notice" role="status">{{ message.text }}</p>
    </template>
  </section>
    <button v-if="!followsLatestMessage" class="jump-latest" type="button" @click="jumpToLatest"><ArrowDown :size="16" aria-hidden="true" />回到最新消息</button>
  </div>
</template>

<style scoped>
.message-area { position: relative; min-height: 0; overflow: hidden; }
.jump-latest { position: absolute; bottom: var(--space-3); left: 50%; transform: translateX(-50%); display: flex; align-items: center; gap: var(--space-2); min-height: 36px; padding: 4px 10px; font-size: 12px; color: var(--color-primary-ink); background: var(--color-surface); border: 1px solid var(--color-line); border-radius: var(--radius-pill); box-shadow: var(--shadow-md); white-space: nowrap; }

.message-list {
  display: grid;
  align-content: start;
  gap: var(--space-3);
  min-height: 0;
  height: 100%;
  padding: var(--space-6) max(var(--space-4), calc((100% - var(--content-width)) / 2));
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
@media (max-width: 680px) { .message-list { padding: 12px; scrollbar-gutter: auto; } }
</style>
