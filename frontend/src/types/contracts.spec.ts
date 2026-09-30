import { describe, expect, expectTypeOf, it } from 'vitest'

import type {
  ChatRequest,
  ConfirmationAction,
  HealthResponse,
  LoginResponse,
} from './api'
import type { AssistantMessage, ChatMessage, PromptAction } from './chat'
import type { ResultPayload } from './results'
import type { StreamEvent } from './stream'

function streamEventName(event: StreamEvent): string {
  switch (event.type) {
    case 'started':
    case 'progress':
    case 'llm_trace':
    case 'reference':
    case 'clarification':
    case 'tool_error':
    case 'tool':
    case 'confirmation_required':
    case 'result':
    case 'error':
      return event.type
    default: {
      const exhaustive: never = event
      return exhaustive
    }
  }
}

describe('frontend contracts', () => {
  it('mirrors required API field types', () => {
    expectTypeOf<ChatRequest['message']>().toEqualTypeOf<string>()
    expectTypeOf<LoginResponse['access_token']>().toEqualTypeOf<string>()
    expectTypeOf<HealthResponse['checks']>().toEqualTypeOf<
      Record<string, string> | undefined
    >()
  })

  it('keeps all supported confirmation actions in the contract', () => {
    const actions: ConfirmationAction[] = [
      'cancel_order',
      'refund_order',
      'update_cart',
      'update_cart_items',
      'remove_from_cart',
      'clear_cart',
      'create_order',
      'pay_order',
    ]

    expect(actions).toHaveLength(8)
  })

  it('uses discriminated unions for stream events and results', () => {
    const event: StreamEvent = {
      type: 'started',
      data: { message: '正在理解你的问题' },
    }
    const result: ResultPayload = { kind: 'raw', value: { future: true } }

    expect(streamEventName(event)).toBe('started')
    expect(result.kind).toBe('raw')
  })

  it('keeps assistant messages assignable to the chat union', () => {
    const assistant: AssistantMessage = {
      id: 'message-1',
      role: 'assistant',
      runId: 'run-1',
      at: 1,
      text: '',
      status: null,
      reference: null,
      results: { kind: 'none' },
      confirmation: null,
      confirmationPhase: 'pending',
      confirmationResult: null,
      streamPhase: 'connecting',
    }
    const message: ChatMessage = assistant

    expect(message.role).toBe('assistant')
  })

  it('keeps result actions explicit about authentication', () => {
    const action: PromptAction = {
      prompt: '加入购物车',
      label: '加入个人购物车',
      authRequired: true,
    }

    expect(action.authRequired).toBe(true)
  })
})
