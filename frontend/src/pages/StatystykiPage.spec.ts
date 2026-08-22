import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import StatystykiPage from './StatystykiPage.vue'
import type { DailyStats, StatsDay } from '@/api/stats'

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

async function mountPage() {
  setActivePinia(createPinia())
  const wrapper = mount(StatystykiPage, {
    global: {
      // `retry: false` — aplikacja ponawia raz (main.ts), a test ma sprawdzać
      // komunikat błędu, nie czekać na politykę ponowień.
      plugins: [
        [VueQueryPlugin, { queryClientConfig: { defaultOptions: { queries: { retry: false } } } }],
      ],
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

    expect(wrapper.get('[data-testid="stats-tab-kcal"]').attributes('aria-selected')).toBe('true')
    expect(wrapper.find('[data-testid="stats-chart-kcal"]').exists()).toBe(true)

    await wrapper.get('[data-testid="stats-tab-macros"]').trigger('click')

    expect(wrapper.find('[data-testid="stats-chart-macros"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="stats-tab-macros"]').attributes('aria-selected')).toBe('true')
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

  it('podsumowanie pokazuje trio wartość/cel/delta + status słowny', async () => {
    const wrapper = await mountPage()

    const tile = wrapper.get('[data-testid="stats-tile-kcal"]')
    expect(tile.text()).toContain('1900')
    expect(tile.text()).toContain('2000')
    expect(wrapper.get('[data-testid="stats-status-kcal"]').text()).toContain('prawidłowo')
    expect(wrapper.get('[data-testid="stats-days"]').text()).toContain('6 z 7')
  })

  it('zakładka makro pokazuje trzy kafelki i legendę składników', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="stats-tab-macros"]').trigger('click')

    expect(wrapper.find('[data-testid="stats-tile-protein_g"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="stats-tile-fat_g"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="stats-tile-carbs_g"]').exists()).toBe(true)
    // Cel tłuszczu nie jest ustawiony w podsumowaniu — kafelek mówi „brak celu".
    expect(wrapper.get('[data-testid="stats-tile-fat_g"]').text()).toContain('brak celu')
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
})
