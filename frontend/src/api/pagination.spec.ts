import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { usePaginatedList, type PageResponse, type PaginatedList } from './pagination'

let client: QueryClient
let wrapper: VueWrapper
let list: PaginatedList<{ id: number }>
const key = ['pagination-regression'] as const
async function render(
  fetchPage: (page: { limit: number; offset: number }) => Promise<PageResponse<{ id: number }>>,
) {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  wrapper = mount(
    defineComponent({
      setup() {
        list = usePaginatedList({ queryKey: key, fetchPage, pageSize: 2 })
        return () => null
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
  )
  await flushPromises()
}
afterEach(() => {
  wrapper?.unmount()
  client?.clear()
})
describe('paginacja — zachowanie cache i precyzyjne błędy', () => {
  it('odróżnia błąd kolejnej strony od odświeżenia, zachowuje legacy flagę i ponawia ten sam offset', async () => {
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce({ items: [{ id: 1 }, { id: 2 }], total: 3 })
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ items: [{ id: 3 }], total: 3 })
    await render(fetchPage)
    list.loadMore()
    await flushPromises()
    expect(list.items.value).toEqual([{ id: 1 }, { id: 2 }])
    expect(list.isError.value).toBe(false)
    expect(list.nextPageFailed.value).toBe(true)
    expect(list.loadMoreFailed.value).toBe(true)
    expect(list.refreshFailed.value).toBe(false)
    list.loadMore()
    await flushPromises()
    expect(fetchPage).toHaveBeenNthCalledWith(3, { limit: 2, offset: 2 })
    expect(list.loaded.value).toBe(3)
    expect(list.hasMore.value).toBe(false)
    expect(list.nextPageFailed.value).toBe(false)
  })
  it('błąd refetch na końcu katalogu ma osobną flagę i refresh ponawia wszystkie strony', async () => {
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce({ items: [{ id: 1 }, { id: 2 }], total: 3 })
      .mockResolvedValueOnce({ items: [{ id: 3 }], total: 3 })
    await render(fetchPage)
    list.loadMore()
    await flushPromises()
    fetchPage.mockRejectedValueOnce(new Error('offline'))
    await client.invalidateQueries({ queryKey: key })
    await flushPromises()
    expect(list.loaded.value).toBe(3)
    expect(list.hasMore.value).toBe(false)
    expect(list.refreshFailed.value).toBe(true)
    expect(list.nextPageFailed.value).toBe(false)
    expect(list.loadMoreFailed.value).toBe(true)
    expect(list.isError.value).toBe(false)
    fetchPage
      .mockResolvedValueOnce({ items: [{ id: 1 }, { id: 2 }], total: 3 })
      .mockResolvedValueOnce({ items: [{ id: 3 }], total: 3 })
    list.refresh()
    await flushPromises()
    expect(fetchPage.mock.calls.slice(-2)).toEqual([
      [{ limit: 2, offset: 0 }],
      [{ limit: 2, offset: 2 }],
    ])
    expect(list.refreshFailed.value).toBe(false)
    expect(list.loaded.value).toBe(3)
  })
  it('odświeżanie zachowuje wiersze i nie przywraca pierwszego loading', async () => {
    const fetchPage = vi.fn().mockResolvedValueOnce({ items: [{ id: 1 }], total: 1 })
    await render(fetchPage)
    let finish!: (value: PageResponse<{ id: number }>) => void
    fetchPage.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve
      }),
    )
    list.refresh()
    await flushPromises()
    expect(list.isRefreshing.value).toBe(true)
    expect(list.isPending.value).toBe(false)
    expect(list.items.value).toEqual([{ id: 1 }])
    finish({ items: [{ id: 1 }], total: 1 })
    await flushPromises()
    expect(list.isRefreshing.value).toBe(false)
  })
})
