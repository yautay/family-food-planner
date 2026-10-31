import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import type { RecipeSummary } from '@/api/recipes'
import RecipePlanningPanel from '@/components/domain/planning/RecipePlanningPanel.vue'
import PrzepisyPage from './PrzepisyPage.vue'

const { fetchRecipes, fetchTags } = vi.hoisted(() => ({
  fetchRecipes: vi.fn(),
  fetchTags: vi.fn(),
}))
vi.mock('@/api/recipes', () => ({ fetchRecipes, fetchTags }))

function recipe(id: number): RecipeSummary {
  return {
    id,
    name: `Przepis ${id}`,
    scope: 'household',
    owner_user_id: 1,
    base_servings: 2,
    prep_time_min: 20,
    difficulty: 2,
    is_archived: false,
    photo_url: null,
    photo_thumb_url: null,
    tags: [],
    avg_rating: null,
    ratings_count: 0,
    my_rating: null,
    nutrition: {
      kcal: '420',
      protein_g: '20',
      fat_g: '10',
      carbs_g: '55',
      fiber_g: '6',
      sugars_g: '8',
      glycemic_load: '25',
      complete: true,
      missing: [],
    },
    created_at: '2026-08-21T10:00:00Z',
    updated_at: '2026-08-21T10:00:00Z',
  }
}
const ALL = Array.from({ length: 103 }, (_unused, index) => recipe(index + 1))
let client: QueryClient
let wrapper: VueWrapper
let router: Router
async function render(url = '/przepisy') {
  client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/przepisy', name: 'przepisy', component: { template: '<div />' } },
      { path: '/przepisy/nowy', name: 'przepis-nowy', component: { template: '<div />' } },
      { path: '/przepisy/:id', name: 'przepis-szczegol', component: { template: '<div />' } },
      { path: '/plan-dnia/:date', name: 'plan-dnia', component: { template: '<div />' } },
    ],
  })
  await router.push(url)
  wrapper = mount(PrzepisyPage, {
    global: {
      plugins: [router, [VueQueryPlugin, { queryClient: client }]],
      stubs: { RecipePlanningPanel: { props: ['open', 'recipe', 'date'], template: '<div />' } },
    },
  })
  await flushPromises()
  return wrapper
}
beforeEach(() => {
  vi.clearAllMocks()
  fetchTags.mockResolvedValue({ items: [{ id: 7, name: 'ulubione', is_system: true }], total: 1 })
  fetchRecipes.mockImplementation(({ offset = 0, limit = 50 }) =>
    Promise.resolve({ items: ALL.slice(offset, offset + limit), total: ALL.length }),
  )
})
afterEach(() => {
  wrapper?.unmount()
  client?.clear()
  vi.useRealTimers()
})

describe('PrzepisyPage — katalog i URL', () => {
  it('kolejne strony pozostają osiągalne z prawdziwymi linkami szczegółów i stałym limitem', async () => {
    await render()
    expect(wrapper.findAll('[data-testid^="recipe-open-"]')).toHaveLength(50)
    expect(wrapper.get('[data-testid="recipes-total"]').text()).toContain('50 z 103')
    await wrapper.get('[data-testid="recipes-load-more"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-testid^="recipe-open-"]')).toHaveLength(100)
    expect(fetchRecipes).toHaveBeenLastCalledWith(
      expect.objectContaining({ limit: 50, offset: 50 }),
    )
    await wrapper.get('[data-testid="recipes-load-more"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-testid^="recipe-open-"]')).toHaveLength(103)
    expect(wrapper.get('[data-testid="recipe-open-103"]').attributes('href')).toBe('/przepisy/103')
    expect(wrapper.find('[data-testid="recipes-load-more"]').exists()).toBe(false)
  })

  it('odczytuje q/scope/tag/czas i kontekst kalendarza z bezpośredniego URL', async () => {
    await render(
      '/przepisy?q=zupa&scope=global&tag=7&prep_time_max=30&selectedDate=2031-04-09&from=2031-04-07&to=2031-04-13',
    )
    expect(fetchRecipes).toHaveBeenCalledWith({
      limit: 50,
      offset: 0,
      q: 'zupa',
      scope: 'global',
      tag: [7],
      prep_time_max: 30,
    })
    expect(wrapper.get('[data-testid="recipes-search"]').element).toHaveProperty('value', 'zupa')
    expect(wrapper.get('[data-testid="recipes-quick"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('[data-testid="recipes-filters"]').attributes('open')).toBeUndefined()
    expect(wrapper.get('[data-testid="recipes-active-filters"]').text()).toContain(
      'Aktywne filtry (4)',
    )
    expect(wrapper.get('[data-testid="recipes-active-filters"]').text()).toContain('Dla wszystkich')
    expect(wrapper.get('[data-testid="recipes-active-filters"]').text()).toContain('ulubione')
    await wrapper.get('[data-testid="recipes-filters-toggle"]').trigger('click')
    expect(wrapper.get('[data-testid="recipes-scope-global"]').attributes('aria-pressed')).toBe(
      'true',
    )
    expect(wrapper.get('[data-testid="recipes-tag-7"]').attributes('aria-pressed')).toBe('true')
    const target = router.resolve(wrapper.get('[data-testid="recipe-open-1"]').attributes('href')!)
    expect(target.query).toEqual(router.currentRoute.value.query)
  })

  it('zmiana filtrów zapisuje query i odpytuje serwer od offsetu zero, zachowując kalendarz', async () => {
    await render('/przepisy?selectedDate=2031-04-09')
    await wrapper.get('[data-testid="recipes-load-more"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="recipes-filters-toggle"]').trigger('click')
    await wrapper.get('[data-testid="recipes-scope-global"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="recipes-tag-7"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="recipes-quick"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({
      selectedDate: '2031-04-09',
      scope: 'global',
      tag: ['7'],
      prep_time_max: '30',
    })
    expect(fetchRecipes).toHaveBeenLastCalledWith(
      expect.objectContaining({
        scope: 'global',
        tag: [7],
        prep_time_max: 30,
        limit: 50,
        offset: 0,
      }),
    )
    expect(wrapper.findAll('[data-testid^="recipe-card-"]')).toHaveLength(50)
    await wrapper.get('[data-testid="recipes-clear"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ selectedDate: '2031-04-09' })
  })

  it('wyszukiwanie ma debounce i reaguje na zewnętrzną zmianę URL bez nadpisania go', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    await render('/przepisy?q=zupa')
    await wrapper.get('[data-testid="recipes-search"]').setValue('owsianka')
    await vi.advanceTimersByTimeAsync(260)
    await flushPromises()
    expect(router.currentRoute.value.query.q).toBe('owsianka')
    expect(fetchRecipes).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'owsianka' }))
    await wrapper.get('[data-testid="recipes-search"]').setValue('spóźniona fraza')
    await router.replace('/przepisy?q=makaron')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(260)
    await flushPromises()
    expect(router.currentRoute.value.query.q).toBe('makaron')
    expect(wrapper.get('[data-testid="recipes-search"]').element).toHaveProperty('value', 'makaron')
  })

  it('pusty filtr daje wyczyszczenie i prawdziwy link utworzenia przepisu', async () => {
    fetchRecipes.mockResolvedValue({ items: [], total: 0 })
    await render('/przepisy?q=bez-wyniku')
    expect(wrapper.get('[data-testid="recipes-empty"]').text()).toContain('Brak wyników')
    expect(wrapper.get('[data-testid="recipes-empty-add"]').attributes('href')).toContain(
      '/przepisy/nowy?q=bez-wyniku',
    )
  })

  it('planowanie karty podaje rzeczywisty przepis i datę, a zapis kieruje do dnia odpowiedzi', async () => {
    await render('/przepisy?selectedDate=2031-04-09&from=2031-04-07&to=2031-04-13')
    await wrapper.get('[data-testid="recipe-plan-2"]').trigger('click')
    const panel = wrapper.findComponent(RecipePlanningPanel)
    expect(panel.props()).toMatchObject({ open: true, recipe: { id: 2 }, date: '2031-04-09' })
    // Test granicy konsumenta: zapis i walidacja HTTP należą do testów prawdziwego panelu.
    panel.vm.$emit('saved', { day: { day: '2031-04-11' }, mealId: 50, itemId: 80, mode: 'add' })
    await flushPromises()
    expect(router.currentRoute.value.params.date).toBe('2031-04-11')
    expect(router.currentRoute.value.query).toEqual({
      selectedDate: '2031-04-11',
      from: '2031-04-07',
      to: '2031-04-13',
    })
    expect(panel.props('open')).toBe(false)
  })
})

describe('PrzepisyPage — loading, błędy i cache', () => {
  it('pierwsze ładowanie nie jest pustym katalogiem', async () => {
    fetchRecipes.mockReturnValue(new Promise(() => {}))
    await render()
    expect(wrapper.get('[role="status"][aria-busy="true"]').text()).toContain('Wczytywanie')
    expect(wrapper.find('[data-testid="recipes-empty"]').exists()).toBe(false)
  })

  it('błąd pierwszej strony ma skuteczne ponowienie bez fałszywego empty', async () => {
    fetchRecipes.mockRejectedValueOnce(new Error('offline'))
    await render()
    expect(wrapper.find('[data-testid="recipes-empty"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="recipes-error"]').exists()).toBe(true)
    await wrapper.get('[data-testid="recipes-error"] button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="recipes-error"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid^="recipe-card-"]')).toHaveLength(50)
  })

  it('błąd drugiej strony zachowuje karty i ponawia offset 50', async () => {
    await render()
    fetchRecipes.mockRejectedValueOnce(new Error('offline'))
    await wrapper.get('[data-testid="recipes-load-more"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-testid^="recipe-card-"]')).toHaveLength(50)
    expect(wrapper.find('[data-testid="recipes-load-more-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="recipes-error"]').exists()).toBe(false)
    await wrapper.get('[data-testid="recipes-load-more"]').trigger('click')
    await flushPromises()
    expect(fetchRecipes).toHaveBeenLastCalledWith(
      expect.objectContaining({ offset: 50, limit: 50 }),
    )
    expect(wrapper.findAll('[data-testid^="recipe-card-"]')).toHaveLength(100)
  })

  it('błąd refetch zachowuje dane także na końcu katalogu i ma osobne ponowienie', async () => {
    fetchRecipes.mockResolvedValue({ items: ALL.slice(0, 2), total: 2 })
    await render()
    fetchRecipes.mockRejectedValueOnce(new Error('offline'))
    await wrapper.get('[data-testid="recipes-refresh"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-testid^="recipe-card-"]')).toHaveLength(2)
    expect(wrapper.find('[data-testid="recipes-refresh-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="recipes-load-more"]').exists()).toBe(false)
    await wrapper.get('[data-testid="recipes-refresh-error"] button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="recipes-refresh-error"]').exists()).toBe(false)
  })

  it('błąd tagów zachowuje aktywny tag URL, nie unieważnia poprawnych kart', async () => {
    fetchTags.mockRejectedValue(new Error('offline'))
    await render('/przepisy?tag=7')
    expect(wrapper.get('[data-testid="recipes-active-filters"]').text()).toContain('Tag: #7')
    expect(wrapper.get('[data-testid="recipes-clear"]').isVisible()).toBe(true)
    await wrapper.get('[data-testid="recipes-filters-toggle"]').trigger('click')
    expect(wrapper.find('[data-testid="recipes-tags-error"]').exists()).toBe(true)
    expect(fetchRecipes).toHaveBeenCalledWith(expect.objectContaining({ tag: [7] }))
    expect(wrapper.findAll('[data-testid^="recipe-card-"]')).toHaveLength(50)
    fetchTags.mockResolvedValue({ items: [{ id: 7, name: 'ulubione' }], total: 1 })
    await wrapper.get('[data-testid="recipes-tags-error"] button').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="recipes-tag-7"]').attributes('aria-pressed')).toBe('true')
  })
})

describe('PrzepisyPage — domyślnie zwinięte dodatkowe filtry', () => {
  it('wiele pełnych nazw tagów nie rozwija panelu; otwarcie i zamknięcie nie zmienia zapytania ani wyników', async () => {
    const tagName = 'Na rodzinny obiad po wspólnym spacerze'
    fetchTags.mockResolvedValue({
      items: Array.from({ length: 40 }, (_, index) => ({
        id: index + 1,
        name: `${tagName} ${index + 1}`,
        is_system: false,
      })),
      total: 40,
    })
    await render()
    const panel = wrapper.get('[data-testid="recipes-filters"]')
    expect(panel.element.tagName).toBe('DETAILS')
    expect(panel.attributes('open')).toBeUndefined()
    expect(wrapper.get('[data-testid="recipes-filters-toggle"]').element.tagName).toBe('SUMMARY')
    expect(wrapper.get('[data-testid="recipes-tag-7"]').isVisible()).toBe(false)
    expect(wrapper.findAll('[data-testid^="recipe-card-"]')).toHaveLength(50)
    const requests = fetchRecipes.mock.calls.length
    await wrapper.get('[data-testid="recipes-filters-toggle"]').trigger('click')
    expect(panel.attributes('open')).toBeDefined()
    expect(wrapper.get('[data-testid="recipes-tag-7"]').isVisible()).toBe(true)
    expect(wrapper.get('[data-testid="recipes-tag-7"]').text()).toBe(`${tagName} 7`)
    await wrapper.get('[data-testid="recipes-filters-toggle"]').trigger('click')
    expect(panel.attributes('open')).toBeUndefined()
    expect(fetchRecipes).toHaveBeenCalledTimes(requests)
    expect(router.currentRoute.value.query).toEqual({})
  })

  it('zamknięcie zachowuje wybrane scope/tag w URL i pełny opis aktywnych filtrów poza panelem', async () => {
    await render()
    await wrapper.get('[data-testid="recipes-filters-toggle"]').trigger('click')
    await wrapper.get('[data-testid="recipes-scope-household"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="recipes-tag-7"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="recipes-filters-toggle"]').trigger('click')
    expect(wrapper.get('[data-testid="recipes-filters"]').attributes('open')).toBeUndefined()
    expect(wrapper.get('[data-testid="recipes-active-filters"]').isVisible()).toBe(true)
    expect(wrapper.get('[data-testid="recipes-active-filters"]').text()).toContain(
      'Aktywne filtry (2): Widoczność: Rodzinny · Tag: ulubione',
    )
    expect(wrapper.get('[data-testid="recipes-filters-toggle"]').text()).toContain('(2)')
    expect(router.currentRoute.value.query).toEqual({ scope: 'household', tag: ['7'] })
    await wrapper.get('[data-testid="recipes-clear"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({})
    expect(wrapper.find('[data-testid="recipes-active-filters"]').exists()).toBe(false)
  })
})
