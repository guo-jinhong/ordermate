<script setup lang="ts">
import { useSessionStore } from '../../stores/session'
import IdentityAvatar from '../common/IdentityAvatar.vue'

defineProps<{ text: string }>()
const session = useSessionStore()
</script>

<template>
  <div class="message-row">
    <article class="message" aria-label="您的消息">{{ text }}</article>
    <IdentityAvatar kind="user" :username="session.username" size="sm" />
  </div>
</template>

<style scoped>
.message-row { display: flex; align-items: flex-end; justify-content: flex-end; gap: var(--space-2); min-width: 0; }
.message {
  width: fit-content;
  max-width: min(42rem, calc(100% - 2.5rem));
  padding: var(--space-3) var(--space-4);
  color: var(--color-primary-ink);
  background: var(--color-primary-soft);
  border-radius: var(--radius-lg) var(--radius-lg) var(--radius-sm) var(--radius-lg);
  line-height: var(--leading-relaxed);
  white-space: pre-wrap;
}
</style>
