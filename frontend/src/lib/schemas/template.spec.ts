import { describe, expect, it } from 'vitest'

import {
  BLOCK_PRESET_2_2_2,
  blockCopySchema,
  blockCopySequence,
  cycleApplySchema,
  dateListSchema,
  isMonday,
  isValidIsoDate,
  parseDateList,
} from './template'

/**
 * Logika dat dialogów bloku i cyklu (karta B07 §Tests, FE).
 *
 * `blockCopySequence` musi dawać DOKŁADNIE to samo, co `block_copy_sequence`
 * w backendzie — dialog pokazuje podgląd, więc rozjazd tych dwóch funkcji
 * znaczyłby, że podgląd kłamie o skutkach kliknięcia.
 */
describe('blockCopySequence', () => {
  it('powtarza każdy dzień pod rząd — preset 2+2+2 daje d1,d1,d2,d2,d3,d3', () => {
    const pairs = blockCopySequence('2026-08-17', 3, 2, '2026-09-07')

    expect(pairs.map((pair) => pair.source)).toEqual([
      '2026-08-17',
      '2026-08-17',
      '2026-08-18',
      '2026-08-18',
      '2026-08-19',
      '2026-08-19',
    ])
    expect(pairs.map((pair) => pair.target)).toEqual([
      '2026-09-07',
      '2026-09-08',
      '2026-09-09',
      '2026-09-10',
      '2026-09-11',
      '2026-09-12',
    ])
  })

  it('preset 2+2+2 to trzy dni po dwa razy', () => {
    expect(BLOCK_PRESET_2_2_2).toEqual({ sourceDays: 3, repeatEach: 2 })
    expect(blockCopySequence('2026-08-17', 3, 2, '2026-09-07')).toHaveLength(6)
  })

  it('bez powtórzeń jest zwykłym przesunięciem bloku', () => {
    const pairs = blockCopySequence('2026-08-17', 3, 1, '2026-09-07')

    expect(pairs.map((pair) => pair.target)).toEqual(['2026-09-07', '2026-09-08', '2026-09-09'])
  })

  it('daty docelowe są kolejne i bez powtórzeń', () => {
    const targets = blockCopySequence('2026-08-17', 4, 3, '2026-09-07').map((pair) => pair.target)

    expect(new Set(targets).size).toBe(12)
    expect([...targets].sort()).toEqual(targets)
  })

  it('przechodzi przez granicę miesiąca', () => {
    const pairs = blockCopySequence('2026-08-30', 2, 2, '2026-08-31')

    expect(pairs.map((pair) => pair.source)).toEqual([
      '2026-08-30',
      '2026-08-30',
      '2026-08-31',
      '2026-08-31',
    ])
    expect(pairs.map((pair) => pair.target)).toEqual([
      '2026-08-31',
      '2026-09-01',
      '2026-09-02',
      '2026-09-03',
    ])
  })

  it('zwraca pustą sekwencję dla bezsensownych parametrów', () => {
    expect(blockCopySequence('2026-08-17', 0, 2, '2026-09-07')).toEqual([])
    expect(blockCopySequence('2026-08-17', 3, 0, '2026-09-07')).toEqual([])
  })
})

describe('blockCopySchema', () => {
  it('odrzuca blok przekraczający sufit dni docelowych', () => {
    const result = blockCopySchema.safeParse({
      sourceFrom: '2026-08-17',
      sourceDays: 30,
      repeatEach: 7,
      targetStart: '2026-09-07',
    })

    expect(result.success).toBe(false)
  })

  it('przyjmuje preset 2+2+2', () => {
    const result = blockCopySchema.safeParse({
      sourceFrom: '2026-08-17',
      sourceDays: 3,
      repeatEach: 2,
      targetStart: '2026-09-07',
    })

    expect(result.success).toBe(true)
  })
})

describe('cycleApplySchema', () => {
  it('wymaga poniedziałku w dacie „od”', () => {
    const result = cycleApplySchema.safeParse({
      dateFrom: '2026-08-18',
      dateTo: '2026-08-25',
    })

    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues[0]?.path).toEqual(['dateFrom'])
    }
  })

  it('przyjmuje poniedziałek', () => {
    expect(
      cycleApplySchema.safeParse({ dateFrom: '2026-08-17', dateTo: '2026-08-30' }).success,
    ).toBe(true)
  })

  it('odrzuca odwrócony zakres', () => {
    const result = cycleApplySchema.safeParse({ dateFrom: '2026-08-24', dateTo: '2026-08-17' })

    expect(result.success).toBe(false)
  })
})

describe('isMonday', () => {
  it('rozpoznaje poniedziałek i odrzuca resztę tygodnia', () => {
    expect(isMonday('2026-08-17')).toBe(true)
    expect(isMonday('2026-08-18')).toBe(false)
    // Niedziela należy do TEGO tygodnia (PL), więc nie jest jego początkiem.
    expect(isMonday('2026-08-23')).toBe(false)
  })
})

describe('isValidIsoDate', () => {
  it('odrzuca daty, które pasują do wzorca, ale nie istnieją', () => {
    expect(isValidIsoDate('2026-08-17')).toBe(true)
    expect(isValidIsoDate('2026-02-30')).toBe(false)
    expect(isValidIsoDate('17.08.2026')).toBe(false)
    expect(isValidIsoDate('')).toBe(false)
  })
})

describe('parseDateList', () => {
  it('czyta daty z wierszy, przecinków i średników, bez duplikatów', () => {
    expect(parseDateList('2026-08-17\n2026-08-18, 2026-08-17;\n\n 2026-08-19 ')).toEqual([
      '2026-08-17',
      '2026-08-18',
      '2026-08-19',
    ])
  })

  it('dateListSchema odrzuca puste wejście i złe formaty', () => {
    expect(dateListSchema.safeParse('   ').success).toBe(false)
    expect(dateListSchema.safeParse('17.08.2026').success).toBe(false)
    expect(dateListSchema.safeParse('2026-08-17\n2026-08-18').success).toBe(true)
  })
})
