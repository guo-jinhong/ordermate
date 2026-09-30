<script setup lang="ts">
withDefaults(
  defineProps<{
    label: string
    tone?: 'neutral' | 'loading' | 'success' | 'warning' | 'error'
  }>(),
  { tone: 'neutral' },
)
</script>

<template>
  <span class="pill" :data-tone="tone"><span class="dot" aria-hidden="true" />{{ label }}</span>
</template>

<style scoped>
.pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--control-height-sm);
  padding-inline: var(--space-3);
  color: var(--color-muted);
  background: var(--color-surface-subtle);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-pill);
  font-size: var(--text-sm);
  font-weight: 700;
}

.dot {
  width: 0.5rem;
  height: 0.5rem;
  background: var(--color-subtle);
  border-radius: var(--radius-pill);
}

[data-tone="loading"] .dot { background: var(--color-primary); }
[data-tone="success"] .dot { background: var(--color-success); }
[data-tone="warning"] .dot { background: var(--color-warning); }
[data-tone="error"] .dot { background: var(--color-danger); }
</style>
