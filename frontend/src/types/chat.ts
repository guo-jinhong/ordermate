import type { Confirmation, ReferenceResolution } from './api'
import type { ResultPayload } from './results'

export type MessageStatusTone = 'loading' | 'success' | 'warning' | 'error'

export interface MessageStatus {
  text: string
  tone: MessageStatusTone
}

export interface PromptAction {
  prompt: string
  /** 展示给用户的友好文案；prompt 可保留供 Agent 精确执行的内部参数。 */
  displayPrompt?: string
  label: string
  authRequired: boolean
  preserveScroll?: boolean
}

export type RunPhase = 'connecting' | 'streaming' | 'done' | 'error' | 'cancelled'

export type ConfirmationPhase =
  | 'pending'
  | 'submitting'
  | 'executed'
  | 'cancelled'
  | 'failed'
  | 'unknown'

export interface UserMessage {
  id: string
  preserveScroll?: boolean
  role: 'user'
  text: string
  at: number
}

export interface SystemNotice {
  id: string
  role: 'system'
  text: string
  at: number
}

/** 一条助手消息由可独立缺失的文本、状态、引用、结果和确认块组成。 */
export interface AssistantMessage {
  id: string
  preserveScroll?: boolean
  role: 'assistant'
  /** 与本次运行绑定，用于阻止旧流写回新会话。 */
  runId: string
  at: number
  text: string
  status: MessageStatus | null
  reference: ReferenceResolution | null
  results: ResultPayload
  confirmation: Confirmation | null
  confirmationPhase: ConfirmationPhase
  confirmationResult: { message: string; data: unknown } | null
  streamPhase: RunPhase
}

export type ChatMessage = UserMessage | AssistantMessage | SystemNotice
