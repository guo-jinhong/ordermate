/// <reference types="node" />

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const readLocalFile = (name: string) =>
  readFileSync(fileURLToPath(new URL(name, import.meta.url)), 'utf8')

const tokens = readLocalFile('./tokens.css')
const base = readLocalFile('./base.css')
const app = readLocalFile('../App.vue')

describe('global style foundation', () => {
  it('defines the required token families', () => {
    const requiredTokens = [
      '--color-canvas',
      '--color-surface',
      '--color-ink',
      '--color-primary',
      '--color-ai',
      '--color-success',
      '--color-warning',
      '--color-danger',
      '--color-navy',
      '--font-sans',
      '--font-display',
      '--font-mono',
      '--text-xs',
      '--text-2xl',
      '--leading-tight',
      '--leading-relaxed',
      '--radius-sm',
      '--radius-pill',
      '--shadow-sm',
      '--shadow-focus',
      '--duration-fast',
      '--ease-standard',
      '--control-height-sm',
      '--control-height-md',
      ...Array.from({ length: 10 }, (_, index) => `--space-${index + 1}`),
    ]

    requiredTokens.forEach((token) => {
      expect(tokens).toContain(`${token}:`)
    })
  })

  it('keeps custom property declarations in tokens.css only', () => {
    expect(base).not.toMatch(/--[a-z0-9-]+\s*:/i)
    expect(app).not.toMatch(/--[a-z0-9-]+\s*:/i)
  })

  it('covers keyboard and operating-system accessibility preferences', () => {
    expect(base).toContain(':focus-visible')
    expect(base).toContain('(pointer: coarse)')
    expect(base).toContain('(prefers-reduced-motion: reduce)')
    expect(base).toContain('(forced-colors: active)')
  })
})
