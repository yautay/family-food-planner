import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import RecipePlanningPanel from '@/components/domain/planning/RecipePlanningPanel.vue'
import { queryKeys } from '@/api/queryKeys'
import CycleEditorDialog from '@/components/domain/planning/CycleEditorDialog.vue'
import PlanningDialog from '@/components/domain/planning/PlanningDialog.vue'
import BarChart from '@/components/charts/BarChart.vue'
import PlanTygodniaPage from './PlanTygodniaPage.vue'
import type * as PlanningApi from '@/api/planning'
import type * as TemplatesApi from '@/api/templates'

const api = vi.hoisted(() => ({
  fetchPlanDays: vi.fn(),
  fetchDayTemplates: vi.fn(),
  fetchWeekTemplates: vi.fn(),
  fetchCycles: vi.fn(),
  copyPlan: vi.fn(),
  deleteMeal: vi.fn(),
}))
vi.mock('@/api/planning', async (original) => ({
  ...(await original<typeof PlanningApi>()),
  fetchPlanDays: api.fetchPlanDays,
  copyPlan: api.copyPlan,
  deleteMeal: api.deleteMeal,
}))
vi.mock('@/api/templates', async (original) => ({
  ...(await original<typeof TemplatesApi>()),
  fetchDayTemplates: api.fetchDayTemplates,
  fetchWeekTemplates: api.fetchWeekTemplates,
  fetchCycles: api.fetchCycles,
}))
async function mountWeek(
  path = '/tydzien/2031-03-03?selectedDate=2031-03-05',
  seed?: (client: QueryClient) => void,
) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/tydzien/:weekStart?', name: 'tydzien', component: PlanTygodniaPage },
      { path: '/zakupy', name: 'zakupy', component: { template: '<div />' } },
      { path: '/przepisy/:id', name: 'przepis-szczegol', component: { template: '<div />' } },
      { path: '/plan-dnia/:date?', name: 'plan-dnia', component: { template: '<div />' } },
    ],
  })
  await router.push(path)
  await router.isReady()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  seed?.(client)
  const wrapper = mount(PlanTygodniaPage, {
    global: {
      plugins: [router, [VueQueryPlugin, { queryClient: client }]],
      stubs: {
        RecipePlanningPanel: true,
        BlockCopyDialog: true,
        CycleEditorDialog: true,
        PlanningDialog: true,
        ReuseHistoryDialog: true,
        TemplateApplyDialog: true,
        TemplateSaveDialog: true,
      },
    },
  })
  await flushPromises()
  return { wrapper, router, client }
}
describe('kontekst tygodnia UX02', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.fetchPlanDays.mockResolvedValue({ items: [] })
    api.fetchDayTemplates.mockResolvedValue({ items: [] })
    api.fetchWeekTemplates.mockResolvedValue({ items: [] })
    api.fetchCycles.mockResolvedValue({ items: [] })
  })
  afterEach(() => {
    vi.useRealTimers()
  })
  it('w poniedziałek następny tydzień zachowuje piątek, a Bieżący tydzień jawnie wybiera dziś', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2031, 2, 10, 12))
    const { wrapper, router } = await mountWeek('/tydzien/2031-03-03?selectedDate=2031-03-07')
    await wrapper.get('[data-testid="week-next"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/tydzien/2031-03-10')
    expect(router.currentRoute.value.query.selectedDate).toBe('2031-03-14')
    expect(wrapper.get('[data-testid="week-day-2031-03-14"]').classes()).toContain('ring-2')

    await wrapper.get('[data-testid="week-today"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.selectedDate).toBe('2031-03-10')
    expect(wrapper.get('[data-testid="week-day-2031-03-10"]').classes()).toContain('ring-2')
  })
  it('odczytuje środę z query, zapisuje wybór dnia i zachowuje offset przy zmianie tygodnia', async () => {
    const { wrapper, router } = await mountWeek()
    expect(wrapper.get('[data-testid="week-day-2031-03-05"]').classes()).toContain('ring-2')
    await wrapper.get('[data-testid="week-day-select-2031-03-07"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toMatchObject({
      selectedDate: '2031-03-07',
      from: '2031-03-03',
      to: '2031-03-09',
    })
    await wrapper.get('[data-testid="week-next"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/tydzien/2031-03-10')
    expect(router.currentRoute.value.query.selectedDate).toBe('2031-03-14')
    expect(api.fetchPlanDays).toHaveBeenLastCalledWith('2031-03-10', '2031-03-16')
  })
  it('zewnętrzne query odtwarza wybór, a dzień spoza tygodnia nie zmienia zakresu', async () => {
    const { wrapper, router } = await mountWeek()
    const replace = vi.spyOn(router, 'replace')
    await router.push('/tydzien/2031-03-03?selectedDate=2031-03-08')
    await flushPromises()
    expect(wrapper.get('[data-testid="week-day-2031-03-08"]').classes()).toContain('ring-2')
    expect(replace).not.toHaveBeenCalled()
    await router.push('/tydzien/2031-03-03?selectedDate=2031-04-01')
    await flushPromises()
    expect(wrapper.get('[data-testid="week-day-2031-03-03"]').classes()).toContain('ring-2')
  })
  it('błędna data ścieżki nie wywołuje RangeError', async () => {
    const { wrapper } = await mountWeek('/tydzien/2031-02-31')
    expect(wrapper.findAll('[data-testid^="week-day-select-"]')).toHaveLength(7)
    expect(api.fetchPlanDays).toHaveBeenCalledOnce()
  })
})

const nutrition = {
  kcal: '1200',
  protein_g: '30',
  fat_g: '40',
  carbs_g: '50',
  fiber_g: '6',
  sugars_g: '7',
  glycemic_load: '8',
  complete: true,
  missing: [],
}
const metric = { value: '1200', target: '2000', delta: '-800', status: 'below' as const }
const item: PlanningApi.PlanItem = {
  id: 5,
  recipe_id: 9,
  recipe_name: 'Długi pełny tytuł dania z warzywami i kaszą gryczaną',
  recipe_photo_thumb_url: null,
  product_id: null,
  product_name: null,
  amount: null,
  amount_unit: null,
  servings: '3.30',
  servings_split: [],
  position: 0,
  nutrition,
}
const meal: PlanningApi.PlanMeal = {
  id: 3,
  name: 'Obiad po spacerze',
  position: 0,
  kcal_target: '2000',
  kcal_status: 'below',
  items: [item],
  nutrition,
}
const day: PlanningApi.PlanDay = {
  id: 7,
  day: '2031-12-31',
  meals: [meal],
  nutrition,
  title: null,
  scope: 'household',
  owner_user_id: 1,
  goal_progress: { kcal: metric, protein_g: metric, fat_g: metric, carbs_g: metric },
  goal_valid_from: null,
  created_at: null,
  updated_at: null,
}

describe('agenda i akcje UX07', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    api.fetchPlanDays.mockResolvedValue({ items: [day] })
    api.fetchDayTemplates.mockResolvedValue({ items: [] })
    api.fetchWeekTemplates.mockResolvedValue({ items: [] })
    api.fetchCycles.mockResolvedValue({ items: [] })
  })
  it.each([true, false])(
    'zerowa energia z posiłkami nie udaje pustego tygodnia; complete=%s',
    async (complete) => {
      const zeroNutrition = {
        kcal: '0',
        protein_g: '0',
        fat_g: '0',
        carbs_g: '0',
        fiber_g: '0',
        sugars_g: '0',
        glycemic_load: '0',
        complete,
        missing: complete ? [] : ['Niepełne dane przepisu'],
      }
      const zeroMeal = {
        ...meal,
        nutrition: zeroNutrition,
        items: [{ ...item, nutrition: zeroNutrition }],
      }
      api.fetchPlanDays.mockResolvedValue({
        items: [
          {
            ...day,
            nutrition: zeroNutrition,
            meals: [
              zeroMeal,
              { ...zeroMeal, id: 4, name: 'Kolacja', items: [{ ...zeroMeal.items[0], id: 6 }] },
            ],
          },
        ],
      })
      const { wrapper } = await mountWeek('/tydzien/2031-12-29')
      const chart = wrapper.getComponent(BarChart)
      expect(chart.text()).toContain('Energia całego planu z dostępnych danych wynosi 0 kcal.')
      expect(chart.text()).not.toContain('Dodaj posiłki')
      expect(wrapper.find('[data-testid="week-empty"]').exists()).toBe(false)
      expect(
        wrapper
          .get('[data-testid="week-day-2031-12-31"]')
          .text()
          .includes('Niepełne wartości odżywcze'),
      ).toBe(!complete)
      if (!complete)
        expect(wrapper.get('[data-testid="week-day-2031-12-31"]').text()).toContain(
          'Niepełne dane przepisu',
        )
      wrapper.unmount()
    },
  )
  it('pusty tydzień zachowuje domyślną podpowiedź dodania posiłków', async () => {
    api.fetchPlanDays.mockResolvedValue({ items: [] })
    const { wrapper } = await mountWeek('/tydzien/2031-12-29')
    expect(wrapper.getComponent(BarChart).text()).toContain(
      'Dodaj posiłki, żeby zobaczyć rozkład tygodnia.',
    )
    expect(wrapper.getComponent(BarChart).text()).not.toContain(
      'Energia całego planu z dostępnych danych',
    )
    expect(wrapper.find('[data-testid="week-empty"]').exists()).toBe(true)
    wrapper.unmount()
  })
  it('przy dacie pozostawia krótki status, a pełne rzeczywiste braki udostępnia w rozwinięciu za daniami', async () => {
    const missing = [
      'Płatki owsiane pełnoziarniste z otrębami i pestkami dyni: produkt niezweryfikowany',
      'Produkt próbny z polskimi znakami — żółć: brak indeksu glikemicznego',
      'Jogurt naturalny z długą nazwą: brak wartości białka',
    ]
    api.fetchPlanDays.mockResolvedValue({
      items: [{ ...day, nutrition: { ...nutrition, complete: false, missing } }],
    })
    const { wrapper } = await mountWeek('/tydzien/2031-12-29')
    const card = wrapper.get('[data-testid="week-day-2031-12-31"]')
    const dateHeader = card.get('header')
    expect(dateHeader.text()).toContain('Niepełne wartości odżywcze')
    for (const reason of missing) expect(dateHeader.text()).not.toContain(reason)
    const details = card.get<HTMLDetailsElement>(
      '[data-testid="week-nutrition-details-2031-12-31"]',
    )
    const summary = details.get('summary')
    expect(summary.text()).toBe('Braki danych odżywczych (3)')
    expect(details.element.open).toBe(false)
    expect(details.element.closest('header')).toBeNull()
    expect(
      card.get('[data-testid="week-recipe-5"]').element.compareDocumentPosition(details.element) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).not.toBe(0)
    const reasons = details.findAll('li')
    expect(reasons.map((reason) => reason.text())).toEqual(missing)
    expect(reasons.every((reason) => !reason.isVisible())).toBe(true)
    await summary.trigger('click')
    expect(details.element.open).toBe(true)
    expect(reasons.every((reason) => reason.isVisible())).toBe(true)
    await summary.trigger('click')
    expect(details.element.open).toBe(false)
    expect(reasons.every((reason) => !reason.isVisible())).toBe(true)
    wrapper.unmount()
  })
  it('przekazuje dzień i posiłek do wspólnego panelu dodania i zamiany', async () => {
    const { wrapper } = await mountWeek('/tydzien/2031-12-29?selectedDate=2031-12-31')
    expect(wrapper.get('[data-testid="week-recipe-5"]').text()).toBe(item.recipe_name)
    const panel = wrapper.getComponent(RecipePlanningPanel)
    const newMeal = wrapper.get('[data-testid="week-add-2031-12-31"]')
    expect(newMeal.text()).toBe('Nowy posiłek z daniem')
    expect(newMeal.attributes('aria-label')).toBe('Nowy posiłek z daniem: 2031-12-31')
    await newMeal.trigger('click')
    expect(panel.props()).toMatchObject({
      open: true,
      date: day.day,
      meal: null,
      replaceItem: null,
    })
    const existingMeal = wrapper.get('[data-testid="week-meal-add-3"]')
    expect(existingMeal.text()).toBe('Dodaj do posiłku')
    expect(existingMeal.attributes('aria-label')).toBe(
      'Dodaj do posiłku: Obiad po spacerze, 2031-12-31',
    )
    await existingMeal.trigger('click')
    expect(panel.props()).toMatchObject({ open: true, date: day.day, meal, replaceItem: null })
    await wrapper.get('[data-testid="week-replace-5"]').trigger('click')
    expect(panel.props()).toMatchObject({ open: true, date: day.day, meal, replaceItem: item })
    panel.vm.$emit('saved', { day, mealId: 3, itemId: 5, mode: 'replace' })
    await flushPromises()
    expect(wrapper.get('[data-testid="week-result"]').text()).toContain('2031-12-31')
    expect(wrapper.getComponent(BarChart).props('target')).toBeNull()
    expect(wrapper.getComponent(BarChart).props('data')[0]?.empty).toBe(true)
    expect(wrapper.text()).not.toContain('2 000')
    wrapper.unmount()
  })
  it('zakupy dostają cały widoczny zakres przez granicę roku; przepis dostaje kontekst powrotu', async () => {
    const { wrapper } = await mountWeek('/tydzien/2031-12-29?selectedDate=2031-12-31')
    expect(wrapper.get('[data-testid="week-shopping"]').attributes('href')).toBe(
      '/zakupy?selectedDate=2031-12-31&from=2031-12-29&to=2032-01-04',
    )
    expect(wrapper.get('[data-testid="week-recipe-5"]').attributes('href')).toContain(
      'returnTo=week&selectedDate=2031-12-31&from=2031-12-29&to=2032-01-04',
    )
    wrapper.unmount()
  })
  it('błąd pierwszego odczytu nie renderuje pustego planu; błąd refetch zachowuje cache', async () => {
    api.fetchPlanDays.mockRejectedValueOnce(new Error('offline'))
    const { wrapper, client } = await mountWeek()
    expect(wrapper.get('[data-testid="week-load-error"]').text()).toContain('Nie udało')
    expect(wrapper.find('[data-testid="week-grid"]').exists()).toBe(false)
    api.fetchPlanDays.mockResolvedValueOnce({ items: [day] })
    await wrapper.get('[data-testid="week-load-error"] button').trigger('click')
    await flushPromises()
    api.fetchPlanDays.mockRejectedValueOnce(new Error('offline'))
    await client.invalidateQueries()
    await flushPromises()
    expect(wrapper.find('[data-testid="week-refresh-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="week-grid"]').exists()).toBe(true)
    wrapper.unmount()
  })
  it('częściowe przeniesienie pokazuje prawdziwy skutek i zamyka ponawianie kopiowania', async () => {
    api.copyPlan.mockResolvedValue({ items: [] })
    api.deleteMeal.mockRejectedValue(new Error('500'))
    const { wrapper } = await mountWeek('/tydzien/2031-12-29')
    await wrapper.get('[data-testid="week-meal-move-3"]').trigger('click')
    const dialog = wrapper
      .findAllComponents(PlanningDialog)
      .find((component) => component.props('testid') === 'move-meal-dialog')!
    dialog.vm.$emit('submit')
    await flushPromises()
    expect(api.copyPlan).toHaveBeenCalledTimes(1)
    expect(api.deleteMeal).toHaveBeenCalledWith(3)
    expect(wrapper.get('[data-testid="week-action-error"]').text()).toContain('został skopiowany')
    expect(dialog.props('open')).toBe(false)
    wrapper.unmount()
  })
})

const cachedCycle: TemplatesApi.Cycle = {
  id: 4,
  name: 'Rotacja z cache',
  scope: 'private',
  owner_user_id: 1,
  template_ids: [1, 2],
  template_names: ['A', 'B'],
  start_date: null,
  created_at: '2031-01-01T12:00:00Z',
  updated_at: '2031-01-01T12:00:00Z',
}
describe('odświeżenie zapisanej rotacji cyklu', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    api.fetchPlanDays.mockResolvedValue({ items: [] })
    api.fetchDayTemplates.mockResolvedValue({ items: [] })
    api.fetchWeekTemplates.mockResolvedValue({ items: [] })
  })
  it('cached A→B nie kończy sprawdzania podczas held GET; po odpowiedzi przekazuje C→D', async () => {
    let resolveRead!: (result: TemplatesApi.CycleList) => void
    api.fetchCycles.mockReturnValue(
      new Promise((resolve) => {
        resolveRead = resolve
      }),
    )
    const { wrapper } = await mountWeek(undefined, (client) =>
      client.setQueryData(queryKeys.cycles.all, { items: [cachedCycle], total: 1 }),
    )
    const dialog = wrapper.getComponent(CycleEditorDialog)
    expect(dialog.props('cycles')[0]?.template_ids).toEqual([1, 2])
    expect(dialog.props('loading')).toBe(true)
    resolveRead({
      items: [{ ...cachedCycle, template_ids: [3, 4], template_names: ['C', 'D'] }],
      total: 1,
    })
    await flushPromises()
    expect(dialog.props('loading')).toBe(false)
    expect(dialog.props('cycles')[0]?.template_ids).toEqual([3, 4])
    wrapper.unmount()
  })
  it('odmowa odświeżenia pozostawia cache, ale blokuje sprawdzanie i podaje błąd', async () => {
    let rejectRead!: (reason: Error) => void
    api.fetchCycles.mockReturnValue(
      new Promise((_resolve, reject) => {
        rejectRead = reject
      }),
    )
    const { wrapper } = await mountWeek(undefined, (client) =>
      client.setQueryData(queryKeys.cycles.all, { items: [cachedCycle], total: 1 }),
    )
    const dialog = wrapper.getComponent(CycleEditorDialog)
    expect(dialog.props('loading')).toBe(true)
    rejectRead(new Error('Odmowa GET /cycles'))
    await flushPromises()
    expect(dialog.props('cycles')[0]?.template_ids).toEqual([1, 2])
    expect(dialog.props('unavailable')).toBe(true)
    expect(dialog.props('error')).toContain('Nie udało się odświeżyć')
    wrapper.unmount()
  })
})
