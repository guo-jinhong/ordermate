import type {
  ChatResponse,
  ConfirmationAction,
  ReferenceResolution,
  ToolOutcome,
} from './api'

export interface SseStarted {
  message: string
}

export interface SseProgress {
  message: string
}

export interface SseLlmTrace {
  calls: unknown[]
}

export interface SseClarification {
  tool: string
  message: string | null
}

export interface SseToolError {
  name: string
  error: string | null
}

export interface SseTool {
  name: string
  outcome: ToolOutcome
  arguments: Record<string, unknown>
}

export interface SseConfirmationRequired {
  action: ConfirmationAction
}

export interface SseError {
  detail: string
}

export type StreamEvent =
  | { type: 'started'; data: SseStarted }
  | { type: 'progress'; data: SseProgress }
  | { type: 'llm_trace'; data: SseLlmTrace }
  | { type: 'reference'; data: ReferenceResolution }
  | { type: 'clarification'; data: SseClarification }
  | { type: 'tool_error'; data: SseToolError }
  | { type: 'tool'; data: SseTool }
  | { type: 'confirmation_required'; data: SseConfirmationRequired }
  | { type: 'result'; data: ChatResponse }
  | { type: 'error'; data: SseError }
