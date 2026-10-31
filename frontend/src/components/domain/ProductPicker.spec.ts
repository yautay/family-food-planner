import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProductPicker from './ProductPicker.vue'

const { fetchProducts, fetchCategories, createProduct, fetchProduct } = vi.hoisted(() => ({
  fetchProducts: vi.fn(),
  fetchCategories: vi.fn(),
  createProduct: vi.fn(),
  fetchProduct: vi.fn(),
}))

vi.mock('@/api/catalog', () => ({
  fetchProducts,
  fetchCategories,
  createProduct,
  fetchProduct,
}))

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

const MARCHEW = { ...CEBULA, id: 2, name: 'Marchew', normalized_name: 'marchew' }

function mountPicker() {
  return mount(ProductPicker, {
    props: { debounceMs: 0 },
    global: { plugins: [VueQueryPlugin], stubs: { RouterLink: true } },
  })
}

async function type(wrapper: ReturnType<typeof mountPicker>, phrase: string) {
  // Focus otwiera listę — dokładnie tak, jak przy pracy z klawiatury.
  await wrapper.get('[data-testid="picker-input"]').trigger('focus')
  await wrapper.get('[data-testid="picker-input"]').setValue(phrase)
  await flushPromises()
  await flushPromises()
}

describe('ProductPicker', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchProducts.mockResolvedValue({ items: [CEBULA, MARCHEW], total: 2 })
    fetchCategories.mockResolvedValue({
      items: [{ id: 1, name: 'Warzywa', position: 1, perishability: 'fresh' }],
      total: 1,
    })
  })

  it('dwa pickery mają oddzielne etykiety i listy wyników, także z własnym inputId', async () => {
    const wrapper = mount(
      defineComponent({
        components: { ProductPicker },
        template:
          '<div><ProductPicker label="Pierwszy" :debounce-ms="0" /><ProductPicker label="Drugi" input-id="drugi-produkt" :debounce-ms="0" /></div>',
      }),
      { attachTo: document.body, global: { plugins: [VueQueryPlugin] } },
    )
    try {
      const inputs = wrapper.findAll<HTMLInputElement>('[data-testid="picker-input"]')
      expect(inputs[0]!.element.id).not.toBe(inputs[1]!.element.id)
      expect(inputs[1]!.element.id).toBe('drugi-produkt')
      const labels = wrapper.findAll<HTMLLabelElement>('label')
      for (const [index, input] of inputs.entries()) {
        expect(labels[index]!.element.control).toBe(input.element)
        await input.setValue('cebula')
      }
      await flushPromises()
      const lists = wrapper.findAll('[data-testid="picker-results"]')
      expect(lists).toHaveLength(2)
      for (const [index, list] of lists.entries()) {
        expect(inputs[index]!.attributes('aria-controls')).toBe(list.attributes('id'))
      }
      expect(lists[0]!.attributes('id')).not.toBe(lists[1]!.attributes('id'))
    } finally {
      wrapper.unmount()
    }
  })

  it('szuka produktu po wpisanej frazie', async () => {
    const wrapper = mountPicker()

    await type(wrapper, 'cebul')

    expect(fetchProducts).toHaveBeenCalledWith(expect.objectContaining({ q: 'cebul' }))
    expect(wrapper.get('[data-testid="picker-results"]').text()).toContain('Cebula')
  })

  it('kliknięcie w trafienie emituje wybór', async () => {
    const wrapper = mountPicker()
    await type(wrapper, 'cebul')

    await wrapper.get('[data-testid="picker-option-1"]').trigger('click')

    expect(wrapper.emitted('selected')?.[0]?.[0]).toMatchObject({ id: 1, name: 'Cebula' })
    expect(wrapper.emitted('update:modelValue')?.[0]?.[0]).toMatchObject({ id: 1 })
  })

  it('strzałkami i Enterem wybiera się bez myszy', async () => {
    const wrapper = mountPicker()
    await type(wrapper, 'ce')

    const input = wrapper.get('[data-testid="picker-input"]')
    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.trigger('keydown', { key: 'Enter' })

    expect(wrapper.emitted('selected')?.[0]?.[0]).toMatchObject({ id: 2, name: 'Marchew' })
  })

  it('strzałka w górę zawija się na koniec listy', async () => {
    const wrapper = mountPicker()
    await type(wrapper, 'ce')

    const input = wrapper.get('[data-testid="picker-input"]')
    await input.trigger('keydown', { key: 'ArrowUp' })
    await input.trigger('keydown', { key: 'Enter' })

    expect(wrapper.emitted('selected')?.[0]?.[0]).toMatchObject({ id: 2 })
  })

  it('brak trafień proponuje dodanie produktu z wpisaną nazwą', async () => {
    fetchProducts.mockResolvedValue({ items: [], total: 0 })
    const wrapper = mountPicker()

    await type(wrapper, 'kalarepa')

    const create = wrapper.get('[data-testid="picker-create"]')
    expect(create.text()).toContain('kalarepa')
  })

  it('pełny cykl create-in-context: brak wyniku → drawer → zapis → wybór', async () => {
    fetchProducts.mockResolvedValue({ items: [], total: 0 })
    const created = { ...CEBULA, id: 99, name: 'Kalarepa', unit_weights: [] }
    createProduct.mockResolvedValue(created)
    const wrapper = mountPicker()
    await type(wrapper, 'kalarepa')

    await wrapper.get('[data-testid="picker-create"]').trigger('click')
    await flushPromises()

    // Drawer dostaje wpisaną nazwę w prefillu — użytkownik nie pisze jej drugi raz.
    const nameInput = wrapper.get('[data-testid="drawer-product-name"]').element as HTMLInputElement
    expect(nameInput.value).toBe('kalarepa')

    await wrapper.get('[data-testid="drawer-submit"]').trigger('click')
    await flushPromises()

    expect(createProduct).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'kalarepa', category_id: 1, measure_kind: 'mass' }),
    )
    expect(wrapper.emitted('selected')?.[0]?.[0]).toMatchObject({ id: 99, name: 'Kalarepa' })
    // Po wyborze wracamy do przerwanego flow: drawer znika.
    expect(wrapper.find('[data-testid="product-create-drawer"]').exists()).toBe(false)
  })

  it('Escape zamyka listę trafień', async () => {
    const wrapper = mountPicker()
    await type(wrapper, 'ce')

    await wrapper.get('[data-testid="picker-input"]').trigger('keydown', { key: 'Escape' })
    await flushPromises()

    expect(wrapper.emitted('selected')).toBeUndefined()
  })

  it('wybrany produkt pokazuje się zamiast pola wyszukiwania', () => {
    const wrapper = mount(ProductPicker, {
      props: { modelValue: CEBULA, debounceMs: 0 },
      global: { plugins: [VueQueryPlugin] },
    })

    expect(wrapper.get('[data-testid="picker-selected"]').text()).toContain('Cebula')
    expect(wrapper.find('[data-testid="picker-input"]').exists()).toBe(false)
  })

  it('archiwalnych produktów nie szuka — pyta API bez nich', async () => {
    const wrapper = mountPicker()

    await type(wrapper, 'ce')

    expect(fetchProducts).toHaveBeenCalledWith(
      expect.not.objectContaining({ include_archived: true }),
    )
  })
})
