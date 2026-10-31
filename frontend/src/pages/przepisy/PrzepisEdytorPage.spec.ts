import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RecipeDetail } from '@/api/recipes'

import PrzepisEdytorPage from './PrzepisEdytorPage.vue'

const routerPush = vi.hoisted(() => vi.fn())
const route = vi.hoisted(() => ({
  params: {} as Record<string, string>,
  query: {} as Record<string, string | string[] | null>,
}))

vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ push: routerPush, replace: vi.fn() }),
  onBeforeRouteLeave: vi.fn(),
  onBeforeRouteUpdate: vi.fn(),
}))

const recipesApi = vi.hoisted(() => ({
  copyRecipe: vi.fn(),
  createRecipe: vi.fn(),
  updateRecipe: vi.fn(),
  createTag: vi.fn(),
  fetchRecipe: vi.fn(),
  fetchTags: vi.fn(),
  uploadRecipePhoto: vi.fn(),
  deleteRecipePhoto: vi.fn(),
}))

vi.mock('@/api/recipes', () => recipesApi)

const catalogApi = vi.hoisted(() => ({
  fetchProducts: vi.fn(),
  fetchCategories: vi.fn(),
  createProduct: vi.fn(),
  fetchProduct: vi.fn(),
  fetchUnitWeights: vi.fn(),
}))

vi.mock('@/api/catalog', () => catalogApi)

const CEBULA = {
  id: 1,
  name: 'Cebula',
  normalized_name: 'cebula',
  category_id: 1,
  category_name: 'Warzywa',
  measure_kind: 'mass' as const,
  piece_weight_g: null,
  verification_status: 'verified' as const,
  verified_at: null,
  perishability: 'fresh' as const,
  perishability_override: null,
  is_archived: false,
  nutrition: {
    kcal_100: '40.00',
    protein_100: '1.10',
    fat_100: '0.10',
    carbs_100: '9.30',
    fiber_100: null,
    sugars_100: null,
    glycemic_index: '15.0',
    nutrition_source: 'usda',
  },
  completeness: { complete: true, has_core_macros: true, has_glycemic_index: true, missing: [] },
  created_at: '2026-08-16T10:00:00Z',
  updated_at: '2026-08-16T10:00:00Z',
}

function mountEditor(attachTo?: HTMLElement) {
  // Edytor czyta rolę z `useAuthStore` (opcja zakresu Wszyscy tylko dla ADMIN-a).
  setActivePinia(createPinia())
  return mount(PrzepisEdytorPage, {
    attachTo,
    global: { plugins: [VueQueryPlugin], stubs: { RouterLink: RouterLinkStub } },
  })
}

describe('PrzepisEdytorPage — składniki przez ProductPicker', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    route.params = {}
    route.query = {}
    recipesApi.fetchTags.mockResolvedValue({ items: [], total: 0 })
    catalogApi.fetchProducts.mockResolvedValue({ items: [CEBULA], total: 1 })
    catalogApi.fetchUnitWeights.mockResolvedValue({
      items: [
        {
          id: 5,
          product_id: 1,
          unit_label: 'łyżka',
          grams_per_unit: '15.00',
          source: null,
          samples_count: 1,
        },
      ],
      total: 1,
    })
    recipesApi.createRecipe.mockResolvedValue({ id: 7 })
  })

  it('dodanie składnika przez ProductPicker aktualizuje model i payload zapisu', async () => {
    const wrapper = mountEditor()

    await wrapper.get('[data-testid="ingredient-add"]').trigger('click')
    expect(wrapper.find('[data-testid="ingredient-row-0"]').exists()).toBe(true)

    // Wyszukanie i wybór produktu w pickerze — edytor używa domyślnego
    // debounce (250 ms), więc czekamy realnie; fake timers psułyby kolejkę
    // zadań vee-validate/vue-query.
    await wrapper.get('[data-testid="picker-input"]').trigger('focus')
    await wrapper.get('[data-testid="picker-input"]').setValue('cebul')
    await new Promise((resolve) => setTimeout(resolve, 300))
    await flushPromises()

    await wrapper.get('[data-testid="picker-option-1"]').trigger('click')
    await flushPromises()

    // Model wiersza zaktualizowany: picker pokazuje wybór, jednostki produktu
    // (systemowe + przelicznik domowy) trafiają do selecta ilości.
    expect(wrapper.get('[data-testid="picker-selected"]').text()).toContain('Cebula')
    const unitOptions = wrapper
      .get('[data-testid="ingredient-amount-0-unit"]')
      .findAll('option')
      .map((option) => option.text())
    expect(unitOptions).toEqual(['g', 'kg', 'łyżka'])

    await wrapper.get('[data-testid="ingredient-amount-0"]').setValue('2,5')
    await wrapper.get('[data-testid="ingredient-amount-0-unit"]').setValue('łyżka')

    await wrapper.get('[data-testid="recipe-name"]').setValue('Zupa cebulowa')
    await wrapper.get('[data-testid="recipe-form"]').trigger('submit')
    // Walidacja vee-validate jest asynchroniczna — czekamy na faktyczny zapis.
    await vi.waitFor(() => expect(recipesApi.createRecipe).toHaveBeenCalled())

    expect(recipesApi.createRecipe).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'Zupa cebulowa',
        base_servings: 1,
        ingredients: [{ product_id: 1, quantity: '2.5', unit: 'łyżka', note: '' }],
      }),
    )
    expect(routerPush).toHaveBeenCalledWith({
      name: 'przepis-szczegol',
      params: { id: 7 },
      query: {},
    })
  })

  it('składnik bez produktu blokuje wysyłkę z czytelnym komunikatem', async () => {
    const wrapper = mountEditor()
    await wrapper.get('[data-testid="ingredient-add"]').trigger('click')
    await wrapper.get('[data-testid="recipe-name"]').setValue('Zupa')

    await wrapper.get('[data-testid="recipe-form"]').trigger('submit')
    await vi.waitFor(() =>
      expect(wrapper.get('[data-testid="recipe-editor-error"]').text()).toContain('składnik'),
    )

    expect(recipesApi.createRecipe).not.toHaveBeenCalled()
  })

  it('usunięcie wiersza składnika czyści model', async () => {
    const wrapper = mountEditor()
    await wrapper.get('[data-testid="ingredient-add"]').trigger('click')

    await wrapper.get('[data-testid="ingredient-remove-0"]').trigger('click')

    expect(wrapper.find('[data-testid="ingredient-row-0"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="ingredients-empty"]').text()).not.toBe('')
  })
})

describe('PrzepisEdytorPage — naturalny fokus nad paskiem zapisu', () => {
  let wrapper: ReturnType<typeof mountEditor>
  let frame: FrameRequestCallback | undefined
  let scroll: ReturnType<typeof vi.spyOn>
  beforeEach(async () => {
    vi.clearAllMocks()
    route.params = {}
    route.query = {}
    recipesApi.fetchTags.mockResolvedValue({ items: [], total: 0 })
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      frame = callback
      return 1
    })
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {})
    scroll = vi.spyOn(window, 'scrollBy').mockImplementation(() => {})
    wrapper = mountEditor(document.body)
    await flushPromises()
    vi.spyOn(
      wrapper.get('[data-testid="recipe-save-bar"]').element,
      'getBoundingClientRect',
    ).mockReturnValue(new DOMRect(0, 500, 300, 100))
  })
  afterEach(() => {
    wrapper.unmount()
    vi.restoreAllMocks()
    frame = undefined
  })

  it('odsłania faktycznie aktywne pole zasłonięte paskiem bez zmiany fokusu', () => {
    const input = wrapper.get<HTMLInputElement>('[data-testid="recipe-name"]').element
    vi.spyOn(input, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 480, 300, 44))
    input.focus()
    frame?.(0)
    expect(scroll).toHaveBeenCalledWith({ top: 256, behavior: 'instant' })
    expect(document.activeElement).toBe(input)
  })

  it('nie przewija już widocznego pola ani przycisku w pasku zapisu', () => {
    const input = wrapper.get<HTMLInputElement>('[data-testid="recipe-name"]').element
    vi.spyOn(input, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 120, 300, 44))
    input.focus()
    frame?.(0)
    wrapper.get<HTMLButtonElement>('[data-testid="recipe-submit"]').element.focus()
    frame?.(0)
    expect(scroll).not.toHaveBeenCalled()
  })

  it('ignoruje zdarzenie dla nieaktywnego pola i pomiar po przeniesieniu fokusu', async () => {
    const input = wrapper.get<HTMLInputElement>('[data-testid="recipe-name"]').element
    vi.spyOn(input, 'getBoundingClientRect').mockReturnValue(new DOMRect(0, 480, 300, 44))
    await wrapper.get('[data-testid="recipe-name"]').trigger('focusin')
    frame?.(0)
    expect(scroll).not.toHaveBeenCalled()
    input.focus()
    const staleFrame = frame
    wrapper.get<HTMLButtonElement>('[data-testid="recipe-submit"]').element.focus()
    staleFrame?.(0)
    expect(scroll).not.toHaveBeenCalled()
  })
})

describe('PrzepisEdytorPage — zachowanie kontekstu katalogu i planowania', () => {
  const context = {
    q: 'zupa',
    tag: ['2', '7'],
    scope: 'household',
    prep_time_max: '30',
    selectedDate: '2031-04-09',
    from: '2031-04-07',
    to: '2031-04-13',
  }
  function detail(id: number): RecipeDetail {
    return {
      id,
      name: 'Zupa na sobotę',
      instructions: 'Ugotuj i podaj.',
      scope: 'household',
      owner_user_id: 1,
      base_servings: 2,
      prep_time_min: 30,
      difficulty: null,
      is_archived: false,
      photo_url: null,
      photo_thumb_url: null,
      tags: [],
      avg_rating: null,
      ratings_count: 0,
      my_rating: null,
      servings: '1',
      ingredients: [],
      nutrition: {
        kcal: '0',
        protein_g: '0',
        fat_g: '0',
        carbs_g: '0',
        fiber_g: '0',
        sugars_g: '0',
        glycemic_load: '0',
        complete: true,
        missing: [],
      },
      created_at: '2026-10-03T10:00:00Z',
      updated_at: '2026-10-03T10:00:00Z',
    }
  }
  let wrapper: ReturnType<typeof mountEditor>
  beforeEach(() => {
    vi.resetAllMocks()
    route.params = {}
    route.query = { ...context, offset: '50', next: 'https://example.com/nie-przekierowuj' }
    recipesApi.fetchTags.mockResolvedValue({ items: [], total: 0 })
    recipesApi.fetchRecipe.mockResolvedValue(detail(19))
    recipesApi.createRecipe.mockResolvedValue(detail(77))
    recipesApi.updateRecipe.mockResolvedValue(detail(19))
    catalogApi.fetchUnitWeights.mockResolvedValue({ items: [], total: 0 })
  })
  afterEach(() => {
    wrapper?.unmount()
  })

  it.each([false, true])(
    'Wróć z edytora (edycja=%s) nadal prowadzi do katalogu z całą allowlistą query',
    async (edit) => {
      route.params = edit ? { id: '19' } : {}
      wrapper = mountEditor()
      await flushPromises()
      expect(wrapper.getComponent(RouterLinkStub).props('to')).toEqual({
        name: 'przepisy',
        query: context,
      })
    },
  )

  it.each([false, true])(
    'zapis (edycja=%s) zachowuje filtry i datę przy rzeczywistym ID odpowiedzi API',
    async (edit) => {
      route.params = edit ? { id: '19' } : {}
      wrapper = mountEditor()
      await flushPromises()
      await wrapper.get('[data-testid="recipe-name"]').setValue('Zupa po zapisaniu')
      await wrapper.get('[data-testid="recipe-form"]').trigger('submit')
      await vi.waitFor(() =>
        expect(routerPush).toHaveBeenCalledWith({
          name: 'przepis-szczegol',
          params: { id: edit ? 19 : 77 },
          query: context,
        }),
      )
      if (edit) {
        expect(recipesApi.updateRecipe).toHaveBeenCalledWith(
          19,
          expect.objectContaining({ name: 'Zupa po zapisaniu', scope: 'household' }),
        )
        expect(recipesApi.createRecipe).not.toHaveBeenCalled()
      } else {
        expect(recipesApi.createRecipe).toHaveBeenCalledWith(
          expect.objectContaining({ name: 'Zupa po zapisaniu', scope: 'private' }),
        )
        expect(recipesApi.updateRecipe).not.toHaveBeenCalled()
      }
    },
  )
})
