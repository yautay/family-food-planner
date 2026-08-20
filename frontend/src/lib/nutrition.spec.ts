import { describe, expect, it } from 'vitest'

import { statusFor, statusLabel, statusToken } from './nutrition'

/**
 * Odpowiednik testów `goal_status` z silnika (D9): oba progi NALEŻĄ do
 * przedziału „prawidłowo". Ta funkcja służy wyłącznie podglądowi w ustawieniach
 * — prawdą pozostaje odpowiedź serwera.
 */
describe('statusFor', () => {
  const DEFAULT = { low: 90, high: 110 }

  it('dokładnie 90% i dokładnie 110% celu to jeszcze „prawidłowo"', () => {
    expect(statusFor(1800, 2000, DEFAULT)).toBe('ok')
    expect(statusFor(2200, 2000, DEFAULT)).toBe('ok')
  })

  it('poniżej progu to „za mało", powyżej to „za dużo"', () => {
    expect(statusFor(1799, 2000, DEFAULT)).toBe('below')
    expect(statusFor(2201, 2000, DEFAULT)).toBe('above')
  })

  it('progi z ustawień przesuwają granice', () => {
    expect(statusFor(1850, 2000, { low: 95, high: 105 })).toBe('below')
    expect(statusFor(1850, 2000, { low: 80, high: 120 })).toBe('ok')
  })

  it('brak celu daje brak statusu, nie „za mało"', () => {
    expect(statusFor(1200, null, DEFAULT)).toBeNull()
    expect(statusFor(1200, 0, DEFAULT)).toBeNull()
  })
})

describe('prezentacja statusu', () => {
  it('każdy status ma polską etykietę', () => {
    expect(statusLabel('below')).toBe('za mało')
    expect(statusLabel('ok')).toBe('prawidłowo')
    expect(statusLabel('above')).toBe('za dużo')
  })

  it('brak statusu nie udaje żadnego z trzech', () => {
    expect(statusLabel(null)).toBe('')
    expect(statusToken(null).text).toBe('text-muted-foreground')
  })

  it('kolory pochodzą wyłącznie z tokens, nigdy z wartości hex', () => {
    for (const status of ['below', 'ok', 'above'] as const) {
      expect(statusToken(status).fill).toMatch(/^fill-[a-z-]+$/)
      expect(statusToken(status).text).toMatch(/^text-[a-z-]+$/)
    }
  })
})
