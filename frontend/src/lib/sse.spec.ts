import { describe, expect, it } from 'vitest'

import { flushSseBuffer, parseSseChunk, SseParseError } from './sse'

const startedFrame = 'event: started\ndata: {"message":"开始"}\n\n'

describe('parseSseChunk', () => {
  it('parses a single frame', () => {
    const parsed = parseSseChunk('', startedFrame)

    expect(parsed.events).toEqual([{ type: 'started', data: { message: '开始' } }])
    expect(parsed.buffer).toBe('')
  })

  it('parses a frame split at every chunk boundary', () => {
    for (let index = 1; index < startedFrame.length; index += 1) {
      const first = parseSseChunk('', startedFrame.slice(0, index))
      const second = parseSseChunk(first.buffer, startedFrame.slice(index))

      expect(second.events, `split at ${index}`).toEqual([
        { type: 'started', data: { message: '开始' } },
      ])
      expect(second.buffer).toBe('')
    }
  })

  it('parses multiple frames from one chunk', () => {
    const parsed = parseSseChunk(
      '',
      `${startedFrame}event: progress\ndata: {"message":"处理中"}\n\n`,
    )

    expect(parsed.events.map(({ type }) => type)).toEqual(['started', 'progress'])
  })

  it('flushes a final frame without a blank-line terminator', () => {
    expect(flushSseBuffer('event: error\ndata: {"detail":"失败"}')).toEqual([
      { type: 'error', data: { detail: '失败' } },
    ])
  })

  it('joins multiline data before parsing JSON', () => {
    const parsed = parseSseChunk(
      '',
      'event: started\ndata: {"message":\ndata: "开始"}\n\n',
    )

    expect(parsed.events[0]).toEqual({ type: 'started', data: { message: '开始' } })
  })

  it('throws a clear error for invalid JSON', () => {
    expect(() => parseSseChunk('', 'event: tool\ndata: {broken}\n\n')).toThrowError(
      SseParseError,
    )
    expect(() => parseSseChunk('', 'event: tool\ndata: {broken}\n\n')).toThrow(
      '收到无法解析的流式事件（tool）。',
    )
  })

  it('ignores unknown event names for forward compatibility', () => {
    const parsed = parseSseChunk('', 'event: future_event\ndata: {"value":1}\n\n')

    expect(parsed.events).toEqual([])
    expect(parsed.buffer).toBe('')
  })
})
