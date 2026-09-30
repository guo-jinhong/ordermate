import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { gzipSync } from 'node:zlib'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

const DIST = join(process.cwd(), 'dist')
const RAW_BUDGET = 220 * 1024
const GZIP_BUDGET = 75 * 1024
const PHASE_ZERO_RAW = 112_340
const PHASE_ZERO_GZIP = 40_910

function filesUnder(directory: string): string[] {
  return readdirSync(directory).flatMap((name) => {
    const path = join(directory, name)
    return statSync(path).isDirectory() ? filesUnder(path) : [path]
  })
}

function productionFiles(): string[] {
  expect(existsSync(DIST), 'dist 不存在，请先运行 npm run build').toBe(true)
  return filesUnder(DIST)
}

describe('production artifact contract', () => {
  it('keeps index.html free of external resources', () => {
    const html = readFileSync(join(DIST, 'index.html'), 'utf8')

    expect(html).not.toMatch(/(?:src|href)=["']https?:\/\//i)
    expect(html).not.toMatch(/<link[^>]+rel=["'](?:preconnect|dns-prefetch)["']/i)
  })

  it('does not package image dependencies', () => {
    const content = productionFiles()
      .filter((path) => /\.(?:html|css|js)$/i.test(path))
      .map((path) => readFileSync(path, 'utf8'))
      .join('\n')

    expect(content).not.toMatch(/(?:url\(|src=)[^\n]*\.(?:avif|gif|jpe?g|png|svg|webp)(?:[?#"')]|$)/i)
  })

  it('stays inside the frozen JavaScript and CSS budgets', () => {
    const assets = productionFiles().filter((path) => /\.(?:css|js)$/i.test(path))
    const raw = assets.reduce((total, path) => total + statSync(path).size, 0)
    const gzip = assets.reduce(
      (total, path) => total + gzipSync(readFileSync(path)).byteLength,
      0,
    )

    process.stdout.write(
      `\n产物体积：raw ${(raw / 1000).toFixed(2)} kB（较 Phase 0 +${((raw - PHASE_ZERO_RAW) / 1000).toFixed(2)} kB），` +
      `gzip ${(gzip / 1000).toFixed(2)} kB（较 Phase 0 +${((gzip - PHASE_ZERO_GZIP) / 1000).toFixed(2)} kB）\n`,
    )
    expect(raw).toBeLessThanOrEqual(RAW_BUDGET)
    expect(gzip).toBeLessThanOrEqual(GZIP_BUDGET)
  })

  it('does not embed credential configuration', () => {
    const scripts = productionFiles()
      .filter((path) => path.endsWith('.js'))
      .map((path) => readFileSync(path, 'utf8'))
      .join('\n')

    expect(scripts).not.toMatch(/VITE_(?:API_KEY|SECRET|PASSWORD)/i)
    expect(scripts).not.toMatch(/(?:api[_-]?key|secret|password)\s*[:=]\s*["'][^"']{8,}["']/i)
  })

  it('contains only expected production file types', () => {
    const unexpected = productionFiles()
      .map((path) => relative(DIST, path))
      .filter((path) => !/\.(?:css|html|js)$/i.test(path))

    expect(unexpected).toEqual([])
  })
})
