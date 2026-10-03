import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import PrzepisEdytorPage from './PrzepisEdytorPage.vue'

const routerPush = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {} }),
  useRouter: () => ({ push: routerPush, replace: vi.fn() }),
}))

const recipesApi = vi.hoisted(() => ({
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

function mountEditor() {
  // Edytor czyta rolę z `useAuthStore` (opcja zakresu Wszyscy tylko dla ADMIN-a).
  setActivePinia(createPinia())
  return mount(PrzepisEdytorPage, {
    global: { plugins: [VueQueryPlugin], stubs: { RouterLink: true } },
  })
}

describe('PrzepisEdytorPage — składniki przez ProductPicker', () => {
  beforeEach(() => {
    vi.clearAllMocks()
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
    expect(routerPush).toHaveBeenCalledWith({ name: 'przepis-szczegol', params: { id: 7 } })
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
