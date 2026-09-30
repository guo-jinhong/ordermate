import type { StreamEvent } from '@/types/stream'

const STREAM_EVENT_TYPES = new Set<StreamEvent['type']>([
  'started',
  'progress',
  'llm_trace',
  'reference',
  'clarification',
  'tool_error',
  'tool',
  'confirmation_required',
  'result',
  'error',
])

export interface SseParseResult {
  events: StreamEvent[]
  buffer: string
}

export class SseParseError extends Error {
  readonly eventName: string

  constructor(eventName: string) {
    super(`收到无法解析的流式事件（${eventName}）。`)
    this.name = 'SseParseError'
    this.eventName = eventName
  }
}

function isStreamEventType(value: string): value is StreamEvent['type'] {
  return STREAM_EVENT_TYPES.has(value as StreamEvent['type'])
}

function parseFrame(frame: string): StreamEvent | null {
  let eventName = ''
  const dataLines: string[] = []

  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith(':')) continue
    if (line.startsWith('event:')) eventName = line.slice(6).trim()
    if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''))
  }

  if (!eventName || dataLines.length === 0 || !isStreamEventType(eventName)) return null

  try {
    const data: unknown = JSON.parse(dataLines.join('\n'))
    return { type: eventName, data } as StreamEvent
  } catch {
    throw new SseParseError(eventName)
  }
}

export function parseSseChunk(
  buffer: string,
  chunk: string,
  flush = false,
): SseParseResult {
  const frames = `${buffer}${chunk}`.split(/\r?\n\r?\n/)
  let remainder = frames.pop() ?? ''

  if (flush && remainder.trim()) {
    frames.push(remainder)
    remainder = ''
  }

  const events = frames
    .map(parseFrame)
    .filter((event): event is StreamEvent => event !== null)

  return { events, buffer: remainder }
}

export function flushSseBuffer(buffer: string): StreamEvent[] {
  return parseSseChunk(buffer, '', true).events
}
