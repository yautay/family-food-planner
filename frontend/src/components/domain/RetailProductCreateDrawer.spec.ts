import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import RetailProductCreateDrawer from './RetailProductCreateDrawer.vue'

/**
 * `RetailProductCreateDrawer` — KONTRAKT dla B10/B11 (karta B09, AC 6).
 *
 * Testy pilnują dokładnie tego, na co tamte batche będą liczyć: props
 * `{ open, canonicalProductId, prefillName }`, emit `created` z zapisanym
 * wariantem oraz jednostka opakowania ZAWĘŻONA do osi produktu kanonicznego
 * (backend odrzuciłby każdą inną — 422).
 */

const { fetchProduct, createRetailProduct, uploadRetailPhoto, fetchStores, createStore } =
  vi.hoisted(() => ({
    fetchProduct: vi.fn(),
    createRetailProduct: vi.fn(),
    uploadRetailPhoto: vi.fn(),
    fetchStores: vi.fn(),
    createStore: vi.fn(),
  }))

vi.mock('@/api/catalog', () => ({ fetchProduct }))
vi.mock('@/api/retail', () => ({ createRetailProduct, uploadRetailPhoto }))
vi.mock('@/api/stores', () => ({ fetchStores, createStore }))

function product(overrides: Record<string, unknown> = {}) {
  return {
    id: 10,
    name: 'Jogurt naturalny',
    measure_kind: 'mass' as const,
    piece_weight_g: null,
    ...overrides,
  }
}

function retailProduct(overrides: Record<string, unknown> = {}) {
  return {
    id: 55,
    canonical_product_id: 10,
    canonical_product_name: 'Jogurt naturalny',
    name: 'Pilos Jogurt naturalny 400 g',
    brand: 'Pilos',
    store_id: null,
    store_name: null,
    package_amount: '400.00',
    package_unit: 'g' as const,
    pieces_per_package: null,
    photo_url: null,
    photo_thumb_url: null,
    is_archived: false,
    created_at: '2026-08-21T10:00:00Z',
    updated_at: '2026-08-21T10:00:00Z',
    ...overrides,
  }
}

async function mountDrawer(props: Record<string, unknown> = {}) {
  const wrapper = mount(RetailProductCreateDrawer, {
    props: { open: true, canonicalProductId: 10, ...props },
    global: { plugins: [VueQueryPlugin] },
  })
  await flushPromises()
  return wrapper
}

describe('RetailProductCreateDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchProduct.mockResolvedValue(product())
    fetchStores.mockResolvedValue({ items: [], total: 0 })
    createRetailProduct.mockResolvedValue(retailProduct())
  })

  it('prefill wypełnia nazwę, a jednostka wynika ze sposobu liczenia produktu', async () => {
    const wrapper = await mountDrawer({ prefillName: 'Pilos Jogurt naturalny 400 g' })

    expect((wrapper.get('[data-testid="retail-name"]').element as HTMLInputElement).value).toBe(
      'Pilos Jogurt naturalny 400 g',
    )
    // Produkt liczony na wagę ⇒ jedyną jednostką opakowania jest gram.
    const unit = wrapper.get('[data-testid="retail-amount-unit"]')
    expect(unit.findAll('option').map((option) => option.text())).toEqual(['g'])
  })

  it('produkt liczony w sztukach dostaje jednostkę „szt."', async () => {
    fetchProduct.mockResolvedValue(
      product({ id: 11, name: 'Jajko', measure_kind: 'piece', piece_weight_g: '60.00' }),
    )

    const wrapper = await mountDrawer({ canonicalProductId: 11 })

    const unit = wrapper.get('[data-testid="retail-amount-unit"]')
    expect(unit.findAll('option').map((option) => option.text())).toEqual(['szt.'])
  })

  it('zapis wysyła komplet pól i emituje `created` z zapisanym wariantem', async () => {
    const wrapper = await mountDrawer({ prefillName: 'Pilos Jogurt naturalny 400 g' })

    await wrapper.get('[data-testid="retail-brand"]').setValue('Pilos')
    await wrapper.get('[data-testid="retail-amount"]').setValue('400')
    await flushPromises()
    await wrapper.get('[data-testid="retail-submit"]').trigger('click')
    await flushPromises()

    expect(createRetailProduct).toHaveBeenCalledWith({
      canonical_product_id: 10,
      name: 'Pilos Jogurt naturalny 400 g',
      brand: 'Pilos',
      store_id: null,
      package_amount: '400',
      package_unit: 'g',
      pieces_per_package: null,
    })
    expect(wrapper.emitted('created')?.[0]).toEqual([retailProduct()])
    // Bez pliku nie dotykamy endpointu zdjęcia.
    expect(uploadRetailPhoto).not.toHaveBeenCalled()
  })

  it('zapis jest zablokowany bez nazwy i bez wielkości opakowania', async () => {
    const wrapper = await mountDrawer()

    expect(wrapper.get('[data-testid="retail-submit"]').attributes('disabled')).toBeDefined()

    await wrapper.get('[data-testid="retail-name"]').setValue('Jogurt 400 g')
    await flushPromises()
    // Nazwa jest, ale ilości nadal nie ma.
    expect(wrapper.get('[data-testid="retail-submit"]').attributes('disabled')).toBeDefined()

    await wrapper.get('[data-testid="retail-amount"]').setValue('400')
    await flushPromises()
    expect(wrapper.get('[data-testid="retail-submit"]').attributes('disabled')).toBeUndefined()
  })

  it('liczba sztuk w opakowaniu musi być liczbą całkowitą', async () => {
    const wrapper = await mountDrawer({ prefillName: 'Jaja 10 szt.' })
    await wrapper.get('[data-testid="retail-amount"]').setValue('10')
    await flushPromises()

    await wrapper.get('[data-testid="retail-pieces"]').setValue('dziesięć')
    await flushPromises()

    expect(wrapper.get('[data-testid="retail-submit"]').attributes('disabled')).toBeDefined()
  })

  it('błąd zapisu pokazuje komunikat i nie emituje `created`', async () => {
    const { ApiError } = await import('@/api/client')
    createRetailProduct.mockRejectedValue(
      new ApiError(422, {
        code: 'validation_error',
        message: 'Opakowanie w złej jednostce.',
        details: {},
      }),
    )
    const wrapper = await mountDrawer({ prefillName: 'Jogurt 400 g' })
    await wrapper.get('[data-testid="retail-amount"]').setValue('400')
    await flushPromises()

    await wrapper.get('[data-testid="retail-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="retail-drawer-error"]').text()).toContain(
      'Opakowanie w złej jednostce.',
    )
    expect(wrapper.emitted('created')).toBeUndefined()
  })

  it('anulowanie emituje `close`', async () => {
    const wrapper = await mountDrawer()

    await wrapper.get('[data-testid="retail-cancel"]').trigger('click')

    expect(wrapper.emitted('close')).toHaveLength(1)
  })
})
