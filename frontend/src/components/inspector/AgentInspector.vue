<script setup lang="ts">
import { computed } from 'vue'

import { streamEventLabel, toolBusinessLabel, toolStatusCopy } from '../../lib/labels'
import { useInspectorStore } from '../../stores/inspector'
import type { InspectorEvent } from '../../stores/inspector'
import { useSessionStore } from '../../stores/session'
import type { SseClarification, SseTool, SseToolError } from '../../types/stream'

defineProps<{ modelLabel: string }>()
const emit = defineEmits<{ close: [] }>()

const inspector = useInspectorStore()
const session = useSessionStore()

const phaseLabel = computed(() => ({
  connecting: '正在连接',
  streaming: '流式处理中',
  done: '已完成',
  error: '运行失败',
  cancelled: '已停止',
})[inspector.phase])

const elapsed = (event: InspectorEvent): string => {
  if (inspector.startedAt == null) return '—'
  return `+${Math.max(0, event.at - inspector.startedAt)} ms`
}

const eventTitle = (event: InspectorEvent): string => {
  if (event.type === 'tool' || event.type === 'tool_error') {
    return toolBusinessLabel((event.data as SseTool | SseToolError).name)
  }
  if (event.type === 'clarification') {
    return toolBusinessLabel((event.data as SseClarification).tool)
  }
  return streamEventLabel(event.type)
}

const eventData = (event: InspectorEvent): unknown => {
  if (event.type === 'tool') {
    const data = event.data as SseTool
    return {
      status: toolStatusCopy(data.name, data.outcome).status,
      arguments: data.arguments,
    }
  }
  if (event.type === 'tool_error') return { error: (event.data as SseToolError).error }
  if (event.type === 'clarification') {
    return { message: (event.data as SseClarification).message }
  }
  return event.data
}

const formatData = (value: unknown): string => JSON.stringify(value, null, 2)
</script>

<template>
  <aside class="inspector" aria-label="Agent 调试视图">
    <header>
      <div><p>Developer view</p><h2>Agent Inspector</h2></div>
      <button type="button" aria-label="关闭调试视图" @click="emit('close')">×</button>
    </header>

    <section class="run" aria-labelledby="run-title">
      <h3 id="run-title">当前问题</h3>
      <p>{{ inspector.query || '尚未发起问题' }}</p>
    </section>

    <dl class="metrics">
      <div><dt>SSE 状态</dt><dd>{{ phaseLabel }}</dd></div>
      <div><dt>浏览器观测时长</dt><dd>{{ inspector.durationMs == null ? '—' : `${inspector.durationMs} ms` }}</dd></div>
      <div><dt>业务步骤</dt><dd>{{ inspector.toolCount }}</dd></div>
    </dl>

    <ol v-if="inspector.events.length" class="timeline" aria-label="完整事件时间线">
      <li v-for="event in inspector.events" :key="event.id">
        <div class="event-heading">
          <strong>{{ eventTitle(event) }}</strong>
          <span>{{ streamEventLabel(event.type) }} · {{ elapsed(event) }}</span>
        </div>
        <pre>{{ formatData(eventData(event)) }}</pre>
      </li>
    </ol>
    <p v-else class="empty">发送消息后，这里会展示经过脱敏的完整事件时间线。</p>

    <footer>
      <span>模型：{{ modelLabel }}</span>
      <span>会话：{{ session.sessionId }}</span>
    </footer>
  </aside>
</template>

<style scoped>
.inspector { display: grid; grid-template-rows: auto auto auto minmax(0, 1fr) auto; gap: var(--space-4); min-height: 0; padding: var(--space-5); overflow: hidden; color: var(--color-on-dark); background: var(--color-navy); border-left: 1px solid var(--color-navy-soft); }
header, .event-heading { display: flex; justify-content: space-between; gap: var(--space-3); } header p { color: var(--color-ai); font-size: var(--text-xs); font-weight: 800; text-transform: uppercase; } h2 { font-size: var(--text-xl); } header button { color: var(--color-on-dark); background: transparent; border: 0; font-size: var(--text-xl); }
.run { display: grid; gap: var(--space-1); padding: var(--space-3); background: var(--color-navy-raised); border-radius: var(--radius-md); }.run h3 { color: var(--color-on-dark-muted); font-size: var(--text-xs); }.run p { line-height: var(--leading-relaxed); }
.metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-2); margin: 0; }.metrics div { padding: var(--space-3); background: var(--color-navy-raised); border-radius: var(--radius-md); }.metrics dt { color: var(--color-on-dark-muted); font-size: var(--text-xs); }.metrics dd { margin: var(--space-1) 0 0; font-weight: 800; overflow-wrap: anywhere; }
.timeline { display: grid; align-content: start; gap: var(--space-3); margin: 0; padding: 0; overflow-y: auto; list-style: none; }.timeline li { padding: var(--space-3); background: var(--color-navy-raised); border-radius: var(--radius-md); }.event-heading { align-items: baseline; }.event-heading strong { color: var(--color-ai-soft); }.event-heading span { color: var(--color-on-dark-muted); font-size: var(--text-xs); white-space: nowrap; }.timeline pre { max-height: 12rem; margin: var(--space-2) 0 0; overflow: auto; color: var(--color-on-dark-muted); font-family: var(--font-mono); font-size: var(--text-xs); white-space: pre-wrap; word-break: break-word; }
.empty, footer { color: var(--color-on-dark-muted); }.empty { align-self: start; } footer { display: grid; gap: var(--space-1); padding-top: var(--space-3); border-top: 1px solid var(--color-navy-soft); font-family: var(--font-mono); font-size: var(--text-xs); overflow-wrap: anywhere; }
@media (max-width: 460px) { .metrics { grid-template-columns: 1fr; } }
</style>
