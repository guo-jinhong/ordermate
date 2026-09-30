import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { streamChat } from '../api/chat'
import type { ChatResponse } from '../types/api'
import type { StreamEvent } from '../types/stream'
import { useChatStream } from './useChatStream'

vi.mock('../api/chat', () => ({ streamChat: vi.fn() }))

const streamChatMock = vi.mocked(streamChat)

const result: ChatResponse = {
  answer: '这是回答',
  tool_calls: [],
  confirmation: null,
  data: null,
  reference: null,
}

function sseResponse(...chunks: string[]): Response {
  const encoder = new TextEncoder()
  return new Response(
    new ReadableStream({
      start(controller) {
        chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)))
        controller.close()
      },
    }),
    { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
  )
}

function frame(type: StreamEvent['type'], data: unknown): string {
  return `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`
}

function mountStream(onEvent = vi.fn<(runId: string, event: StreamEvent) => void>()) {
  const holder: { stream?: ReturnType<typeof useChatStream> } = {}
  const wrapper = mount(
    defineComponent({
      setup() {
        holder.stream = useChatStream(onEvent)
        return () => h('div')
      },
    }),
  )
  if (!holder.stream) throw new Error('流式组合函数未初始化。')
  return { stream: holder.stream, onEvent, wrapper }
}

describe('useChatStream', () => {
  beforeEach(() => vi.clearAllMocks())

  it('consumes a normal stream and does not retain repeated progress events', async () => {
    streamChatMock.mockResolvedValue(
      sseResponse(
        frame('started', { message: '开始' }) + frame('progress', { message: '处理中' }),
        frame('tool', { name: 'search_products', outcome: 'success', arguments: {} }),
        frame('result', result),
      ),
    )
    const { stream, onEvent, wrapper } = mountStream()

    await expect(
      stream.send({ message: '推荐商品', sessionId: 'session-1', accessToken: null, runId: 'run-1' }),
    ).resolves.toEqual(result)

    expect(stream.phase.value).toBe('done')
    expect(stream.events.value.map(({ type }) => type)).toEqual(['started', 'tool', 'result'])
    expect(onEvent).toHaveBeenCalledTimes(4)
    wrapper.unmount()
  })

  it('throws an SSE error event', async () => {
    streamChatMock.mockResolvedValue(sseResponse(frame('error', { detail: 'Agent 失败' })))
    const { stream, wrapper } = mountStream()

    await expect(
      stream.send({ message: '失败', sessionId: 'session-1', accessToken: null, runId: 'run-1' }),
    ).rejects.toThrow('Agent 失败')
    expect(stream.phase.value).toBe('error')
    wrapper.unmount()
  })

  it('rejects a stream that ends without a result event', async () => {
    streamChatMock.mockResolvedValue(sseResponse(frame('started', { message: '开始' })))
    const { stream, wrapper } = mountStream()

    await expect(
      stream.send({ message: '无结果', sessionId: 'session-1', accessToken: null, runId: 'run-1' }),
    ).rejects.toThrow('流式响应意外结束。')
    wrapper.unmount()
  })

  it('normalizes a non-2xx response before reading the stream', async () => {
    streamChatMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: [{ loc: ['body', 'message'], msg: '字段不能为空' }] }), {
        status: 422,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const { stream, wrapper } = mountStream()

    const request = stream.send({
      message: '',
      sessionId: 'session-1',
      accessToken: null,
      runId: 'run-1',
    })
    await expect(request).rejects.toMatchObject({
      status: 422,
      message: 'message：字段不能为空',
    })
    wrapper.unmount()
  })

  it('preserves a plain-text non-2xx error message', async () => {
    streamChatMock.mockResolvedValue(
      new Response('上游服务暂不可用', {
        status: 503,
        headers: { 'Content-Type': 'text/plain' },
      }),
    )
    const { stream, wrapper } = mountStream()

    await expect(
      stream.send({ message: '重试', sessionId: 'session-1', accessToken: null, runId: 'run-1' }),
    ).rejects.toThrow('上游服务暂不可用')
    wrapper.unmount()
  })

  it('treats cancellation as a non-error terminal state', async () => {
    streamChatMock.mockImplementation(
      (_request, _token, options) =>
        new Promise((_resolve, reject) => {
          options?.signal?.addEventListener('abort', () =>
            reject(new DOMException('aborted', 'AbortError')),
          )
        }),
    )
    const { stream, onEvent, wrapper } = mountStream()
    const request = stream.send({
      message: '取消',
      sessionId: 'session-1',
      accessToken: null,
      runId: 'run-1',
    })

    stream.cancel('user')

    await expect(request).resolves.toBeNull()
    expect(stream.phase.value).toBe('cancelled')
    expect(stream.cancelReason.value).toBe('user')
    expect(onEvent).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('retains tool_error and the following tool event', async () => {
    streamChatMock.mockResolvedValue(
      sseResponse(
        frame('tool_error', { name: 'get_cart', error: '后端失败' }) +
          frame('tool', { name: 'get_cart', outcome: 'error', arguments: {} }) +
          frame('result', result),
      ),
    )
    const { stream, wrapper } = mountStream()

    await stream.send({ message: '购物车', sessionId: 'session-1', accessToken: null, runId: 'run-1' })

    expect(stream.events.value.map(({ type }) => type)).toEqual(['tool_error', 'tool', 'result'])
    wrapper.unmount()
  })
})
