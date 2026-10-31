import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { RetailProduct } from '@/api/retail'
import { ApiError } from '@/api/client'
import RetailProductsSection from './RetailProductsSection.vue'
const api = vi.hoisted(() => ({
  fetchRetailProducts: vi.fn(),
  updateRetailProduct: vi.fn(),
  deleteRetailProduct: vi.fn(),
}))
vi.mock('@/api/retail', () => api)
const rows: RetailProduct[] = Array.from({ length: 55 }, (_, i) => ({
  id: i + 1,
  canonical_product_id: 7,
  canonical_product_name: 'Płatki',
  name: `Opakowanie płatków ${i + 1}`,
  brand: 'Marka',
  store_id: null,
  store_name: null,
  package_amount: '1000.00',
  package_unit: 'g',
  pieces_per_package: null,
  photo_url: null,
  photo_thumb_url: null,
  is_archived: false,
  created_at: '2026-10-31T10:00:00Z',
  updated_at: '2026-10-31T10:00:00Z',
}))
async function render() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = mount(RetailProductsSection, {
    props: { productId: 7 },
    global: {
      plugins: [[VueQueryPlugin, { queryClient }]],
      stubs: { RetailProductCreateDrawer: true },
    },
  })
  await flushPromises()
  return wrapper
}
beforeEach(() => {
  vi.clearAllMocks()
  api.fetchRetailProducts.mockImplementation(({ limit, offset }) =>
    Promise.resolve({ items: rows.slice(offset, offset + limit), total: 55 }),
  )
})
describe('warianty sklepowe produktu', () => {
  it('udostępnia także opakowania spoza pierwszej strony', async () => {
    const wrapper = await render()
    expect(wrapper.findAll('[data-testid^="retail-row-"]')).toHaveLength(50)
    await wrapper.get('[data-testid="retail-load-more"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-testid^="retail-row-"]')).toHaveLength(55)
    expect(api.fetchRetailProducts).toHaveBeenLastCalledWith(
      expect.objectContaining({ canonical_product_id: 7, offset: 50, limit: 50 }),
    )
  })
  it('błąd pobrania nie podszywa się pod pustą bibliotekę', async () => {
    api.fetchRetailProducts.mockRejectedValue(new Error('sieć'))
    const wrapper = await render()
    expect(wrapper.find('[data-testid="retail-empty"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Nie udało się pobrać wariantów')
  })
  it('409 proponuje archiwizację dokładnie blokowanego wariantu', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    api.deleteRetailProduct.mockRejectedValue(
      new ApiError(409, {
        code: 'conflict',
        message: 'Wariant jest używany.',
        details: { used_in: [{ type: 'pantry', id: 8, name: 'Spiżarnia' }] },
      }),
    )
    api.updateRetailProduct.mockResolvedValue(rows[1])
    const wrapper = await render()
    await wrapper.get('[data-testid="retail-delete-2"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="retail-used-in"]').text()).toContain('Spiżarnia')
    await wrapper.get('[data-testid="retail-archive-instead"]').trigger('click')
    await flushPromises()
    expect(api.updateRetailProduct).toHaveBeenCalledWith(2, { is_archived: true })
    vi.restoreAllMocks()
  })
})
