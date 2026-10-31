import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { catalogFilters, catalogQuery, returnToCatalog } from './catalogNavigation'

describe('nawigacja katalogu — niezaufane query i historia', () => {
  it('przyjmuje wyłącznie poprawne, jednoznaczne filtry i usuwa powtórzone ID tagów', () => {
    expect(
      catalogFilters({
        q: ' zupa ',
        scope: 'household',
        prep_time_max: '30',
        tag: ['7', '2', '7'],
      }),
    ).toEqual({
      limit: 50,
      q: 'zupa',
      scope: 'household',
      prep_time_max: 30,
      tag: [2, 7],
    })
    expect(
      catalogFilters({
        q: ['zupa', 'makaron'],
        scope: 'admin',
        prep_time_max: '31',
        tag: ['-1', '0', '3.5', 'NaN', '9007199254740993'],
      }),
    ).toEqual({
      limit: 50,
      q: undefined,
      scope: undefined,
      prep_time_max: undefined,
      tag: undefined,
    })
  })
  it('zachowuje kontekst UX02, nie przenosi obcego adresu powrotu ani offsetu', () => {
    expect(
      catalogQuery({
        q: 'zupa',
        selectedDate: '2031-04-09',
        from: '2031-04-07',
        to: '2031-04-13',
        next: 'https://example.com',
        offset: '100',
      }),
    ).toEqual({
      q: 'zupa',
      tag: undefined,
      scope: undefined,
      prep_time_max: undefined,
      selectedDate: '2031-04-09',
      from: '2031-04-07',
      to: '2031-04-13',
    })
  })
  function mockRouter(back: string | null) {
    const actual = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/przepisy', name: 'przepisy', component: { template: '<div />' } },
        { path: '/przepisy/:id', name: 'przepis-szczegol', component: { template: '<div />' } },
      ],
    })
    const previous = vi.fn()
    const router = {
      resolve: actual.resolve,
      options: { history: { state: { back } } },
      back: previous,
    } as unknown as Router
    return { router, previous }
  }
  it('zgodny poprzedni katalog używa Wstecz dla savedPosition, również przy innej kolejności query', () => {
    const { router, previous } = mockRouter('/przepisy?scope=global&q=zupa')
    const event = new MouseEvent('click', { button: 0, cancelable: true })
    returnToCatalog(event, router, { q: 'zupa', scope: 'global' })
    expect(event.defaultPrevented).toBe(true)
    expect(previous).toHaveBeenCalledOnce()
  })
  it.each([null, '/przepisy?q=inne', '/przepisy/8?q=zupa'])(
    'bez zgodnego katalogu (%s) pozostawia prawdziwy link',
    (back) => {
      const { router, previous } = mockRouter(back)
      const event = new MouseEvent('click', { button: 0, cancelable: true })
      returnToCatalog(event, router, { q: 'zupa' })
      expect(event.defaultPrevented).toBe(false)
      expect(previous).not.toHaveBeenCalled()
    },
  )
  it('Ctrl+klik pozostaje nawigacją linku w nowej karcie', () => {
    const { router, previous } = mockRouter('/przepisy?q=zupa')
    const event = new MouseEvent('click', { button: 0, ctrlKey: true, cancelable: true })
    returnToCatalog(event, router, { q: 'zupa' })
    expect(event.defaultPrevented).toBe(false)
    expect(previous).not.toHaveBeenCalled()
  })
})
