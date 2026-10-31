import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import type { CurrentUser } from '@/api/auth'
import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import type { RecipeDetail, RatingResponse } from '@/api/recipes'
import RecipePlanningPanel from '@/components/domain/planning/RecipePlanningPanel.vue'
import { useAuthStore } from '@/stores/auth'
import { captureSessionGeneration } from '@/lib/sessionGeneration'
import PrzepisSzczegolPage from './PrzepisSzczegolPage.vue'

const api = vi.hoisted(() => ({
  fetchRecipe: vi.fn(),
  deleteRecipe: vi.fn(),
  rateRecipe: vi.fn(),
  copyRecipe: vi.fn(),
  archiveRecipe: vi.fn(),
  unarchiveRecipe: vi.fn(),
}))
vi.mock('@/api/recipes', () => api)

function detail(overrides: Partial<RecipeDetail> = {}): RecipeDetail {
  return {
    id: 9,
    name: 'Wspólny żurek',
    scope: 'global',
    owner_user_id: 1,
    base_servings: 2,
    prep_time_min: null,
    difficulty: null,
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
    created_at: '2026-10-03T10:00:00Z',
    updated_at: '2026-10-03T10:00:00Z',
    instructions: 'Ugotuj warzywa.\nPodaj gorące.',
    servings: '1',
    ingredients: [
      {
        id: 41,
        product_id: 8,
        product_name: 'Pełnoziarnista mąka żytnia',
        amount: '200',
        amount_unit: 'g',
        measure_kind: 'mass',
        display_qty: null,
        display_unit: null,
        scaled_amount: '100',
        note: 'przesiana',
        position: 0,
      },
    ],
    ...overrides,
  }
}
function account(id: number, role: CurrentUser['role']): CurrentUser {
  return {
    id,
    email: `u${id}@example.com`,
    display_name: `Użytkownik ${id}`,
    role,
    household: null,
    ui_settings: {},
  } as CurrentUser
}
let wrapper: VueWrapper
let client: QueryClient
let router: Router
async function render(
  role: CurrentUser['role'] = 'user',
  userId = 1,
  recipe = detail(),
  url = '/przepisy/9',
) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().setUser(account(userId, role), captureSessionGeneration())
  client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/przepisy', name: 'przepisy', component: { template: '<div />' } },
      { path: '/przepisy/:id', name: 'przepis-szczegol', component: { template: '<div />' } },
      { path: '/przepisy/:id/edytuj', name: 'przepis-edycja', component: { template: '<div />' } },
      { path: '/plan-dnia/:date', name: 'plan-dnia', component: { template: '<div />' } },
    ],
  })
  api.fetchRecipe.mockResolvedValueOnce(recipe)
  await router.push(url)
  wrapper = mount(PrzepisSzczegolPage, {
    global: {
      plugins: [pinia, router, [VueQueryPlugin, { queryClient: client }]],
      stubs: { RecipePlanningPanel: { props: ['open', 'recipe', 'date'], template: '<div />' } },
    },
  })
  await flushPromises()
  return wrapper
}
beforeEach(() => {
  vi.resetAllMocks()
})
afterEach(() => {
  wrapper?.unmount()
  client?.clear()
})

describe('PrzepisSzczegolPage — scope i istniejące działania', () => {
  it('zdegradowany właściciel globalnego przepisu może planować i kopiować, bez zarządzania i toggle serca', async () => {
    await render('user', 1, detail({ tags: [{ id: 7, name: 'ulubione', is_system: true }] }))
    expect(wrapper.find('[data-testid="recipe-edit"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="recipe-delete"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="recipe-archive"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="recipe-copy"]').text()).toBe('Kopiuj do mojej rodziny')
    expect(wrapper.get('[data-testid="recipe-plan"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('[data-testid="recipe-scope-badge"]').text()).toContain('Dla wszystkich')
    expect(wrapper.get('[data-testid="recipe-favorite-tag"]').element.tagName).toBe('P')
    expect(wrapper.get('[data-testid="recipe-read-only"]').text()).toContain('administrator')
  })

  it('ADMIN ma edycję, usunięcie i archiwizację', async () => {
    await render('admin', 2)
    expect(wrapper.get('[data-testid="recipe-edit"]').attributes('href')).toBe('/przepisy/9/edytuj')
    expect(wrapper.find('[data-testid="recipe-delete"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="recipe-archive"]').exists()).toBe(true)
  })

  it('archiwalny przepis ma Przywróć i nadal pozwala planować zgodnie z API', async () => {
    await render('admin', 2, detail({ is_archived: true }))
    expect(wrapper.find('[data-testid="recipe-archive"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="recipe-unarchive"]').text()).toBe('Przywróć z archiwum')
    expect(wrapper.get('[data-testid="recipe-plan"]').attributes('disabled')).toBeUndefined()
  })

  it('własny rodzinny: edycja i usunięcie bez zbędnego kopiowania', async () => {
    await render('user', 1, detail({ scope: 'household' }))
    expect(wrapper.find('[data-testid="recipe-edit"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="recipe-delete"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="recipe-copy"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="recipe-archive"]').exists()).toBe(false)
  })

  it('członek rodziny może edytować cudzy rodzinny przepis, lecz nie usuwać', async () => {
    await render('user', 2, detail({ scope: 'household' }))
    expect(wrapper.find('[data-testid="recipe-edit"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="recipe-delete"]').exists()).toBe(false)
  })

  it('kopia zachowuje query i otrzymuje nowe rzeczywiste ID dopiero po odpowiedzi API', async () => {
    await render('user', 5, detail(), '/przepisy/9?q=zupa&selectedDate=2031-04-09')
    let finish!: (value: RecipeDetail) => void
    api.copyRecipe.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve
      }),
    )
    await wrapper.get('[data-testid="recipe-copy"]').trigger('click')
    await flushPromises()
    expect(api.copyRecipe).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[data-testid="recipe-copy"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="recipe-success"]').exists()).toBe(false)
    expect(router.currentRoute.value.params.id).toBe('9')
    finish(detail({ id: 77, scope: 'household' }))
    await flushPromises()
    expect(router.currentRoute.value.params.id).toBe('77')
    expect(router.currentRoute.value.query).toEqual({ q: 'zupa', selectedDate: '2031-04-09' })
    expect(wrapper.get('[data-testid="recipe-success"]').text()).toContain('kopię')
  })

  it('archiwizacja unieważnia przepisy i ogłasza potwierdzony stan', async () => {
    api.archiveRecipe.mockResolvedValue(detail({ is_archived: true }))
    await render('admin', 2)
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    await wrapper.get('[data-testid="recipe-archive"]').trigger('click')
    await flushPromises()
    expect(api.archiveRecipe).toHaveBeenCalledWith(9)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.recipes.all })
    expect(wrapper.get('[data-testid="recipe-success"]').text()).toContain('zarchiwizowany')
  })

  it('ocena ma natywne radio, pending oraz błąd bez fikcyjnego sukcesu', async () => {
    await render()
    api.rateRecipe.mockRejectedValue(
      new ApiError(422, { code: 'validation', message: 'Nie zapisano oceny.', details: {} }),
    )
    await wrapper.get('[data-testid="recipe-rate-4"]').setValue()
    await flushPromises()
    expect(api.rateRecipe).toHaveBeenCalledWith(9, 4)
    expect(wrapper.get('[data-testid="recipe-rate-4"]').attributes('type')).toBe('radio')
    expect(wrapper.get('[data-testid="recipe-action-error"]').text()).toBe('Nie zapisano oceny.')
    expect((wrapper.get('[data-testid="recipe-rate-4"]').element as HTMLInputElement).checked).toBe(
      false,
    )
    expect(wrapper.find('[data-testid="recipe-success"]').exists()).toBe(false)
  })

  it('ocena w toku blokuje kolejną mutację i pokazuje sukces dopiero po odpowiedzi', async () => {
    await render()
    let finish!: (value: RatingResponse) => void
    api.rateRecipe.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve
      }),
    )
    api.fetchRecipe.mockResolvedValueOnce(
      detail({ my_rating: 4, avg_rating: '4', ratings_count: 1 }),
    )
    await wrapper.get('[data-testid="recipe-rate-4"]').setValue()
    await flushPromises()
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="recipe-success"]').exists()).toBe(false)
    finish({ my_rating: 4, avg_rating: '4', ratings_count: 1 })
    await flushPromises()
    expect(wrapper.get('[data-testid="recipe-success"]').text()).toContain('Ocena została zapisana')
    expect(wrapper.get('fieldset').attributes('disabled')).toBeUndefined()
    expect((wrapper.get('[data-testid="recipe-rate-4"]').element as HTMLInputElement).checked).toBe(
      true,
    )
  })

  it('usunięcie wymaga potwierdzenia i zachowuje czytelną listę użyć z 409', async () => {
    await render('admin', 2)
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    await wrapper.get('[data-testid="recipe-delete"]').trigger('click')
    expect(api.deleteRecipe).not.toHaveBeenCalled()
    api.deleteRecipe.mockRejectedValue(
      new ApiError(409, {
        code: 'conflict',
        message: 'Przepis jest używany.',
        details: {
          used_in: [{ type: 'plan_day', id: 4, name: '2031-04-09 — Wspólna kolacja' }],
        },
      }),
    )
    await wrapper.get('[data-testid="recipe-delete"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="recipe-used-in"]').text()).toContain(
      '2031-04-09 — Wspólna kolacja',
    )
    expect(wrapper.get('[data-testid="recipe-name"]').text()).toBe('Wspólny żurek')
    confirm.mockRestore()
  })
})

describe('PrzepisSzczegolPage — odczyt, skalowanie i planowanie', () => {
  it('Wróć korzysta z historii bez równoległego push RouterLink i zachowuje link', async () => {
    await render('user', 1, detail(), '/przepisy/9?q=zupa')
    Object.defineProperty(router.options.history, 'state', {
      value: { back: '/przepisy?q=zupa' },
      configurable: true,
    })
    const previous = vi.spyOn(router, 'back').mockImplementation(() => {})
    const push = vi.spyOn(router, 'push')
    expect(wrapper.get('[data-testid="recipe-back"]').attributes('href')).toBe('/przepisy?q=zupa')
    wrapper
      .get('[data-testid="recipe-back"]')
      .element.dispatchEvent(new MouseEvent('click', { button: 0, cancelable: true }))
    await flushPromises()
    expect(previous).toHaveBeenCalledOnce()
    expect(push).not.toHaveBeenCalled()
  })
  it('składniki i przygotowanie są równocześnie w DOM, pełne nazwy i zdjęcie pozostają dostępne', async () => {
    const name =
      'Pełnoziarnista zapiekanka z pieczoną papryką, cukinią, serem i delikatnymi świeżymi ziołami'
    await render('user', 1, detail({ name, photo_url: '/uploads/recipes/test.jpg' }))
    expect(wrapper.get('[data-testid="recipe-ingredients"]').text()).toContain('mąka żytnia')
    expect(wrapper.get('[data-testid="recipe-instructions"]').text()).toContain('Ugotuj warzywa')
    expect(wrapper.get('[data-testid="recipe-name"]').text()).toBe(name)
    expect(wrapper.get('img').attributes('src')).toBe('/uploads/recipes/test.jpg')
    await wrapper.get('img').trigger('error')
    expect(wrapper.find('[data-testid="recipe-image-fallback"]').exists()).toBe(true)
    expect(wrapper.find('[role="tab"]').exists()).toBe(false)
  })

  it('skalowanie przekazuje string i wyświetla ilości oraz wartości policzone przez serwer', async () => {
    await render()
    api.fetchRecipe.mockResolvedValueOnce(
      detail({
        servings: '1.5',
        ingredients: [{ ...detail().ingredients[0]!, scaled_amount: '150' }],
        nutrition: { ...detail().nutrition, kcal: '630' },
      }),
    )
    await wrapper.get('[data-testid="servings-increase"]').trigger('click')
    await flushPromises()
    expect(api.fetchRecipe).toHaveBeenLastCalledWith(9, '1.5')
    expect(wrapper.get('[data-testid="recipe-ingredient-41"]').text()).toContain('150 g')
    expect(wrapper.get('[data-testid="nutrition-Kalorie"]').text()).toBe('630 kcal')
    expect(wrapper.get('[data-testid="recipe-scaled-for"]').text()).toContain('1,5')
  })

  it('błąd skalowania zachowuje ostatni wynik w Query i mówi, dla ilu porcji jest potwierdzony', async () => {
    await render()
    api.fetchRecipe.mockRejectedValueOnce(new Error('offline'))
    await wrapper.get('[data-testid="servings-increase"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="recipe-name"]').text()).toBe('Wspólny żurek')
    expect(wrapper.get('[data-testid="recipe-ingredient-41"]').text()).toContain('100 g')
    expect(wrapper.get('[data-testid="recipe-scaled-for"]').text()).toContain('dla 1 porcji')
    expect(wrapper.find('[data-testid="recipe-refresh-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="recipe-error"]').exists()).toBe(false)
    api.fetchRecipe.mockResolvedValueOnce(detail({ servings: '1.5' }))
    await wrapper.get('[data-testid="recipe-refresh-error"] button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="recipe-refresh-error"]').exists()).toBe(false)
  })

  it('błąd pierwszego odczytu daje retry i nie udaje pustego przepisu', async () => {
    api.fetchRecipe.mockRejectedValueOnce(new Error('offline'))
    await render()
    expect(wrapper.find('[data-testid="recipe-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="recipe-name"]').exists()).toBe(false)
    await wrapper.get('[data-testid="recipe-error"] button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="recipe-error"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="recipe-name"]').exists()).toBe(true)
  })

  it('kolejna zmiana porcji po błędzie zachowuje potwierdzone dane bez pierwszego skeletonu', async () => {
    await render()
    api.fetchRecipe.mockRejectedValueOnce(new Error('offline'))
    await wrapper.get('[data-testid="servings-increase"]').trigger('click')
    await flushPromises()
    api.fetchRecipe.mockReturnValueOnce(new Promise(() => {}))
    await wrapper.get('[data-testid="servings-increase"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="status"][aria-busy="true"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="recipe-name"]').text()).toBe('Wspólny żurek')
    expect(wrapper.get('[data-testid="recipe-ingredient-41"]').text()).toContain('100 g')
    expect(api.fetchRecipe).toHaveBeenLastCalledWith(9, '2.0')
  })

  it('inna trasa ID nie dziedziczy poprzedniego przepisu ani jego akcji przez placeholderData', async () => {
    await render()
    api.fetchRecipe.mockReturnValueOnce(new Promise(() => {}))
    await router.push('/przepisy/77')
    await flushPromises()
    expect(wrapper.find('[data-testid="recipe-name"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="recipe-copy"]').exists()).toBe(false)
  })

  it('brakujące wartości są jawne, a planowanie globalnego bierze ID i datę URL', async () => {
    await render(
      'user',
      1,
      detail({ nutrition: { ...detail().nutrition, complete: false, missing: ['Jabłko: IG'] } }),
      '/przepisy/9?q=zupa&selectedDate=2031-04-09&from=2031-04-07&to=2031-04-13',
    )
    expect(wrapper.get('[data-testid="recipe-incomplete"]').text()).toContain('Jabłko: IG')
    expect(wrapper.get('[data-testid="recipe-back"]').attributes('href')).toContain(
      '/przepisy?q=zupa',
    )
    await wrapper.get('[data-testid="recipe-plan"]').trigger('click')
    const panel = wrapper.findComponent(RecipePlanningPanel)
    expect(panel.props()).toMatchObject({ open: true, recipe: { id: 9 }, date: '2031-04-09' })
    panel.vm.$emit('close')
    await flushPromises()
    expect(panel.props('open')).toBe(false)
    await wrapper.get('[data-testid="recipe-plan"]').trigger('click')
    panel.vm.$emit('saved', { day: { day: '2031-04-11' }, mealId: 40, itemId: 60, mode: 'add' })
    await flushPromises()
    expect(router.currentRoute.value.params.date).toBe('2031-04-11')
  })
})
