import { describe, expect, it } from 'vitest'

import { addDays, startOfWeek, weekDayLabel } from './dates'

/**
 * Daty planu są kalendarzowe, więc arytmetyka nie może zależeć od strefy
 * czasowej przeglądarki — inaczej nawigacja „poprzedni dzień" gubiłaby dobę.
 */
describe('addDays', () => {
  it('przesuwa datę w przód i w tył', () => {
    expect(addDays('2026-08-17', 1)).toBe('2026-08-18')
    expect(addDays('2026-08-17', -1)).toBe('2026-08-16')
  })

  it('przechodzi przez granicę miesiąca i roku', () => {
    expect(addDays('2026-08-31', 1)).toBe('2026-09-01')
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01')
    expect(addDays('2027-01-01', -1)).toBe('2026-12-31')
  })

  it('zna rok przestępny', () => {
    expect(addDays('2028-02-28', 1)).toBe('2028-02-29')
  })
})

describe('startOfWeek', () => {
  it('tydzień zaczyna się w poniedziałek', () => {
    // 2026-08-17 to poniedziałek.
    expect(startOfWeek('2026-08-17')).toBe('2026-08-17')
    expect(startOfWeek('2026-08-19')).toBe('2026-08-17')
    expect(startOfWeek('2026-08-23')).toBe('2026-08-17')
  })

  it('niedziela należy do tygodnia, który zaczął się sześć dni wcześniej', () => {
    expect(startOfWeek('2026-08-16')).toBe('2026-08-10')
  })
})

describe('weekDayLabel', () => {
  it('daje polskie skróty dni', () => {
    expect(weekDayLabel('2026-08-17')).toBe('pon')
    expect(weekDayLabel('2026-08-22')).toBe('sob')
    expect(weekDayLabel('2026-08-23')).toBe('nd')
  })
})
