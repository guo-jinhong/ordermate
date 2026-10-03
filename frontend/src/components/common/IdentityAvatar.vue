<script setup lang="ts">
import { computed } from 'vue'
import { Headset } from '@lucide/vue'

const props = withDefaults(defineProps<{
  kind?: 'assistant' | 'user'
  username?: string | null
  size?: 'sm' | 'md' | 'lg'
}>(), {
  kind: 'assistant',
  username: null,
  size: 'md',
})

const initial = computed(() => props.username?.trim().charAt(0).toLocaleUpperCase() || '我')
</script>

<template>
  <span class="identity-avatar" :data-kind="kind" :data-size="size" aria-hidden="true">
    <Headset v-if="kind === 'assistant'" :stroke-width="1.8" />
    <span v-else>{{ initial }}</span>
  </span>
</template>

<style scoped>
.identity-avatar { display: inline-grid; flex: 0 0 auto; width: 2.5rem; height: 2.5rem; place-items: center; color: var(--color-on-primary); background: var(--color-primary); border-radius: var(--radius-md); font-weight: 600; line-height: 1; }
.identity-avatar svg { width: 56%; height: 56%; }
.identity-avatar[data-kind="user"] { color: var(--color-primary-ink); background: var(--color-primary-soft); border: 1px solid color-mix(in srgb, var(--color-primary) 26%, var(--color-line)); box-shadow: none; }
.identity-avatar[data-size="sm"] { width: 1.875rem; height: 1.875rem; border-radius: var(--radius-sm); font-size: var(--text-sm); }
.identity-avatar[data-size="lg"] { width: 3.75rem; height: 3.75rem; border-radius: var(--radius-xl); }
</style>
