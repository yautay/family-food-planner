import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import type * as Planning from '@/api/planning'
import type * as Recipes from '@/api/recipes'
import { queryKeys } from '@/api/queryKeys'
import PlanDniaPage from './PlanDniaPage.vue'

const api = vi.hoisted(() => ({
  fetchPlanDays: vi.fn(),
  fetchMyProfiles: vi.fn(),
  planRecipe: vi.fn(),
  fetchRecipes: vi.fn(),
}))
vi.mock('@/api/planning', async (original) => ({
  ...(await original<typeof Planning>()),
  fetchPlanDays: api.fetchPlanDays,
  planRecipe: api.planRecipe,
}))
vi.mock('@/api/households', () => ({ fetchMyProfiles: api.fetchMyProfiles }))
vi.mock('@/api/recipes', async (original) => ({
  ...(await original<typeof Recipes>()),
  fetchRecipes: api.fetchRecipes,
}))
const nutrition = {
  kcal: '600',
  protein_g: '20',
  fat_g: '10',
  carbs_g: '50',
  fiber_g: '5',
  sugars_g: '2',
  glycemic_load: '3',
  complete: false,
  missing: ['Brak IG'],
}
const day = {
  id: 1,
  day: '2031-01-07',
  title: null,
  meals: [{ id: 2, name: 'Po spacerze', items: [], nutrition }],
  nutrition,
  goal_valid_from: '2030-01-01',
  goal_progress: { kcal: { target: '2000', delta: '-1400', status: 'low' } },
}
let wrapper: VueWrapper
let client: QueryClient
async function open(
  options: { realMeals?: boolean; realPanel?: boolean } = {},
): Promise<ReturnType<typeof createRouter>> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/plan-dnia/:date?', name: 'plan-dnia', component: PlanDniaPage }],
  })
  await router.push('/plan-dnia/2031-01-07?selectedDate=2031-01-07&from=2031-01-01&to=2031-01-31')
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  wrapper = mount(PlanDniaPage, {
    attachTo: document.body,
    global: {
      plugins: [router, [VueQueryPlugin, { queryClient: client }]],
      stubs: {
        RecipePlanningPanel: !options.realPanel,
        MealCard: options.realMeals
          ? false
          : {
              props: ['meal'],
              template: '<article data-testid="meal-test">{{ meal.name }}</article>',
            },
      },
    },
  })
  await flushPromises()
  return router
}
beforeEach(() => {
  vi.clearAllMocks()
  api.fetchPlanDays.mockResolvedValue({ items: [day], total: 1 })
  api.fetchMyProfiles.mockResolvedValue({ items: [] })
})
afterEach(() => {
  wrapper?.unmount()
  client?.clear()
  document.body.innerHTML = ''
})

describe('Plan dnia UX03', () => {
  it('po błędzie profili ponawia ich pobranie z drawera i odblokowuje podział po sukcesie', async () => {
    const item = {
      id: 3,
      recipe_id: 9,
      recipe_name: 'Zupa',
      recipe_photo_thumb_url: null,
      product_id: null,
      product_name: null,
      amount: null,
      amount_unit: null,
      servings: '1',
      servings_split: [],
      position: 0,
      nutrition,
    }
    api.fetchPlanDays.mockResolvedValue({
      items: [
        {
          ...day,
          meals: [{ ...day.meals[0], kcal_status: null, kcal_target: null, items: [item] }],
        },
      ],
      total: 1,
    })
    api.fetchMyProfiles.mockRejectedValueOnce(new Error('Pobranie profili wyczerpało próby'))
    await open({ realMeals: true })
    expect(api.fetchMyProfiles).toHaveBeenCalledTimes(1)
    await wrapper.get('[data-testid="plan-item-split-open-3"]').trigger('click')
    expect(wrapper.get('[data-testid="servings-split-drawer"]').text()).toContain(
      'Nie udało się pobrać profili',
    )
    expect(wrapper.get<HTMLButtonElement>('[data-testid="split-apply"]').element.disabled).toBe(
      true,
    )
    let finish!: (result: {
      items: { id: number; name: string; default_multiplier: string; is_active: boolean }[]
    }) => void
    api.fetchMyProfiles.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    await wrapper.get('[data-testid="split-profiles-retry"]').trigger('click')
    await flushPromises()
    expect(api.fetchMyProfiles).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[data-testid="servings-split-drawer"]').text()).toContain(
      'Pobieranie profili',
    )
    expect(wrapper.get<HTMLButtonElement>('[data-testid="split-apply"]').element.disabled).toBe(
      true,
    )
    finish({
      items: [{ id: 1, name: 'Osoba z rodziny', default_multiplier: '1.10', is_active: true }],
    })
    await flushPromises()
    expect(wrapper.get('[data-testid="servings-split-drawer"]').text()).not.toContain(
      'Nie udało się pobrać profili',
    )
    expect(wrapper.get<HTMLInputElement>('[data-testid="split-input-1"]').element.value).toBe(
      '1,10',
    )
    expect(wrapper.get<HTMLButtonElement>('[data-testid="split-apply"]').element.disabled).toBe(
      false,
    )
  })

  it('po wyborze innej daty i zapisie pokazuje docelowy dzień oraz zachowane potwierdzenie', async () => {
    const date = '2031-01-14'
    const recipe = { id: 9, name: 'Zupa na wtorek', nutrition }
    const savedDay = {
      ...day,
      id: 3,
      day: date,
      meals: [
        {
          ...day.meals[0],
          id: 4,
          name: 'Po spacerze we wtorek',
          items: [{ id: 5, recipe_id: recipe.id, recipe_name: recipe.name, nutrition }],
        },
      ],
    }
    let saved = false
    api.fetchPlanDays.mockImplementation((from: string, to: string) => {
      const items = [day, ...(saved ? [savedDay] : [])].filter(
        (entry) => from <= entry.day && entry.day <= to,
      )
      return Promise.resolve({ items, total: items.length })
    })
    api.fetchRecipes.mockResolvedValue({ items: [recipe], total: 1 })
    api.planRecipe.mockImplementation(() => {
      saved = true
      return Promise.resolve({ day: savedDay, meal_id: 4, item_id: 5 })
    })
    const router = await open({ realPanel: true })
    await wrapper.get('[data-testid="plan-add-recipe"]').trigger('click')
    await flushPromises()
    const element = <T extends HTMLElement = HTMLElement>(id: string): T => {
      const found = document.querySelector<T>(`[data-testid="${id}"]`)
      if (!found) throw new Error(`Brak elementu ${id}`)
      return found
    }
    for (const [id, value] of [
      ['planning-date', date],
      ['planning-meal-name', 'Po spacerze we wtorek'],
      ['recipe-picker-input', 'Zupa na wtorek'],
    ]) {
      const field = element<HTMLInputElement>(id!)
      field.focus()
      field.value = value!
      field.dispatchEvent(new Event('input', { bubbles: true }))
      await flushPromises()
    }
    await vi.waitFor(() =>
      expect(document.querySelector('[data-testid="recipe-picker-option-9"]')).not.toBeNull(),
    )
    element('recipe-picker-option-9').click()
    await flushPromises()
    element('recipe-planning-submit').click()
    await vi.waitFor(() => expect(router.currentRoute.value.params.date).toBe(date))
    await flushPromises()
    expect(api.planRecipe).toHaveBeenCalledExactlyOnceWith(date, {
      recipe_id: 9,
      new_meal_name: 'Po spacerze we wtorek',
      servings: '1',
      servings_split: [],
    })
    expect(wrapper.get('[data-testid="plan-date"]').text()).toBe(date)
    expect(wrapper.get('[data-testid="meal-test"]').text()).toContain('Po spacerze we wtorek')
    expect(wrapper.get('[data-testid="plan-success"]').text()).toBe('Danie dodane do planu.')
  })
  it('pokazuje jedzenie przed małym Cały plan, bez porównania rodzinnej sumy do celu konta', async () => {
    await open()
    const html = wrapper.html()
    expect(html.indexOf('meal-test')).toBeLessThan(html.indexOf('plan-summary'))
    expect(wrapper.get('[data-testid="plan-summary"]').text()).toContain('Cały plan')
    expect(wrapper.get('[data-testid="plan-tile-kcal"]').text()).toContain('600 kcal')
    expect(wrapper.get('[data-testid="plan-summary"]').text()).not.toContain('2000')
    expect(wrapper.get('[data-testid="plan-summary"]').text()).not.toContain('1400')
    expect(wrapper.get('[data-testid="plan-incomplete"]').text()).toContain('Brak IG')
  })
  it('pierwsze ładowanie i błąd odczytu nie udają pustego dnia; retry może potwierdzić pusty dzień', async () => {
    let reject!: (reason: Error) => void
    api.fetchPlanDays.mockImplementationOnce(
      () =>
        new Promise((_resolve, failure) => {
          reject = failure
        }),
    )
    await open()
    expect(wrapper.find('[data-testid="plan-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="plan-empty"]').exists()).toBe(false)
    reject(new Error('Odczyt nie powiódł się'))
    await flushPromises()
    expect(wrapper.find('[data-testid="plan-load-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="plan-empty"]').exists()).toBe(false)
    api.fetchPlanDays.mockResolvedValue({ items: [], total: 0 })
    await wrapper.get('[data-testid="plan-load-error"] button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="plan-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="plan-add-recipe"]').exists()).toBe(true)
  })
  it('błąd refetch zachowuje nowsze dane cache zamiast wyzerować plan', async () => {
    await open()
    api.fetchPlanDays.mockRejectedValue(new Error('Brak sieci'))
    const key = queryKeys.planDays.range('2031-01-06', '2031-01-12')
    client.setQueryData(key, {
      items: [{ ...day, meals: [{ ...day.meals[0], name: 'Nowszy zapis w cache' }] }],
      total: 1,
    })
    await client.invalidateQueries({ queryKey: queryKeys.planDays.all })
    await flushPromises()
    expect(wrapper.find('[data-testid="plan-refetch-error"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="meal-test"]').text()).toContain('Nowszy zapis w cache')
    expect(wrapper.find('[data-testid="plan-empty"]').exists()).toBe(false)
  })
  it('pasek dat zachowuje kontrakt selectedDate/from/to i wskazuje bieżący dzień', async () => {
    const router = await open()
    expect(wrapper.get('[data-testid="week-day-2031-01-07"]').attributes('aria-current')).toBe(
      'date',
    )
    await wrapper.get('[data-testid="plan-next-day"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.params.date).toBe('2031-01-08')
    expect(router.currentRoute.value.query).toMatchObject({
      selectedDate: '2031-01-08',
      from: '2031-01-01',
      to: '2031-01-31',
    })
  })
})
