import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const nginx = readFileSync(resolve(process.cwd(), 'nginx.conf'), 'utf8')

describe('Nginx production security contract', () => {
  it('keeps SSE unbuffered with an extended read timeout', () => {
    expect(nginx).toMatch(/location = \/chat\/stream[\s\S]*proxy_buffering off;/)
    expect(nginx).toMatch(/location = \/chat\/stream[\s\S]*proxy_read_timeout 300s;/)
  })

  it('blocks admin and metrics prefixes before SPA fallback', () => {
    expect(nginx).toContain('location ^~ /admin')
    expect(nginx).toContain('location = /metrics')
    expect(nginx).toContain('location ^~ /metrics/')
  })

  it('only proxies the exact legacy page and its static assets', () => {
    expect(nginx).toContain('location = /legacy/')
    expect(nginx).toContain('location ^~ /legacy-static/')
    expect(nginx).not.toContain('location /legacy/')
  })
})
