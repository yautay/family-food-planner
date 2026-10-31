import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import type { PropType } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ApiError } from '@/api/client'
import type * as Planning from '@/api/planning'
import type { PlanDay, PlanMeal, PlanItem } from '@/api/planning'
import type { RecipeSummary } from '@/api/recipes'
import type * as Recipes from '@/api/recipes'
import { queryKeys } from '@/api/queryKeys'
import RecipePlanningPanel from './RecipePlanningPanel.vue'

const api = vi.hoisted(() => ({
  fetchPlanDays: vi.fn(),
  planRecipe: vi.fn(),
  updateItem: vi.fn(),
  fetchMyProfiles: vi.fn(),
  fetchRecipes: vi.fn(),
  createRecipe: vi.fn(),
}))
vi.mock('@/api/planning', async (original) => ({ ...(await original<typeof Planning>()), ...api }))
vi.mock('@/api/households', () => ({ fetchMyProfiles: api.fetchMyProfiles }))
vi.mock('@/api/recipes', async (original) => ({
  ...(await original<typeof Recipes>()),
  fetchRecipes: api.fetchRecipes,
  createRecipe: api.createRecipe,
}))
const nutrition = {
  kcal: '200',
  protein_g: '5',
  fat_g: '10',
  carbs_g: '20',
  fiber_g: '1',
  sugars_g: '1',
  glycemic_load: '2',
  complete: true,
  missing: [],
}
const recipe: RecipeSummary = {
  id: 2,
  name: 'Nowe danie',
  nutrition,
  scope: 'private',
  owner_user_id: 1,
  base_servings: 1,
  prep_time_min: null,
  difficulty: null,
  is_archived: false,
  photo_url: null,
  photo_thumb_url: null,
  tags: [],
  avg_rating: null,
  ratings_count: 0,
  my_rating: null,
  created_at: '2031-01-07T12:00:00Z',
  updated_at: '2031-01-07T12:00:00Z',
}
const item: PlanItem = {
  id: 5,
  recipe_id: 1,
  recipe_name: 'Poprzednie danie',
  recipe_photo_thumb_url: null,
  product_id: null,
  product_name: null,
  amount: null,
  amount_unit: null,
  servings: '2.20',
  position: 4,
  servings_split: [
    { member_profile_id: 1, member_name: 'Pierwsza osoba', multiplier: '1.10' },
    { member_profile_id: 2, member_name: 'Historyczna osoba', multiplier: '1.10' },
  ],
  nutrition,
}
const meal: PlanMeal = {
  id: 3,
  name: 'Późny obiad po spacerze',
  items: [item],
  nutrition,
  position: 0,
  kcal_target: null,
  kcal_status: null,
}
const metric = { value: '200', target: null, delta: null, status: null }
const day: PlanDay = {
  id: 7,
  day: '2031-01-07',
  meals: [meal],
  nutrition,
  title: null,
  scope: 'private',
  owner_user_id: 1,
  goal_progress: { kcal: metric, protein_g: metric, fat_g: metric, carbs_g: metric },
  goal_valid_from: null,
  created_at: null,
  updated_at: null,
}
const profiles = [1, 2, 3].map((id) => ({
  id,
  name: `Osoba ${id}`,
  default_multiplier: '1.10',
  is_active: id !== 2,
}))
let wrapper: VueWrapper | undefined
let client: QueryClient
const picker = defineComponent({
  props: { modelValue: { type: Object as PropType<RecipeSummary | null>, default: null } },
  emits: ['update:modelValue'],
  setup: () => ({ recipe }),
  template:
    '<button type="button" data-testid="choose-recipe" @click="$emit(\'update:modelValue\', recipe)">Wybierz danie</button>',
})

function el<T extends HTMLElement = HTMLElement>(id: string): T {
  const element = document.querySelector<T>(`[data-testid="${id}"]`)
  if (!element) throw new Error(`Brak ${id}`)
  return element
}
async function input(id: string, value: string): Promise<void> {
  const field = el<HTMLInputElement>(id)
  field.value = value
  field.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
}
async function open(extra: Record<string, unknown> = {}, realPicker = false): Promise<void> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ name: 'plan-dnia', path: '/plan-dnia/:date?', component: { template: '<div />' } }],
  })
  await router.push('/plan-dnia/2031-01-07')
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  wrapper = mount(RecipePlanningPanel, {
    attachTo: document.body,
    props: { open: false, recipe, date: '2031-01-07', ...extra },
    global: {
      plugins: [router, [VueQueryPlugin, { queryClient: client }]],
      stubs: realPicker ? {} : { RecipePicker: picker },
    },
  })
  await wrapper.setProps({ open: true })
  await flushPromises()
}
async function submit(): Promise<void> {
  el('recipe-planning-submit').click()
  await flushPromises()
}
beforeEach(() => {
  vi.clearAllMocks()
  api.fetchPlanDays.mockResolvedValue({ items: [day], total: 1 })
  api.fetchMyProfiles.mockResolvedValue({ items: profiles, total: 3 })
  api.planRecipe.mockResolvedValue({
    day: { ...day, meals: [{ ...meal, items: [{ ...item, recipe_id: recipe.id }] }] },
    meal_id: meal.id,
    item_id: item.id,
  })
  api.updateItem.mockResolvedValue({
    ...day,
    meals: [{ ...meal, items: [{ ...item, recipe_id: recipe.id }] }],
  })
  api.fetchRecipes.mockResolvedValue({ items: [], total: 0 })
  api.createRecipe.mockResolvedValue(recipe)
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  client?.clear()
  document.body.innerHTML = ''
})

describe('RecipePlanningPanel — potwierdzony zapis i rzeczywisty modal', () => {
  it('zapisuje nowy posiłek jednym POST i emituje realne identyfikatory', async () => {
    await open()
    await input('planning-meal-name', 'Późny obiad')
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    await submit()
    expect(api.planRecipe).toHaveBeenCalledExactlyOnceWith('2031-01-07', {
      new_meal_name: 'Późny obiad',
      recipe_id: 2,
      servings: '1',
      servings_split: [],
    })
    expect(wrapper!.emitted('saved')?.[0]?.[0]).toMatchObject({
      mealId: 3,
      itemId: 5,
      mode: 'add',
      day: { id: 7 },
    })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.planDays.all })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.stats.all })
  })

  it('zapisuje rodzinne 1,1+1,1+1,1 jako 3,3, zero pomija, a niepoprawny tekst blokuje bez BigInt crash', async () => {
    await open({ meal })
    el<HTMLInputElement>('planning-family').click()
    await flushPromises()
    for (const id of [1, 2, 3]) await input(`planning-split-${id}`, '1,1')
    expect(el('planning-total').textContent).toContain('3,3')
    await input('planning-split-3', '1e3')
    expect(el<HTMLButtonElement>('recipe-planning-submit').disabled).toBe(true)
    await input('planning-split-3', '0')
    expect(el('planning-total').textContent).toContain('2,2')
    await submit()
    expect(api.planRecipe.mock.calls[0]?.[1]).toMatchObject({
      servings: '2.2',
      servings_split: [
        { member_profile_id: 1, multiplier: '1.1' },
        { member_profile_id: 2, multiplier: '1.1' },
      ],
    })
  })

  it('zamienia tylko recipe_id, zachowując częściowy historyczny split i brak trzeciej osoby', async () => {
    await open({ meal, replaceItem: item })
    expect(el('planning-total').textContent).toContain('2,2')
    expect(el<HTMLInputElement>('planning-split-3').value).toBe('0')
    expect(el<HTMLInputElement>('planning-date').disabled).toBe(true)
    await submit()
    expect(api.updateItem).toHaveBeenCalledExactlyOnceWith(5, { recipe_id: 2 })
    expect(api.planRecipe).not.toHaveBeenCalled()
    expect(wrapper!.emitted('saved')?.[0]?.[0]).toMatchObject({
      mealId: 3,
      itemId: 5,
      mode: 'replace',
    })
  })

  it('jawna edycja porcji w zamianie wysyła zgodną sumę i cały podział razem', async () => {
    await open({ meal, replaceItem: item })
    await input('planning-split-2', '0')
    await submit()
    expect(api.updateItem).toHaveBeenCalledExactlyOnceWith(5, {
      recipe_id: 2,
      servings: '1.10',
      servings_split: [{ member_profile_id: 1, multiplier: '1.10' }],
    })
  })

  it('wszystkie zera i maksima blokują zapis; bez profili można zapisać samą liczbę', async () => {
    await open({ meal })
    el<HTMLInputElement>('planning-family').click()
    await flushPromises()
    for (const id of [1, 2, 3]) await input(`planning-split-${id}`, '0')
    expect(el<HTMLButtonElement>('recipe-planning-submit').disabled).toBe(true)
    await input('planning-split-1', '100')
    expect(el<HTMLButtonElement>('recipe-planning-submit').disabled).toBe(true)
    el<HTMLInputElement>('planning-family').click()
    await flushPromises()
    await input('planning-servings', '10000')
    expect(el<HTMLButtonElement>('recipe-planning-submit').disabled).toBe(true)
    await input('planning-servings', '2,5')
    await submit()
    expect(api.planRecipe.mock.calls[0]?.[1]).toMatchObject({ servings: '2.5', servings_split: [] })
  })

  it('brak profili i błąd profili to odrębne stany, bez blokowania samej liczby porcji', async () => {
    api.fetchMyProfiles.mockRejectedValue(
      new ApiError(500, { code: 'error', message: 'Błąd', details: {} }),
    )
    await open({ meal })
    expect(el('planning-profiles-error').textContent).toContain('Nie udało się pobrać')
    expect(document.querySelector('[data-testid="planning-no-profiles"]')).toBeNull()
    expect(el<HTMLButtonElement>('recipe-planning-submit').disabled).toBe(false)
    api.fetchMyProfiles.mockResolvedValue({ items: [], total: 0 })
    await client.invalidateQueries({ queryKey: queryKeys.households.profiles })
    el<HTMLInputElement>('planning-family').click()
    await flushPromises()
    expect(el('planning-no-profiles').textContent).toContain('samą liczbę porcji')
  })

  it('API422 zostawia szkic i przenosi fokus tylko na błąd API; retry zachowuje kontekst', async () => {
    api.planRecipe.mockRejectedValueOnce(
      new ApiError(422, { code: 'validation_error', message: 'Niepoprawny podział', details: {} }),
    )
    await open()
    await input('planning-meal-name', 'Obiad po spacerze')
    await submit()
    expect(el<HTMLInputElement>('planning-meal-name').value).toBe('Obiad po spacerze')
    expect(el('recipe-planning-error').textContent).toContain('Niepoprawny podział')
    expect(document.activeElement).toBe(el('recipe-planning-error'))
    expect(wrapper!.emitted('saved')).toBeUndefined()
    await submit()
    expect(api.planRecipe).toHaveBeenCalledTimes(2)
    expect(wrapper!.emitted('saved')).toHaveLength(1)
  })

  it('niepewna utrata odpowiedzi odczytuje realny plan, nie potwierdza podobnego wiersza i nie wysyła ponownie POST', async () => {
    api.planRecipe.mockRejectedValue(
      new ApiError(0, { code: 'network_error', message: 'Brak odpowiedzi', details: {} }),
    )
    await open({ meal })
    await submit()
    expect(el('planning-uncertain').textContent).toContain('Rzeczywisty plan')
    expect(api.fetchPlanDays.mock.calls.length).toBeGreaterThan(1)
    expect(wrapper!.emitted('saved')).toBeUndefined()
    expect(el<HTMLButtonElement>('recipe-planning-submit').disabled).toBe(true)
    await submit()
    expect(api.planRecipe).toHaveBeenCalledTimes(1)
  })

  it('pending blokuje podwójny zapis i zamknięcie; walidacja na żywo nie kradnie fokusu', async () => {
    api.planRecipe.mockImplementation(() => new Promise(() => {}))
    await open()
    const field = el<HTMLInputElement>('planning-meal-name')
    field.focus()
    await input('planning-meal-name', '')
    expect(document.activeElement).toBe(field)
    await input('planning-meal-name', 'Obiad')
    const button = el<HTMLButtonElement>('recipe-planning-submit')
    button.click()
    button.click()
    await flushPromises()
    expect(api.planRecipe).toHaveBeenCalledTimes(1)
    expect(el<HTMLButtonElement>('recipe-planning-cancel').disabled).toBe(true)
    expect(el<HTMLButtonElement>('recipe-planning-close').disabled).toBe(true)
  })

  it('zmiana daty resetuje posiłek, a błąd bez cache nie udaje pustego planu', async () => {
    await open({ meal })
    api.fetchPlanDays.mockRejectedValue(new Error('Brak odczytu'))
    await input('planning-date', '2031-01-08')
    expect(el<HTMLSelectElement>('planning-meal').value).toBe('new')
    expect(el('planning-day-error').textContent).toContain('Nie wiemy, czy ten dzień jest pusty')
    expect(el<HTMLButtonElement>('recipe-planning-submit').disabled).toBe(true)
  })

  it('niespójne propsy zamiany nie mogą wysłać mutacji', async () => {
    await open({ meal: { ...meal, items: [] }, replaceItem: item })
    expect(el('recipe-planning-validation').textContent).toContain('niespójny')
    await submit()
    expect(api.updateItem).not.toHaveBeenCalled()
  })

  it('realny picker tworzy przepis własnym formularzem, zachowując datę i szkic bez wysłania planu', async () => {
    await open({ recipe: null, meal }, true)
    el<HTMLInputElement>('recipe-picker-input').focus()
    await input('recipe-picker-input', 'Nowe danie')
    await vi.waitFor(() =>
      expect(document.querySelector('[data-testid="recipe-picker-create"]')).not.toBeNull(),
    )
    expect(api.fetchRecipes).toHaveBeenCalledWith({ limit: 8, offset: 0, q: 'Nowe danie' })
    el('recipe-picker-create').click()
    await flushPromises()
    expect(document.querySelectorAll('form form')).toHaveLength(0)
    el('recipe-create-submit').click()
    await flushPromises()
    expect(api.createRecipe).toHaveBeenCalledTimes(1)
    expect(api.planRecipe).not.toHaveBeenCalled()
    expect(el('recipe-picker-selected').textContent).toContain(recipe.name)
    expect(el<HTMLInputElement>('planning-date').value).toBe('2031-01-07')
    await submit()
    expect(api.planRecipe).toHaveBeenCalledTimes(1)
  })

  it('Escape zamyka panel, trap zatrzymuje Tab i Reka oddaje fokus wywołującemu', async () => {
    const opener = document.createElement('button')
    opener.textContent = 'Zaplanuj'
    document.body.append(opener)
    opener.focus()
    await open({ meal })
    const dialog = el('recipe-planning')
    opener.focus()
    expect(dialog.contains(document.activeElement)).toBe(true)
    document.activeElement?.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }),
    )
    await flushPromises()
    expect(wrapper!.emitted('close')).toHaveLength(1)
    await wrapper!.setProps({ open: false })
    await vi.waitFor(() => expect(document.activeElement).toBe(opener))
  })
})
