import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { useShoppingDraftStore } from './shoppingDraft'

describe('shoppingDraft — tylko szkic UI', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })
  it('zaczyna bez zgody na spiżarnię i resetuje zgodę bez utraty zakresu', () => {
    const draft = useShoppingDraftStore()
    expect(draft.usePantry).toBe(false)
    draft.dateFrom = '2035-01-01'
    draft.dateTo = '2035-01-07'
    draft.usePantry = true
    draft.openGeneration(10)
    draft.toggleRound('cfg-1')
    draft.reset()
    expect(draft.usePantry).toBe(false)
    expect(draft.generationId).toBeNull()
    expect(draft.collapsedRounds).toEqual([])
    expect([draft.dateFrom, draft.dateTo]).toEqual(['2035-01-01', '2035-01-07'])
  })
  it('przejmuje poprawny zakres włącznie do 92 dni i zamyka podgląd innego zakresu', () => {
    const draft = useShoppingDraftStore()
    draft.openGeneration(10)
    draft.usePantry = true
    draft.applyNavigationRange({ from: '2035-01-01', to: '2035-04-02' })
    expect(draft.rangeValid).toBe(true)
    expect([draft.dateFrom, draft.dateTo]).toEqual(['2035-01-01', '2035-04-02'])
    expect(draft.generationId).toBeNull()
    expect(draft.usePantry).toBe(false)
  })
  it('odrzuca nieistniejące daty, odwrócony i nadmierny zakres nawigacji', () => {
    const draft = useShoppingDraftStore()
    draft.dateFrom = '2035-01-01'
    draft.dateTo = '2035-01-07'
    draft.openGeneration(10)
    draft.usePantry = true
    for (const range of [
      { from: '2035-02-30', to: '2035-03-07' },
      { from: '2035-03-07', to: '2035-03-01' },
      { from: '2035-01-01', to: '2035-04-03' },
    ])
      draft.applyNavigationRange(range)
    expect([draft.dateFrom, draft.dateTo]).toEqual(['2035-01-01', '2035-01-07'])
    expect(draft.generationId).toBe(10)
    expect(draft.usePantry).toBe(true)
  })
  it.each(['', '2035-02-30', '2035-2-01'])(
    'formularz nie akceptuje niepoprawnej daty %s',
    (date) => {
      const draft = useShoppingDraftStore()
      draft.dateFrom = date
      draft.dateTo = '2035-12-31'
      expect(draft.rangeValid).toBe(false)
    },
  )
})
