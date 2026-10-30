import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const css = readFileSync(resolve(process.cwd(), 'src/assets/tailwind.css'), 'utf8')

function luminance(token: string): number {
  const hex = css.match(new RegExp(`--color-${token}:\\s*#([a-f0-9]{6});`, 'i'))?.[1]
  if (!hex) throw new Error(`Brak nieprzezroczystego tokenu koloru ${token}`)
  const channels = [0, 2, 4].map((start) => {
    const value = Number.parseInt(hex.slice(start, start + 2), 16) / 255
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  })
  return channels[0]! * 0.2126 + channels[1]! * 0.7152 + channels[2]! * 0.0722
}

function contrast(first: string, second: string): number {
  const a = luminance(first)
  const b = luminance(second)
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
}

describe('Kontrast rzeczywistych tokenów Paśnika (WCAG)', () => {
  it.each(['background', 'card', 'header', 'muted'])(
    'tekst i komunikaty na powierzchni %s mają ≥4,5:1',
    (surface) => {
      for (const text of ['foreground', 'muted-foreground', 'primary', 'warning', 'destructive']) {
        expect(contrast(text, surface), `${text} / ${surface}`).toBeGreaterThanOrEqual(4.5)
      }
    },
  )

  it.each([
    'primary',
    'primary-hover',
    'secondary',
    'secondary-hover',
    'destructive',
    'destructive-hover',
  ])('etykieta akcji %s ma ≥4,5:1', (surface) => {
    expect(contrast('primary-foreground', surface)).toBeGreaterThanOrEqual(4.5)
  })

  it.each(['background', 'card'])('granice pól i fokus na %s mają ≥3:1', (surface) => {
    expect(contrast('input', surface)).toBeGreaterThanOrEqual(3)
    expect(contrast('ring', surface)).toBeGreaterThanOrEqual(3)
  })
})
