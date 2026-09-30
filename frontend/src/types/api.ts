// /auth/login
export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
}

// /auth/session
export interface AuthSessionRequest {
  access_token: string
}

export interface AuthSessionResponse {
  authenticated: boolean
  username: string | null
}

// /chat, /chat/stream
export interface ChatRequest {
  message: string
  session_id: string
  /** 旧前端兼容字段；Vue 请求统一使用 Authorization 请求头。 */
  access_token?: string | null
}

export type ToolOutcome =
  | 'success'
  | 'error'
  | 'clarification_needed'
  | (string & Record<never, never>)

export interface ToolCallRecord {
  name: string
  arguments: Record<string, unknown>
  outcome: ToolOutcome
  result_message?: string | null
}

export interface ReferenceResolution {
  type: string
  value: string
  source: string
}

export type ConfirmationAction =
  | 'cancel_order'
  | 'refund_order'
  | 'update_cart'
  | 'update_cart_items'
  | 'remove_from_cart'
  | 'clear_cart'
  | 'create_order'
  | 'pay_order'

export interface Confirmation {
  token: string
  action: ConfirmationAction
  description: string
  arguments: Record<string, unknown>
}

export interface ChatResponse {
  answer: string
  tool_calls: ToolCallRecord[]
  confirmation: Confirmation | null
  data: unknown
  reference: ReferenceResolution | null
}

// /conversation/clear
export interface ClearConversationRequest {
  session_id: string
  /** 旧前端兼容字段；Vue 请求统一使用 Authorization 请求头。 */
  access_token?: string | null
}

export interface ClearConversationResponse {
  status: string
  cleared: boolean
}

// /confirm
export interface ConfirmRequest {
  session_id: string
  confirmation_token: string
  approved: boolean
  /** 旧前端兼容字段；Vue 请求统一使用 Authorization 请求头。 */
  access_token?: string | null
}

export type ConfirmStatus = 'executed' | 'cancelled'

export interface ConfirmResponse {
  status: ConfirmStatus
  message: string
  data: unknown
}

// /health
export interface HealthResponse {
  status: string
  model_configured: boolean
  agent_mode: string
  serving_mode: string
  llm_provider?: string | null
  llm_model?: string | null
  embedding_mode: string
  fallback_reason?: string | null
  backend_base_url: string
  checks?: Record<string, string>
}

// /admin/config
export interface RuntimeConfigResponse {
  force_demo: boolean
  disabled_tools: string[]
  max_tool_rounds: number | null
}

// /admin/knowledge/reload
export interface ReloadKnowledgeResponse {
  ok: boolean
  rule_count: number
  product_count: number
}
