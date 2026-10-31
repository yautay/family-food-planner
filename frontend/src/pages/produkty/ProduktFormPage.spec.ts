import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthStore } from '@/stores/auth'
import { captureSessionGeneration } from '@/lib/sessionGeneration'

import ProduktFormPage from './ProduktFormPage.vue'

/**
 * Formularz produktu — bramka D15 w interfejsie (BATCH_09).
 *
 * Backend i tak odpowie 403 (test macierzy w `tests/api/test_products.py`), ale
 * pole zablokowane z podpowiedzią jest lepsze od formularza, który przechodzi
 * walidację i pada dopiero na zapisie (karta B09 §Backend, „Frontend").
 * Sprawdzamy więc oba warianty: USER widzi blokadę, ADMIN nie.
 */

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: '10' } }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

const catalogApi = vi.hoisted(() => ({
  fetchProduct: vi.fn(),
  fetchCategories: vi.fn(),
  createProduct: vi.fn(),
  updateProduct: vi.fn(),
  deleteProduct: vi.fn(),
  setProductArchived: vi.fn(),
  setProductNutrition: vi.fn(),
  createUnitWeight: vi.fn(),
  deleteUnitWeight: vi.fn(),
}))
vi.mock('@/api/catalog', () => catalogApi)

const retailApi = vi.hoisted(() => ({
  fetchRetailProducts: vi.fn(),
  createRetailProduct: vi.fn(),
  updateRetailProduct: vi.fn(),
  deleteRetailProduct: vi.fn(),
  uploadRetailPhoto: vi.fn(),
  deleteRetailPhoto: vi.fn(),
}))
vi.mock('@/api/retail', () => retailApi)

vi.mock('@/api/stores', () => ({ fetchStores: vi.fn(), createStore: vi.fn() }))

const PRODUCT = {
  id: 10,
  name: 'Jajko',
  normalized_name: 'jajko',
  category_id: 1,
  category_name: 'Nabiał',
  measure_kind: 'piece' as const,
  piece_weight_g: '60.00',
  verification_status: 'unverified' as const,
  verified_at: null,
  perishability: 'fresh' as const,
  perishability_override: null,
  is_archived: false,
  nutrition: {
    kcal_100: null,
    protein_100: null,
    fat_100: null,
    carbs_100: null,
    fiber_100: null,
    sugars_100: null,
    glycemic_index: null,
    nutrition_source: null,
  },
  completeness: {
    complete: false,
    has_core_macros: false,
    has_glycemic_index: false,
    missing: ['kcal_100'],
  },
  unit_weights: [],
  created_at: '2026-08-21T10:00:00Z',
  updated_at: '2026-08-21T10:00:00Z',
}

async function mountPage(role: 'admin' | 'user') {
  setActivePinia(createPinia())
  const auth = useAuthStore()
  auth.setUser(
    {
      id: 1,
      email: 'kto@example.com',
      display_name: 'Kto',
      role,
      ui_settings: {},
      household: null,
    },
    captureSessionGeneration(),
  )
  const wrapper = mount(ProduktFormPage, { global: { plugins: [VueQueryPlugin] } })
  await flushPromises()
  return wrapper
}

describe('ProduktFormPage — bramka D15', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    catalogApi.fetchProduct.mockResolvedValue(PRODUCT)
    catalogApi.fetchCategories.mockResolvedValue({
      items: [{ id: 1, name: 'Nabiał', position: 1, perishability: 'fresh' }],
      total: 1,
    })
    retailApi.fetchRetailProducts.mockResolvedValue({ items: [], total: 0 })
  })

  it('USER ma wyłączony sposób liczenia i wagę sztuki, z podpowiedzią co zrobić', async () => {
    const wrapper = await mountPage('user')

    expect(wrapper.get('[data-testid="product-measure"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="product-piece-weight"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="product-measure-locked"]').text()).toContain('administrator')
  })

  it('USER nadal edytuje nazwę i kategorię — bramka nie blokuje całego formularza', async () => {
    const wrapper = await mountPage('user')

    expect(wrapper.get('[data-testid="product-name"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('[data-testid="product-category"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('[data-testid="product-submit"]').attributes('disabled')).toBeUndefined()
  })

  it('ADMIN edytuje sposób liczenia bez ograniczeń', async () => {
    const wrapper = await mountPage('admin')

    expect(wrapper.get('[data-testid="product-measure"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('[data-testid="product-measure-locked"]').exists()).toBe(false)
  })

  it('karta produktu pokazuje sekcję produktów sklepowych (AC 5)', async () => {
    const wrapper = await mountPage('user')

    expect(wrapper.find('[data-testid="retail-section"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="retail-empty"]').exists()).toBe(true)
    expect(retailApi.fetchRetailProducts).toHaveBeenCalledWith(
      expect.objectContaining({ canonical_product_id: 10 }),
    )
  })
})
