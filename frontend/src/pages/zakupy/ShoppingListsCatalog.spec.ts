import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { PAGE_SIZE } from '@/api/pagination'
import { queryKeys } from '@/api/queryKeys'
import type { ShoppingListSummary, ShoppingListsResponse } from '@/api/shoppingLists'
import ShoppingListsCatalog from './ShoppingListsCatalog.vue'

const { fetchShoppingLists } = vi.hoisted(() => ({ fetchShoppingLists: vi.fn() }))
vi.mock('@/api/shoppingLists', () => ({ fetchShoppingLists }))

function summary(id: number): ShoppingListSummary {
  return {
    id,
    generation_id: 1,
    name: `Zakupy ${id}`,
    round_name: 'Świeże',
    store_id: 3,
    store_name: 'Sklep osiedlowy',
    expires_at: '2020-01-01T10:00:00Z',
    items_total: 12,
    items_checked: 4,
    share: null,
    created_at: '2026-10-29T10:00:00Z',
  }
}
let client: QueryClient
let wrapper: VueWrapper
async function render() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/zakupy/:id', name: 'zakupy-lista', component: { template: '<div />' } },
    ],
  })
  await router.push('/')
  wrapper = mount(ShoppingListsCatalog, {
    global: { plugins: [router, [VueQueryPlugin, { queryClient: client }]] },
  })
  await flushPromises()
  return wrapper
}
describe('ShoppingListsCatalog', () => {
  beforeEach(() => {
    fetchShoppingLists.mockReset()
  })
  afterEach(() => {
    wrapper?.unmount()
    client?.clear()
  })

  it('odróżnia pierwsze ładowanie od pustego katalogu, którego akcja otwiera generator', async () => {
    let finish!: (value: ShoppingListsResponse) => void
    fetchShoppingLists.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve
      }),
    )
    await render()
    expect(wrapper.find('[data-testid="shopping-catalog-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="shopping-catalog-empty"]').exists()).toBe(false)
    finish({ items: [], total: 0 })
    await flushPromises()
    expect(wrapper.find('[data-testid="shopping-catalog-loading"]').exists()).toBe(false)
    await wrapper.get('[data-testid="shopping-catalog-empty"] button').trigger('click')
    expect(wrapper.emitted('create')).toHaveLength(1)
    expect(wrapper.get('[data-testid="shopping-catalog-count"]').text()).toBe('0 z 0')
  })

  it('błąd pierwszej strony nie udaje pustego katalogu; można ponowić pobranie', async () => {
    fetchShoppingLists
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue({ items: [summary(1)], total: 1 })
    await render()
    expect(wrapper.find('[data-testid="shopping-catalog-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="shopping-catalog-empty"]').exists()).toBe(false)
    await wrapper.get('[data-testid="shopping-catalog-error"] button').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="shopping-list-1"]').text()).toContain('Zakupy 1')
  })

  it('pokazuje prawdziwe metadane i odhaczenia także dla starej listy, bez fikcyjnego zakończenia', async () => {
    fetchShoppingLists.mockResolvedValue({ items: [summary(1)], total: 1 })
    await render()
    const row = wrapper.get('[data-testid="shopping-list-1"]')
    expect(row.text()).toContain('Ostatnia lista')
    expect(row.text()).toContain('Sklep osiedlowy')
    expect(row.text()).toContain('29.10.2026')
    expect(row.text()).toContain('Odhaczone 4 z 12')
    expect(row.text()).not.toMatch(/zakończ|aktywna lista/i)
    expect(wrapper.get('[data-testid="shopping-list-link-1"]').attributes('href')).toBe('/zakupy/1')
    expect(fetchShoppingLists).toHaveBeenCalledWith({ limit: PAGE_SIZE, offset: 0 })
  })

  it('doładowuje po offset, zachowuje wiersze przy błędzie i ponawia tę samą stronę', async () => {
    const firstPage = Array.from({ length: PAGE_SIZE }, (_, i) => summary(i + 1))
    fetchShoppingLists
      .mockResolvedValueOnce({ items: firstPage, total: PAGE_SIZE + 1 })
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ items: [summary(PAGE_SIZE + 1)], total: PAGE_SIZE + 1 })
    await render()
    await wrapper.get('[data-testid="shopping-catalog-more"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-testid^="shopping-list-link-"]')).toHaveLength(PAGE_SIZE)
    expect(wrapper.find('[data-testid="shopping-catalog-more-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="shopping-catalog-refresh-error"]').exists()).toBe(false)
    await wrapper.get('[data-testid="shopping-catalog-more"]').trigger('click')
    await flushPromises()
    expect(fetchShoppingLists).toHaveBeenNthCalledWith(2, { limit: PAGE_SIZE, offset: PAGE_SIZE })
    expect(fetchShoppingLists).toHaveBeenNthCalledWith(3, { limit: PAGE_SIZE, offset: PAGE_SIZE })
    expect(wrapper.findAll('[data-testid^="shopping-list-link-"]')).toHaveLength(PAGE_SIZE + 1)
    expect(wrapper.find('[data-testid="shopping-catalog-more"]').exists()).toBe(false)
  })

  it('błąd odświeżenia z cache na końcu katalogu ma widoczne ponowienie i nie kasuje danych', async () => {
    fetchShoppingLists
      .mockResolvedValueOnce({ items: [summary(1)], total: 1 })
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ items: [{ ...summary(1), items_checked: 5 }], total: 1 })
    await render()
    await client.invalidateQueries({ queryKey: queryKeys.shopping.listsIndex })
    await flushPromises()
    expect(wrapper.get('[data-testid="shopping-list-1"]').text()).toContain('Odhaczone 4 z 12')
    expect(wrapper.find('[data-testid="shopping-catalog-loading"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="shopping-catalog-more"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="shopping-catalog-more-error"]').exists()).toBe(false)
    await wrapper.get('[data-testid="shopping-catalog-refresh-error"] button').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="shopping-list-1"]').text()).toContain('Odhaczone 5 z 12')
    expect(wrapper.find('[data-testid="shopping-catalog-refresh-error"]').exists()).toBe(false)
  })

  it('w czasie odświeżania pokazuje dane zamiast skeletonu', async () => {
    fetchShoppingLists.mockResolvedValueOnce({ items: [summary(1)], total: 1 })
    await render()
    let finish!: (value: ShoppingListsResponse) => void
    fetchShoppingLists.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve
      }),
    )
    const refresh = client.invalidateQueries({ queryKey: queryKeys.shopping.listsIndex })
    await flushPromises()
    expect(wrapper.find('[data-testid="shopping-catalog-refreshing"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="shopping-list-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="shopping-catalog-loading"]').exists()).toBe(false)
    finish({ items: [summary(1)], total: 1 })
    await refresh
  })
})
