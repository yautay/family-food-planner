import { describe, expect, it } from 'vitest'
import { datePreviewWindow, usedCycleTemplateIds, CYCLE_PREVIEW_PAGE_DAYS } from './cyclePreview'

describe('ograniczony podgląd pełnego zakresu cyklu', () => {
  it('materializuje wyłącznie 28 dni także dla zakresu obejmującego tysiące lat', () => {
    const first = datePreviewWindow('0001-01-01', '9999-12-31', 0)!
    expect(first.totalDays).toBe(3652059)
    expect(first.dates).toHaveLength(CYCLE_PREVIEW_PAGE_DAYS)
    expect(first.from).toBe('0001-01-01')
    expect(first.to).toBe('0001-01-28')
    const last = datePreviewWindow('0001-01-01', '9999-12-31', first.totalPages - 1)!
    expect(last.dates.length).toBeLessThanOrEqual(CYCLE_PREVIEW_PAGE_DAYS)
    expect(last.to).toBe('9999-12-31')
    expect(last.totalDays).toBe(first.totalDays)
  })
  it('następne okno przechodzi przez rok i nie generuje dat poza końcem zakresu', () => {
    const second = datePreviewWindow('2031-12-01', '2032-01-02', 1)!
    expect(second.dates).toEqual([
      '2031-12-29',
      '2031-12-30',
      '2031-12-31',
      '2032-01-01',
      '2032-01-02',
    ])
    expect(second.totalDays).toBe(33)
    expect(datePreviewWindow('2031-12-01', '2032-01-02', 999)?.page).toBe(1)
    expect(datePreviewWindow('2031-12-01', '2031-11-01', 0)).toBeNull()
    expect(datePreviewWindow('', '2032-01-02', 0)).toBeNull()
  })
  it('wyznacza tylko użyte szablony, z ujemną rotacją, niepełnym tygodniem i powtórzeniami', () => {
    expect(usedCycleTemplateIds([1, 2, 3], '2032-01-19', '2032-01-05', '2032-01-06')).toEqual([2])
    expect(usedCycleTemplateIds([1, 2, 3], '2032-01-19', '2032-01-05', '2032-01-18')).toEqual([
      2, 3,
    ])
    expect(usedCycleTemplateIds([1, 1, 2], null, '2032-01-05', '2032-01-18')).toEqual([1])
    expect(usedCycleTemplateIds([1, 2, 3], null, '0001-01-01', '9999-12-31')).toEqual([1, 2, 3])
  })
})
