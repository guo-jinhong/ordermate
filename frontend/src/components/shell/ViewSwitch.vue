<script setup lang="ts">
import { nextTick, ref } from 'vue'

import { useViewStore } from '../../stores/view'
import type { ViewMode } from '../../stores/view'

const view = useViewStore()
const modes: Array<{ value: ViewMode; label: string }> = [
  { value: 'customer', label: '对话' },
  { value: 'developer', label: '调试' },
]
const tabs = ref<HTMLButtonElement[]>([])

const handleKeydown = (event: KeyboardEvent, index: number): void => {
  const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End']
  if (!keys.includes(event.key)) return
  event.preventDefault()
  const nextIndex = event.key === 'Home'
    ? 0
    : event.key === 'End'
      ? modes.length - 1
      : (index + (event.key === 'ArrowRight' ? 1 : -1) + modes.length) % modes.length
  const mode = modes[nextIndex]
  if (!mode) return
  view.setViewMode(mode.value)
  void nextTick(() => tabs.value[nextIndex]?.focus())
}
</script>

<template>
  <div class="switch" role="tablist" aria-label="界面视角">
    <button
      v-for="(mode, index) in modes"
      ref="tabs"
      :key="mode.value"
      type="button"
      role="tab"
      :aria-selected="view.viewMode === mode.value"
      :tabindex="view.viewMode === mode.value ? 0 : -1"
      @click="view.setViewMode(mode.value)"
      @keydown="handleKeydown($event, index)"
    >
      {{ mode.label }}
    </button>
  </div>
</template>

<style scoped>
.switch { display: inline-flex; padding: var(--space-1); background: var(--color-surface-subtle); border: 1px solid var(--color-line); border-radius: var(--radius-pill); }
button { min-height: var(--control-height-sm); padding-inline: var(--space-3); color: var(--color-muted); background: transparent; border: 0; border-radius: var(--radius-pill); font-size: var(--text-sm); font-weight: 700; }
button[aria-selected="true"] { color: var(--color-primary-ink); background: var(--color-surface); box-shadow: var(--shadow-sm); }
</style>
