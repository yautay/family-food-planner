import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { advanceSessionGeneration, captureSessionGeneration } from '@/lib/sessionGeneration'

import ProduktFormPage from './ProduktFormPage.vue'

/**
 * Formularz produktu — bramka D15 w interfejsie (BATCH_09).
 *
 * Backend i tak odpowie 403 (test macierzy w `tests/api/test_products.py`), ale
 * pole zablokowane z podpowiedzią jest lepsze od formularza, który przechodzi
 * walidację i pada dopiero na zapisie (karta B09 §Backend, „Frontend").
 * Sprawdzamy więc oba warianty: USER widzi blokadę, ADMIN nie.
 */

const navigation = vi.hoisted(() => ({
  query: {} as Record<string, string>,
  params: { id: '10' } as { id?: string },
  push: vi.fn(),
  replace: vi.fn(),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: navigation.params, query: navigation.query }),
  useRouter: () => ({ push: navigation.push, replace: navigation.replace }),
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
    missing: [
      'Jajko: brak kalorii',
      'Jajko: brak białka',
      'Jajko: brak tłuszczu',
      'Jajko: brak węglowodanów',
      'Jajko: brak indeksu glikemicznego',
    ],
  },
  unit_weights: [],
  created_at: '2026-08-21T10:00:00Z',
  updated_at: '2026-08-21T10:00:00Z',
}

let client: QueryClient
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
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = mount(ProduktFormPage, {
    global: { plugins: [[VueQueryPlugin, { queryClient: client }]] },
  })
  await flushPromises()
  return wrapper
}

describe('ProduktFormPage — bramka D15', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    navigation.query = {}
    navigation.params = { id: '10' }
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
  it('USER widzi braki wartości i nie dostaje przycisku usuwania', async () => {
    const wrapper = await mountPage('user')
    expect(wrapper.get('[data-testid="nutrition-incomplete-toggle"]').text()).toBe(
      'Niepełne dane — szczegóły',
    )
    expect(
      wrapper.findAll('[data-testid="nutrition-incomplete-messages"] li').map((row) => row.text()),
    ).toEqual(PRODUCT.completeness.missing)
    expect(wrapper.get('[data-testid="nutrition-incomplete"]').attributes('open')).toBeUndefined()
    expect(wrapper.find('[data-testid="nutrition-form"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="product-delete"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="product-archive"]').exists()).toBe(true)
  })

  it('jednostka domowa przechodzi istniejący parser przecinka jako string', async () => {
    catalogApi.createUnitWeight.mockResolvedValue({ id: 2 })
    const wrapper = await mountPage('user')
    await wrapper.get('[data-testid="unit-weight-label"]').setValue('łyżka')
    await wrapper.get('[data-testid="unit-weight-grams"]').setValue('0,25')
    await wrapper.get('[data-testid="unit-weight-form"]').trigger('submit')
    await flushPromises()
    expect(catalogApi.createUnitWeight).toHaveBeenCalledWith(
      10,
      expect.objectContaining({ unit_label: 'łyżka', grams_per_unit: '0.25', samples_count: 1 }),
    )
  })

  it('409 zachowuje produkt, opisuje użycia i daje archiwizację', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    catalogApi.deleteProduct.mockRejectedValue(
      new ApiError(409, {
        code: 'conflict',
        message: 'Produkt jest używany.',
        details: { used_in: [{ type: 'recipe', id: 42, name: 'Owsianka' }] },
      }),
    )
    const wrapper = await mountPage('admin')
    await wrapper.get('[data-testid="product-delete"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="product-used-in"]').text()).toContain('Owsianka')
    expect(wrapper.find('[data-testid="product-archive-instead"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="product-name"]').element).toHaveProperty('value', 'Jajko')
    vi.restoreAllMocks()
  })
  it('usunięcie zachowuje filtr i strony powrotu, usuwając fokus skasowanego produktu', async () => {
    navigation.query = { q: 'Jajko', category: '4', archived: '1', pages: '2', focus: '10' }
    catalogApi.deleteProduct.mockResolvedValue(undefined)
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = await mountPage('admin')
    try {
      await wrapper.get('[data-testid="product-delete"]').trigger('click')
      await flushPromises()
      expect(catalogApi.deleteProduct).toHaveBeenCalledWith(10)
      expect(navigation.push).toHaveBeenCalledWith({
        name: 'produkty',
        query: { q: 'Jajko', category: '4', archived: '1', pages: '2' },
      })
      expect(navigation.query.focus).toBe('10')
    } finally {
      wrapper.unmount()
      confirm.mockRestore()
    }
  })

  it.each([
    ['create', 'session'],
    ['delete', 'session'],
    ['create', 'unmount'],
    ['delete', 'unmount'],
  ] as const)('%s nie nawiguje po %s w trakcie odświeżenia', async (action, change) => {
    if (action === 'create') navigation.params = {}
    catalogApi.createProduct.mockResolvedValue(PRODUCT)
    catalogApi.deleteProduct.mockResolvedValue(undefined)
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = await mountPage('admin')
    let finish!: () => void
    const invalidate = vi.spyOn(client, 'invalidateQueries').mockReturnValueOnce(
      new Promise<void>((resolve) => {
        finish = resolve
      }),
    )
    try {
      if (action === 'create') {
        await wrapper.get('[data-testid="product-name"]').setValue('Jajko')
        await wrapper.get('[data-testid="product-submit"]').trigger('submit')
        await vi.waitFor(() => expect(catalogApi.createProduct).toHaveBeenCalledOnce())
      } else {
        await wrapper.get('[data-testid="product-delete"]').trigger('click')
      }
      await flushPromises()
      expect(invalidate).toHaveBeenCalled()
      if (change === 'session') advanceSessionGeneration()
      else wrapper.unmount()
      finish()
      await flushPromises()
      expect(navigation.push).not.toHaveBeenCalled()
      expect(navigation.replace).not.toHaveBeenCalled()
    } finally {
      wrapper.unmount()
      confirm.mockRestore()
    }
  })

  it('utworzenie w bieżącej sesji otwiera edycję potwierdzonego produktu', async () => {
    navigation.params = {}
    navigation.query = { q: 'jaj', category: '1' }
    catalogApi.createProduct.mockResolvedValue(PRODUCT)
    const wrapper = await mountPage('user')
    let finish!: () => void
    vi.spyOn(client, 'invalidateQueries').mockReturnValueOnce(
      new Promise<void>((resolve) => {
        finish = resolve
      }),
    )
    try {
      await wrapper.get('[data-testid="product-name"]').setValue('Jajko')
      await wrapper.get('[data-testid="product-submit"]').trigger('submit')
      await vi.waitFor(() => expect(catalogApi.createProduct).toHaveBeenCalledOnce())
      expect(navigation.replace).not.toHaveBeenCalled()
      finish()
      await vi.waitFor(() =>
        expect(navigation.replace).toHaveBeenCalledWith({
          name: 'produkt-edycja',
          params: { id: 10 },
          query: { q: 'jaj', category: '1' },
        }),
      )
    } finally {
      wrapper.unmount()
    }
  })
})
