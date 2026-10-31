import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import SklepySection from './SklepySection.vue'

const api = vi.hoisted(() => ({
  fetchStores: vi.fn(),
  createStore: vi.fn(),
  updateStore: vi.fn(),
  deleteStore: vi.fn(),
  fetchCategoryOrder: vi.fn(),
  setCategoryOrder: vi.fn(),
}))
vi.mock('@/api/stores', () => api)
vi.mock('@/api/catalog', () => ({
  fetchCategories: vi.fn().mockResolvedValue({
    items: [
      { id: 1, name: 'Warzywa', position: 1, perishability: 'fresh' },
      { id: 2, name: 'Nabiał', position: 2, perishability: 'fresh' },
    ],
    total: 2,
  }),
}))
const store = {
  id: 1,
  name: 'Sklep z bardzo długą nazwą osiedlową',
  color: null,
  is_archived: false,
  created_at: '',
  updated_at: '',
}
const disposers: (() => void)[] = []
async function render() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = mount(SklepySection, {
    global: { plugins: [[VueQueryPlugin, { queryClient: client }]] },
  })
  disposers.push(() => {
    wrapper.unmount()
    client.clear()
  })
  await flushPromises()
  return wrapper
}
beforeEach(() => {
  vi.clearAllMocks()
  api.fetchStores.mockResolvedValue({ items: [store], total: 1 })
  api.fetchCategoryOrder.mockResolvedValue({
    items: [
      { category_id: 1, category_name: 'Warzywa', position: 0 },
      { category_id: 2, category_name: 'Nabiał', position: 1 },
    ],
    total: 2,
  })
})
afterEach(() =>
  disposers
    .splice(0)
    .reverse()
    .forEach((dispose) => dispose()),
)

describe('Sklepy w sekcji Zakupy', () => {
  it('zachowuje nazwę i kolor po odmowie zapisu', async () => {
    api.createStore.mockRejectedValueOnce(
      new ApiError(422, { code: 'validation', message: 'Sprawdź nazwę sklepu', details: {} }),
    )
    const wrapper = await render()
    await wrapper.get('[data-testid="store-add"]').trigger('click')
    await wrapper.get('[data-testid="store-name"]').setValue('Nowy sklep')
    await wrapper.get('[data-testid="store-color"]').setValue('primary')
    await wrapper.get('[data-testid="store-form"]').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[data-testid="stores-error"]').text()).toContain('Sprawdź nazwę')
    expect(wrapper.get<HTMLInputElement>('[data-testid="store-name"]').element.value).toBe(
      'Nowy sklep',
    )
    expect(wrapper.get<HTMLInputElement>('[data-testid="store-color"]').element.value).toBe(
      'primary',
    )
  })

  it('po błędzie zapisu kolejności pozostawia szkic i pozwala ponowić tę samą kolejność', async () => {
    api.setCategoryOrder
      .mockRejectedValueOnce(new Error('sieć'))
      .mockResolvedValueOnce({ items: [], total: 0 })
    const wrapper = await render()
    await wrapper.get('[data-testid="store-order-1"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="order-down-1"]').trigger('click')
    await wrapper.get('[data-testid="order-save"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="order-saved"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="stores-error"]').text()).not.toBe('')
    expect(
      wrapper.findAll('[data-testid^="order-row-"]').map((row) => row.attributes('data-testid')),
    ).toEqual(['order-row-2', 'order-row-1'])
    await wrapper.get('[data-testid="order-save"]').trigger('click')
    await flushPromises()
    expect(api.setCategoryOrder).toHaveBeenNthCalledWith(2, 1, [2, 1])
    expect(wrapper.get('[data-testid="order-saved"]').text()).toContain('zapisana')
  })

  it('błąd odczytu kolejności nie otwiera pustego edytora, retry pobiera prawdziwy profil', async () => {
    api.fetchCategoryOrder.mockRejectedValueOnce(new Error('sieć'))
    const wrapper = await render()
    await wrapper.get('[data-testid="store-order-1"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="category-order-editor"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Nie udało się odczytać kolejności')
    await wrapper.get('[role="alert"]').element.parentElement!.querySelector('button')!.click()
    await flushPromises()
    expect(wrapper.find('[data-testid="order-row-1"]').exists()).toBe(true)
    expect(api.setCategoryOrder).not.toHaveBeenCalled()
  })
})
