import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import PlanTygodniaPage from './PlanTygodniaPage.vue'
import type * as PlanningApi from '@/api/planning'
import type * as TemplatesApi from '@/api/templates'

const api = vi.hoisted(() => ({
  fetchPlanDays: vi.fn(),
  fetchDayTemplates: vi.fn(),
  fetchWeekTemplates: vi.fn(),
  fetchCycles: vi.fn(),
}))
vi.mock('@/api/planning', async (original) => ({
  ...(await original<typeof PlanningApi>()),
  fetchPlanDays: api.fetchPlanDays,
}))
vi.mock('@/api/templates', async (original) => ({
  ...(await original<typeof TemplatesApi>()),
  fetchDayTemplates: api.fetchDayTemplates,
  fetchWeekTemplates: api.fetchWeekTemplates,
  fetchCycles: api.fetchCycles,
}))
async function mountWeek(path = '/tydzien/2031-03-03?selectedDate=2031-03-05') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/tydzien/:weekStart?', name: 'tydzien', component: PlanTygodniaPage },
      { path: '/plan-dnia/:date?', name: 'plan-dnia', component: { template: '<div />' } },
    ],
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(PlanTygodniaPage, {
    global: {
      plugins: [
        router,
        [VueQueryPlugin, { queryClientConfig: { defaultOptions: { queries: { retry: false } } } }],
      ],
      stubs: {
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
  return { wrapper, router }
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
