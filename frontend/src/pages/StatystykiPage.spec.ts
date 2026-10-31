import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import StatystykiPage from './StatystykiPage.vue'
import type { DailyStats, StatsDay } from '@/api/stats'
import { queryKeys } from '@/api/queryKeys'
import ErrorState from '@/components/domain/ErrorState.vue'

/**
 * Strona statystyk nie liczy niczego domenowego — testujemy to, co robi
 * z odpowiedzią `/stats/daily`: zakres, zakładki, luki, linię celu schodkową,
 * podsumowanie i stan pusty. Zapytanie jest zamockowane (05_FRONTEND §8).
 */
const statsApi = vi.hoisted(() => ({ fetchDailyStats: vi.fn(), MAX_STATS_RANGE_DAYS: 92 }))
vi.mock('@/api/stats', () => statsApi)

function nutrition(kcal: string, macros: [string, string, string], complete = true) {
  const [protein, fat, carbs] = macros
  return {
    kcal,
    protein_g: protein,
    fat_g: fat,
    carbs_g: carbs,
    fiber_g: '0',
    sugars_g: '0',
    glycemic_load: '0',
    complete,
    missing: complete ? [] : ['Cebula: brak IG'],
  }
}

function day(
  date: string,
  options: {
    kcal?: string
    macros?: [string, string, string]
    goalKcal?: string
    complete?: boolean
  } = {},
): StatsDay {
  const hasPlan = options.kcal !== undefined
  return {
    day: date,
    has_plan: hasPlan,
    nutrition: hasPlan
      ? nutrition(options.kcal ?? '0', options.macros ?? ['100', '60', '200'], options.complete)
      : null,
    goal:
      options.goalKcal === undefined
        ? null
        : {
            kcal: options.goalKcal,
            protein_g: '100.0',
            fat_g: '60.0',
            carbs_g: '200.0',
            valid_from: '2026-01-01',
          },
    status: {
      kcal: hasPlan && options.goalKcal !== undefined ? 'ok' : null,
      protein_g: null,
      fat_g: null,
      carbs_g: null,
    },
  }
}

function response(days: StatsDay[], overrides: Partial<DailyStats['summary']> = {}): DailyStats {
  const withPlan = days.filter((entry) => entry.has_plan).length
  return {
    days,
    summary: {
      days_in_range: days.length,
      days_with_plan: withPlan,
      avg: withPlan > 0 ? nutrition('1900', ['100', '60', '200']) : null,
      goal_progress: {
        kcal: { value: '1900', target: '2000', delta: '-100', status: 'ok' },
        protein_g: { value: '100', target: '100.0', delta: '0', status: 'ok' },
        fat_g: { value: '60', target: null, delta: null, status: null },
        carbs_g: { value: '200', target: '200.0', delta: '0', status: 'ok' },
      },
      ...overrides,
    },
  }
}

const WEEK = [
  day('2026-08-17', { kcal: '1800', goalKcal: '2000' }),
  day('2026-08-18', { kcal: '2000', goalKcal: '2000' }),
  day('2026-08-19'),
  day('2026-08-20', { kcal: '1900', goalKcal: '2400' }),
  day('2026-08-21', { kcal: '1900', goalKcal: '2400' }),
  day('2026-08-22', { kcal: '1900', goalKcal: '2400' }),
  day('2026-08-23', { kcal: '1900', goalKcal: '2400' }),
]

async function mountPage(
  path = '/statystyki',
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } }),
) {
  setActivePinia(createPinia())
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/statystyki', name: 'statystyki', component: StatystykiPage },
      { path: '/plan-dnia/:date?', name: 'plan-dnia', component: { template: '<div />' } },
    ],
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(StatystykiPage, {
    global: {
      // `retry: false` — aplikacja ponawia raz (main.ts), a test ma sprawdzać
      // komunikat błędu, nie czekać na politykę ponowień.
      plugins: [router, [VueQueryPlugin, { queryClient }]],
      stubs: { RouterLink: { template: '<a><slot /></a>' } },
    },
  })
  await flushPromises()
  return wrapper
}

describe('StatystykiPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    statsApi.fetchDailyStats.mockResolvedValue(response(WEEK))
  })

  it('odczytuje historyczny zakres URL, a nie bieżący tydzień', async () => {
    const wrapper = await mountPage(
      '/statystyki?from=2031-03-03&to=2031-03-09&selectedDate=2031-03-05',
    )
    expect(statsApi.fetchDailyStats).toHaveBeenCalledWith('2031-03-03', '2031-03-09')
    expect(wrapper.get('[data-testid="stats-preset-week"]').attributes('aria-pressed')).toBe('true')
    await wrapper.get('[data-testid="stats-preset-month"]').trigger('click')
    await flushPromises()
    expect(statsApi.fetchDailyStats).toHaveBeenLastCalledWith('2031-03-01', '2031-03-31')
    expect(wrapper.vm.$router.currentRoute.value.query).toMatchObject({
      from: '2031-03-01',
      to: '2031-03-31',
      selectedDate: '2031-03-05',
    })
  })

  it('zakres własny trafia do URL dopiero gdy obie daty są poprawne, szkic pozostaje', async () => {
    const wrapper = await mountPage(
      '/statystyki?from=2031-03-03&to=2031-03-09&selectedDate=2031-03-05',
    )
    await wrapper.get('[data-testid="stats-preset-custom"]').trigger('click')
    await wrapper.get('[data-testid="stats-to"]').setValue('')
    await wrapper.get('[data-testid="stats-from"]').setValue('2031-04-05')
    await flushPromises()
    expect(wrapper.get<HTMLInputElement>('[data-testid="stats-to"]').element.value).toBe('')
    expect(wrapper.get<HTMLInputElement>('[data-testid="stats-from"]').element.value).toBe(
      '2031-04-05',
    )
    expect(wrapper.vm.$router.currentRoute.value.query.to).toBe('2031-03-09')
    await wrapper.get('[data-testid="stats-to"]').setValue('2031-04-07')
    await flushPromises()
    expect(wrapper.vm.$router.currentRoute.value.query).toMatchObject({
      from: '2031-04-05',
      to: '2031-04-07',
      selectedDate: '2031-04-05',
    })
    expect(statsApi.fetchDailyStats).toHaveBeenLastCalledWith('2031-04-05', '2031-04-07')
  })

  it('zewnętrzna zmiana URL odtwarza zakres bez zapętlonych replace', async () => {
    const wrapper = await mountPage()
    const router = wrapper.vm.$router
    const replace = vi.spyOn(router, 'replace')
    await router.push('/statystyki?from=2031-04-05&to=2031-04-07&selectedDate=2031-04-06')
    await flushPromises()
    expect(wrapper.get<HTMLInputElement>('[data-testid="stats-from"]').element.value).toBe(
      '2031-04-05',
    )
    expect(statsApi.fetchDailyStats).toHaveBeenLastCalledWith('2031-04-05', '2031-04-07')
    expect(replace).not.toHaveBeenCalled()
  })

  it.each([
    ['month', '2031-04-01', '2031-04-30'],
    ['week', '2031-03-31', '2031-04-06'],
  ])(
    'preset %s po kwietniowym zakresie własnym używa nowego dnia bez reloadu',
    async (preset, from, to) => {
      const wrapper = await mountPage(
        '/statystyki?from=2031-03-03&to=2031-03-09&selectedDate=2031-03-05',
      )
      await wrapper.get('[data-testid="stats-preset-custom"]').trigger('click')
      await wrapper.get('[data-testid="stats-to"]').setValue('')
      await wrapper.get('[data-testid="stats-from"]').setValue('2031-04-05')
      await wrapper.get('[data-testid="stats-to"]').setValue('2031-04-07')
      await flushPromises()
      expect(wrapper.vm.$router.currentRoute.value.query.selectedDate).toBe('2031-04-05')

      const replace = vi.spyOn(wrapper.vm.$router, 'replace')
      await wrapper.get(`[data-testid="stats-preset-${preset}"]`).trigger('click')
      await flushPromises()
      expect(statsApi.fetchDailyStats).toHaveBeenLastCalledWith(from, to)
      expect(wrapper.vm.$router.currentRoute.value.query).toMatchObject({
        from,
        to,
        selectedDate: '2031-04-05',
      })
      expect(replace).toHaveBeenCalledOnce()
    },
  )

  it.each([
    'from=2031-02-31&to=2031-03-05',
    'from=2031-03-03',
    'from=2031-03-03&from=2031-03-04&to=2031-03-05',
  ])('ignoruje niepoprawny zakres URL bez błędu daty i zapętlenia: %s', async (query) => {
    const wrapper = await mountPage(`/statystyki?${query}`)
    const replace = vi.spyOn(wrapper.vm.$router, 'replace')
    await flushPromises()
    expect(statsApi.fetchDailyStats).toHaveBeenCalledTimes(1)
    expect(replace).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="stats-error"]').exists()).toBe(false)
  })

  it('startuje od bieżącego tygodnia i pyta o zakres pon–nd', async () => {
    await mountPage()

    expect(statsApi.fetchDailyStats).toHaveBeenCalledTimes(1)
    const [from, to] = statsApi.fetchDailyStats.mock.calls[0] as [string, string]
    // Poniedziałek–niedziela to siedem dni; sam zakres zależy od „dziś".
    expect(new Date(`${to}T00:00:00Z`).getTime() - new Date(`${from}T00:00:00Z`).getTime()).toBe(
      6 * 24 * 60 * 60 * 1000,
    )
  })

  it('pokazuje obie zakładki i przełącza wykres', async () => {
    const wrapper = await mountPage()

    expect(wrapper.get('[data-testid="stats-tab-kcal"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.find('[data-testid="stats-chart-kcal"]').exists()).toBe(true)

    await wrapper.get('[data-testid="stats-tab-macros"]').trigger('click')

    expect(wrapper.find('[data-testid="stats-chart-macros"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="stats-tab-macros"]').attributes('aria-pressed')).toBe('true')
  })

  it('zmiana presetu zakresu przeładowuje dane', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="stats-preset-month"]').trigger('click')
    await flushPromises()

    expect(statsApi.fetchDailyStats).toHaveBeenCalledTimes(2)
    const [from, to] = statsApi.fetchDailyStats.mock.calls[1] as [string, string]
    expect(from.endsWith('-01')).toBe(true)
    expect(from.slice(0, 7)).toBe(to.slice(0, 7))
  })

  it('zakres własny odsłania date-pickery i waliduje odwróconą kolejność', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="stats-preset-custom"]').trigger('click')
    await wrapper.get('[data-testid="stats-from"]').setValue('2026-08-20')
    await wrapper.get('[data-testid="stats-to"]').setValue('2026-08-10')
    await flushPromises()

    expect(wrapper.get('[data-testid="stats-error"]').text()).toContain('nie może być późniejsza')
  })

  it('zakres dłuższy niż 92 dni nie idzie do serwera', async () => {
    const wrapper = await mountPage()
    const callsBefore = statsApi.fetchDailyStats.mock.calls.length

    await wrapper.get('[data-testid="stats-preset-custom"]').trigger('click')
    await wrapper.get('[data-testid="stats-from"]').setValue('2026-01-01')
    await wrapper.get('[data-testid="stats-to"]').setValue('2026-12-31')
    await flushPromises()

    expect(wrapper.get('[data-testid="stats-error"]').text()).toContain('92')
    expect(statsApi.fetchDailyStats.mock.calls).toHaveLength(callsBefore)
  })

  it('wyczyszczona data zakresu nie udaje ładowania ani pustych statystyk', async () => {
    const wrapper = await mountPage()
    const callsBefore = statsApi.fetchDailyStats.mock.calls.length

    await wrapper.get('[data-testid="stats-preset-custom"]').trigger('click')
    await wrapper.get('[data-testid="stats-to"]').setValue('')
    await flushPromises()

    expect(wrapper.get('[data-testid="stats-error"]').text()).toContain('Podaj obie daty')
    expect(wrapper.find('[data-testid="stats-range-blocked"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="stats-empty"]').exists()).toBe(false)
    expect(statsApi.fetchDailyStats.mock.calls).toHaveLength(callsBefore)
  })

  it('dzień bez planu rysuje lukę, a nie zerowy słupek', async () => {
    const wrapper = await mountPage()

    // 19.08 nie ma planu: obrys luki istnieje, segmentu wartości nie ma.
    expect(wrapper.find('[data-testid="stats-kcal-chart-gap-2026-08-19"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="stats-kcal-chart-bar-2026-08-19-kcal"]').exists()).toBe(
      false,
    )
  })

  it('linia celu jest schodkowa i przerywa się na dniu bez celu', async () => {
    const wrapper = await mountPage()

    // Cel 2000 (2 dni) → przerwa na dniu bez planu i bez celu → cel 2400 (4 dni).
    const runs = wrapper.findAll('[data-testid^="stats-kcal-chart-target-step-"]')
    expect(runs).toHaveLength(2)
    const levels = runs.map((run) => run.attributes('data-levels'))
    expect(levels[0]).toBe('17,17')
    expect(levels[1]).toBe('0,0,0,0')
  })

  it('pokazuje średnią całego planu oddzielnie od archiwalnego celu konta bez oceny realizacji', async () => {
    const wrapper = await mountPage()

    const tile = wrapper.get('[data-testid="stats-tile-kcal"]')
    expect(tile.text()).toContain('1900')
    expect(tile.text()).not.toContain('2000')
    expect(wrapper.find('[data-testid="stats-status-kcal"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="stats-account-averages"]').text()).toContain('2000')
    expect(wrapper.get('[data-testid="stats-goal-legend"]').text()).toContain('odczyt archiwalny')
    expect(wrapper.get('[data-testid="stats-semantics"]').text()).toContain('cały plan')
    expect(wrapper.get('[data-testid="stats-days"]').text()).toContain('6 z 7')
  })

  it('zakładka makro pokazuje trzy kafelki i legendę składników', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="stats-tab-macros"]').trigger('click')

    expect(wrapper.find('[data-testid="stats-tile-protein_g"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="stats-tile-fat_g"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="stats-tile-carbs_g"]').exists()).toBe(true)
    // Cel tłuszczu nie jest ustawiony w podsumowaniu — kafelek mówi „brak celu".
    expect(wrapper.get('[data-testid="stats-tile-fat_g"]').text()).toContain('60 g')
    expect(wrapper.get('[data-testid="stats-account-averages"]').text()).toContain('brak celu')
  })

  it('trend średniej kroczącej rysuje się w układzie współrzędnych słupków', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="stats-tab-macros"]').trigger('click')

    const trend = wrapper.find('[data-testid="stats-macro-trend"]')
    expect(trend.exists()).toBe(true)
    // Nakładka nie ma własnego `<svg>` — inaczej miałaby własną skalę.
    expect(trend.element.tagName.toLowerCase()).toBe('g')
    // Dzień bez planu nie dostaje punktu trendu (luka nie wnosi zera).
    expect(wrapper.find('[data-testid="stats-macro-trend-marker-19.08.2026"]').exists()).toBe(false)
  })

  it('krótki zakres nie pokazuje trendu, ale mówi dlaczego', async () => {
    statsApi.fetchDailyStats.mockResolvedValue(
      response([day('2026-08-17', { kcal: '1800', goalKcal: '2000' })]),
    )
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="stats-tab-macros"]').trigger('click')

    expect(wrapper.find('[data-testid="stats-macro-trend"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Średnia krocząca pojawia się dla zakresu od 7 dni.')
  })

  it('niepełne dane dostają plakietkę z listą braków w tooltipie', async () => {
    statsApi.fetchDailyStats.mockResolvedValue(
      response([day('2026-08-17', { kcal: '1800', goalKcal: '2000', complete: false })], {
        avg: nutrition('1800', ['100', '60', '200'], false),
      }),
    )
    const wrapper = await mountPage()

    const badge = wrapper.get('[data-testid="stats-incomplete"]')
    expect(badge.text()).toContain('Niepełne dane')
    expect(badge.attributes('title')).toContain('Cebula: brak IG')
  })

  it('zakres bez zaplanowanych dni pokazuje stan pusty z akcją, nie zera', async () => {
    statsApi.fetchDailyStats.mockResolvedValue(response([day('2026-08-17'), day('2026-08-18')]))
    const wrapper = await mountPage()

    expect(wrapper.get('[data-testid="stats-empty"]').text()).toContain(
      'Brak zaplanowanych dni w tym zakresie',
    )
    expect(wrapper.find('[data-testid="stats-go-to-plan"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="stats-summary"]').exists()).toBe(false)
  })

  it('brak celu w zakresie mówi wprost, że statusów nie będzie', async () => {
    statsApi.fetchDailyStats.mockResolvedValue(
      response([day('2026-08-17', { kcal: '1800' }), day('2026-08-18', { kcal: '1900' })]),
    )
    const wrapper = await mountPage()

    expect(wrapper.find('[data-testid="stats-no-goal"]').exists()).toBe(true)
  })

  it('błąd zapytania nie udaje pustych statystyk', async () => {
    statsApi.fetchDailyStats.mockRejectedValue(new Error('padło'))
    const wrapper = await mountPage()
    await flushPromises()

    expect(wrapper.find('[data-testid="stats-fetch-error"]').exists()).toBe(true)
  })
  it('nie używa osobistych statusów ani wartości goal_progress jako średniej planu', async () => {
    const data = response(WEEK)
    data.summary.goal_progress.kcal = {
      value: '99999',
      target: '2000',
      delta: '97999',
      status: 'above',
    }
    data.days.forEach((entry) => {
      entry.status.kcal = 'above'
    })
    statsApi.fetchDailyStats.mockResolvedValue(data)
    const wrapper = await mountPage()
    expect(wrapper.get('[data-testid="stats-tile-kcal"]').text()).toContain('1900')
    expect(wrapper.get('[data-testid="stats-tile-kcal"]').text()).not.toContain('99999')
    expect(wrapper.text()).not.toContain('za dużo')
    expect(
      wrapper
        .findAll('[data-testid^="stats-kcal-chart-bar-"]')
        .every((bar) => bar.classes().includes('fill-primary')),
    ).toBe(true)
    expect(wrapper.get('[data-testid="stats-kcal-chart"] svg').attributes('aria-label')).toContain(
      'historyczny cel konta',
    )
  })

  it('historia celów konta jest osiągalna także w zakresie bez planu', async () => {
    statsApi.fetchDailyStats.mockResolvedValue(response([day('2030-01-01', { goalKcal: '2200' })]))
    const wrapper = await mountPage()
    expect(wrapper.find('[data-testid="stats-empty"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="stats-account-history"]').text()).toContain(
      'nie wyliczono średnich',
    )
    expect(wrapper.get('[data-testid="stats-goal-history"]').text()).toContain('2200')
    expect(wrapper.find('[data-testid="stats-account-averages"]').exists()).toBe(false)
  })
  it.each([
    {
      label: 'pusty plan',
      cached: response([day('2026-08-17', { goalKcal: '2200' })]),
      visible: 'stats-empty',
    },
    { label: 'plan z posiłkami', cached: response(WEEK), visible: 'stats-chart-kcal' },
  ])(
    'zachowuje potwierdzone dane i ujawnia błąd odświeżenia z ponowieniem: $label',
    async ({ cached, visible }) => {
      let failRefresh!: (error: Error) => void
      let finishRetry!: (data: DailyStats) => void
      const failedRefresh = new Promise<DailyStats>((_resolve, reject) => {
        failRefresh = reject
      })
      const pendingRetry = new Promise<DailyStats>((resolve) => {
        finishRetry = resolve
      })
      statsApi.fetchDailyStats
        .mockReset()
        .mockResolvedValueOnce(cached)
        .mockReturnValueOnce(failedRefresh)
        .mockReturnValueOnce(pendingRetry)
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      const wrapper = await mountPage('/statystyki', client)
      try {
        expect(wrapper.get(`[data-testid="${visible}"]`).isVisible()).toBe(true)
        expect(wrapper.findComponent(ErrorState).exists()).toBe(false)
        const refresh = client.refetchQueries({ queryKey: queryKeys.stats.all })
        await flushPromises()
        expect(statsApi.fetchDailyStats).toHaveBeenCalledTimes(2)
        expect(wrapper.get(`[data-testid="${visible}"]`).isVisible()).toBe(true)
        expect(wrapper.findComponent(ErrorState).exists()).toBe(false)
        failRefresh(new Error('odświeżenie nie powiodło się'))
        await refresh
        await flushPromises()
        const error = wrapper.getComponent(ErrorState)
        expect(error.get('[role="alert"]').text()).toContain('Nie udało się odświeżyć podsumowania')
        expect(error.text()).toContain('ostatnio odczytane dane')
        expect(wrapper.get(`[data-testid="${visible}"]`).isVisible()).toBe(true)
        expect(wrapper.find('[data-testid="stats-fetch-error"]').exists()).toBe(false)
        expect(wrapper.get('[data-testid="stats-account-history"]').isVisible()).toBe(true)
        const retry = error.get('button')
        expect(retry.attributes('disabled')).toBeUndefined()
        await retry.trigger('click')
        await flushPromises()
        expect(statsApi.fetchDailyStats).toHaveBeenCalledTimes(3)
        expect(retry.attributes('disabled')).toBeDefined()
        expect(wrapper.get(`[data-testid="${visible}"]`).isVisible()).toBe(true)
        finishRetry(response(WEEK))
        await flushPromises()
        expect(wrapper.findComponent(ErrorState).exists()).toBe(false)
        expect(wrapper.find('[data-testid="stats-empty"]').exists()).toBe(false)
        expect(wrapper.get('[data-testid="stats-tile-kcal"]').text()).toContain('1900')
        expect(wrapper.find('[data-testid="stats-status-kcal"]').exists()).toBe(false)
      } finally {
        wrapper.unmount()
        client.clear()
      }
    },
  )
})
