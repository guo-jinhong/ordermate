import { defineStore } from 'pinia'

import { redactSensitive } from '../lib/redact'
import type { RunPhase } from '../types/chat'
import type { StreamEvent } from '../types/stream'

export interface InspectorEvent {
  id: string
  runId: string
  type: StreamEvent['type']
  at: number
  data: unknown
}

export const useInspectorStore = defineStore('inspector', {
  state: () => ({
    activeRunId: null as string | null,
    phase: 'done' as RunPhase,
    startedAt: null as number | null,
    completedAt: null as number | null,
    query: '',
    events: [] as InspectorEvent[],
  }),

  getters: {
    durationMs: (state): number | null => {
      if (state.startedAt == null || state.completedAt == null) return null
      return Math.max(0, state.completedAt - state.startedAt)
    },
    toolCount: (state): number => state.events.filter(
      (event) => event.type === 'tool' || event.type === 'tool_error',
    ).length,
  },

  actions: {
    startRun(runId: string, query: string, at = Date.now()): void {
      this.activeRunId = runId
      this.phase = 'connecting'
      this.startedAt = at
      this.completedAt = null
      this.query = query
      this.events = []
    },

    recordEvent(runId: string, event: StreamEvent, at = Date.now()): void {
      if (runId !== this.activeRunId) return
      if (event.type === 'started' || event.type === 'progress') this.phase = 'streaming'
      if (event.type === 'result') this.finishRun(runId, 'done', at)
      if (event.type === 'error') this.finishRun(runId, 'error', at)
      this.events.push({
        id: crypto.randomUUID(),
        runId,
        type: event.type,
        at,
        data: redactSensitive(event.data),
      })
    },

    finishRun(runId: string, phase: RunPhase, at = Date.now()): void {
      if (runId !== this.activeRunId) return
      this.phase = phase
      this.completedAt = at
    },

    reset(): void {
      this.activeRunId = null
      this.phase = 'done'
      this.startedAt = null
      this.completedAt = null
      this.query = ''
      this.events = []
    },
  },
})
