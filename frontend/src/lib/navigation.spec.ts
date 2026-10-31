import { describe, expect, it } from 'vitest'
import type { LocationQuery } from 'vue-router'
import {
  NAV_ITEMS,
  navigationRange,
  planNavigationContext,
  planNavigationTarget,
  validNavigationDate,
  visibleNavItems,
} from './navigation'

const TODAY = '2031-03-05'
function route(
  name: string,
  params: Record<string, string> = {},
  query: Record<string, string | string[]> = {},
) {
  return { name, params, query }
}
describe('kontrakt kalendarza nawigacji UX02', () => {
  it('ma dokładnie cztery sekcje i filtruje rolę bez zmiany kolejności', () => {
    expect(NAV_ITEMS.filter((item) => item.primary).map((item) => item.label)).toEqual([
      'Plan',
      'Przepisy',
      'Zakupy',
      'Spiżarnia',
    ])
    expect(visibleNavItems(false).some((item) => item.adminOnly)).toBe(false)
    expect(visibleNavItems(true).filter((item) => item.adminOnly)).toHaveLength(4)
  })
  it.each(['śmieci', '2031-02-29', '2031-13-01', '', ['2031-03-05']])(
    'odrzuca niepoprawną lub niejednoznaczną datę %s',
    (value) => {
      expect(validNavigationDate(value)).toBeNull()
    },
  )
  it('waliduje kalendarz, kolejność i limit 92 dni zakresu', () => {
    expect(navigationRange({ from: '2032-02-29', to: '2032-02-29' })).toEqual({
      from: '2032-02-29',
      to: '2032-02-29',
    })
    const invalidQueries: LocationQuery[] = [
      { from: '2031-03-05' },
      { from: '2031-03-06', to: '2031-03-05' },
      { from: '2031-01-01', to: '2031-04-03' },
      { from: ['2031-03-05'], to: '2031-03-05' },
    ]
    for (const query of invalidQueries) expect(navigationRange(query)).toBeNull()
    expect(navigationRange({ from: '2031-01-01', to: '2031-04-02' })).not.toBeNull()
  })
  it('zachowuje konkretny dzień między dniem, tygodniem i podsumowaniem', () => {
    const context = planNavigationContext(route('plan-dnia', { date: TODAY }), TODAY)
    expect(context).toEqual({ selectedDate: TODAY, from: '2031-03-03', to: '2031-03-09' })
    expect(planNavigationTarget('tydzien', context)).toEqual({
      name: 'tydzien',
      params: { weekStart: '2031-03-03' },
      query: context,
    })
    expect(
      planNavigationContext(route('tydzien', { weekStart: '2031-03-03' }, { ...context }), TODAY),
    ).toEqual(context)
    expect(planNavigationTarget('zakupy', context)).toEqual({ name: 'zakupy', query: context })
    expect(planNavigationTarget('przepisy', context)).toEqual({ name: 'przepisy', query: context })
    expect(planNavigationContext(route('przepisy', {}, { ...context }), TODAY)).toEqual(context)
  })
  it('stary link tygodnia wybiera dziś tylko w bieżącym tygodniu, inaczej poniedziałek', () => {
    expect(
      planNavigationContext(route('tydzien', { weekStart: '2031-03-05' }), TODAY).selectedDate,
    ).toBe(TODAY)
    expect(
      planNavigationContext(
        route('tydzien', { weekStart: '2031-03-10' }, { selectedDate: TODAY }),
        TODAY,
      ).selectedDate,
    ).toBe('2031-03-10')
    expect(() =>
      planNavigationContext(route('tydzien', { weekStart: 'śmieci' }), TODAY),
    ).not.toThrow()
  })
  it('podsumowanie korzysta z jawnego zakresu i ogranicza wybrany dzień do zakresu', () => {
    const query = { from: '2031-04-01', to: '2031-04-30', selectedDate: TODAY }
    expect(planNavigationContext(route('statystyki', {}, query), TODAY)).toEqual({
      ...query,
      selectedDate: query.from,
    })
  })
})
