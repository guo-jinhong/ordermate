<script setup lang="ts">
defineProps<{ text: string }>()
</script>

<template>
  <article class="message" aria-label="你的消息">{{ text }}</article>
</template>

<style scoped>
.message {
  width: fit-content;
  max-width: min(42rem, 88%);
  margin-inline-start: auto;
  padding: var(--space-3) var(--space-4);
  color: var(--color-on-primary);
  background: var(--color-primary);
  border-radius: var(--radius-lg) var(--radius-lg) var(--radius-sm) var(--radius-lg);
  line-height: var(--leading-relaxed);
  white-space: pre-wrap;
}
</style>
