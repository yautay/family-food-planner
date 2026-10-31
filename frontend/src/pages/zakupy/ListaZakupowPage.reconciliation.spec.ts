vi.mock('@/lib/offline/privateSession', () => ({
  getPrivateOfflineScope: () => 'test-scope',
  isPrivateOfflineScopeCurrent: (scope: string) => scope === 'test-scope',
  isPrivateOfflineScopeConfirmed: (scope: string) => scope === 'test-scope',
  subscribePrivateOfflineScope: () => () => {},
}))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    user: { id: 1 },
    household: null,
    isAuthenticated: true,
    offlineSession: false,
    ensureLoaded: vi.fn().mockResolvedValue(undefined),
    clear: vi.fn(),
  }),
}))
import 'fake-indexeddb/auto'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ShoppingListDetail, ShoppingListItem } from '@/api/shoppingLists'
import type * as ShoppingListsApi from '@/api/shoppingLists'
import { readQueue, readSnapshot, resetOfflineDb } from '@/lib/offline/db'
import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import { useOfflineQueueStore } from '@/stores/offlineQueue'
import ListaZakupowPage from './ListaZakupowPage.vue'

const { fetchShoppingList, updateShoppingListItem } = vi.hoisted(() => ({
  fetchShoppingList: vi.fn(),
  updateShoppingListItem: vi.fn(),
}))
vi.mock('@/api/shoppingLists', async (original) => ({
  ...(await original<typeof ShoppingListsApi>()),
  fetchShoppingList,
  updateShoppingListItem,
}))
vi.mock('@/api/stores', () => ({
  fetchStores: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  createStore: vi.fn(),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: '5' } }),
  useRouter: () => ({ push: vi.fn() }),
}))

function item(id: number, checked = false): ShoppingListItem {
  return {
    id,
    label: `Produkt ${id}`,
    category_id: 10,
    product_id: id,
    retail_product_id: null,
    needed_amount: '100',
    amount_unit: 'g',
    packages_count: null,
    package_size: null,
    leftover_amount: null,
    already_have: false,
    from_pantry_amount: null,
    checked,
    checked_at: null,
    received_at: null,
    position: id,
  }
}
function detail(): ShoppingListDetail {
  return {
    id: 5,
    generation_id: 3,
    name: 'Lista rekonsyliacji',
    round_name: null,
    store_id: null,
    store_name: null,
    expires_at: '2030-01-14T12:00:00Z',
    share: null,
    sections: [{ category_id: 10, category_name: 'Sypkie', items: [item(1), item(2)] }],
    created_at: '2030-01-06T12:00:00Z',
    updated_at: '2030-01-06T12:00:00Z',
  }
}
async function setup() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const queue = useOfflineQueueStore()
  queue.markOffline()
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, networkMode: 'always' },
      mutations: { networkMode: 'always' },
    },
  })
  const wrapper = mount(ListaZakupowPage, {
    global: {
      plugins: [pinia, [VueQueryPlugin, { queryClient: client }]],
      stubs: { RouterLink: { template: '<a><slot /></a>' } },
    },
  })
  await flushPromises()
  await wrapper.get('[data-testid="shopping-check-1"]').trigger('change')
  await vi.waitFor(() =>
    expect(queue.pendingFor({ kind: 'list', listId: 5, scope: 'test-scope' })).toBe(1),
  )
  return { queue, client, wrapper }
}

beforeEach(async () => {
  await resetOfflineDb()
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.deleteDatabase('pasnik-offline')
    request.onsuccess = () => resolve()
    request.onerror = () => reject(request.error)
  })
  vi.clearAllMocks()
  fetchShoppingList.mockReset().mockResolvedValue(detail())
  // Realny flush dostaje 200 z checked=false: starsza decyzja przegrała LWW.
  updateShoppingListItem
    .mockReset()
    .mockImplementation((_list, id) => Promise.resolve(item(id, id !== 1)))
})

describe('przyjęcie po rekonsyliacji kolejki', () => {
  it('zwykły udany refetch po błędzie zostawia osiągalne ponowienie potwierdzenia', async () => {
    const { queue, client, wrapper } = await setup()
    fetchShoppingList.mockRejectedValue(new Error('Pierwsza rekonsyliacja nie dotarła'))
    try {
      queue.online = true
      await queue.flush()
      await vi.waitFor(() =>
        expect(wrapper.find('[data-testid="lista-refresh-error"]').exists()).toBe(true),
      )
      const actual = detail()
      actual.sections[0]!.items[0]!.checked = true
      fetchShoppingList.mockResolvedValue(actual)
      // Takie odświeżenie może pochodzić np. z ShareListDialog. Nie jest
      // dedykowaną ścieżką reconcileList, ale usuwa błąd Query i jego Retry.
      await client.invalidateQueries({
        queryKey: [...queryKeys.shopping.list(5), 'private', 'test-scope'],
      })
      await flushPromises()
      expect(wrapper.find('[data-testid="lista-refresh-error"]').exists()).toBe(false)
      expect(queue.needsReconciliation({ kind: 'list', listId: 5, scope: 'test-scope' })).toBe(true)
      const retry = wrapper.get('[data-testid="lista-reconcile-retry"]')
      expect(retry.attributes('disabled')).toBeUndefined()
      await retry.trigger('click')
      await vi.waitFor(() =>
        expect(queue.needsReconciliation({ kind: 'list', listId: 5, scope: 'test-scope' })).toBe(
          false,
        ),
      )
      expect(
        wrapper.get('[data-testid="lista-accept-open"]').attributes('disabled'),
      ).toBeUndefined()
    } finally {
      wrapper.unmount()
      client.clear()
    }
  })

  it('odtwarza snapshot nowego kliknięcia po old422, gdy nowy online PATCH dopiero później wpada do kolejki', async () => {
    const { queue, client, wrapper } = await setup()
    let startedOld!: () => void
    const oldStarted = new Promise<void>((resolve) => {
      startedOld = resolve
    })
    let rejectOld!: () => void
    const finishOld = new Promise<void>((resolve) => {
      rejectOld = resolve
    })
    let startedNew!: () => void
    const newStarted = new Promise<void>((resolve) => {
      startedNew = resolve
    })
    let rejectNew!: () => void
    const finishNew = new Promise<void>((resolve) => {
      rejectNew = resolve
    })
    updateShoppingListItem
      .mockReset()
      .mockImplementationOnce(async () => {
        startedOld()
        await finishOld
        throw new ApiError(422, { code: 'validation_error', message: 'Old422', details: {} })
      })
      .mockImplementationOnce(async () => {
        startedNew()
        await finishNew
        throw new ApiError(0, { code: 'network_error', message: 'Network0', details: {} })
      })
    try {
      await vi.waitFor(() =>
        expect(
          wrapper.get('[data-testid="shopping-check-1"]').attributes('disabled'),
        ).toBeUndefined(),
      )
      queue.online = true
      const flushing = queue.flush()
      await oldStarted
      await wrapper.get('[data-testid="shopping-purchased-toggle"]').trigger('click')
      await wrapper.get('[data-testid="shopping-check-1"]').trigger('change')
      await newStarted
      await vi.waitFor(async () => {
        const snapshot = await readSnapshot<ShoppingListDetail>('private:test-scope:list:5')
        expect(snapshot?.sections[0]?.items[0]?.checked).toBe(false)
      })
      rejectOld()
      await flushing
      await flushPromises()
      expect(await readSnapshot('private:test-scope:list:5')).toBeNull()
      rejectNew()
      await vi.waitFor(() => expect(queue.pendingCount).toBe(1))
      expect((await readQueue())[0]?.checked).toBe(false)
      const restored = await readSnapshot<ShoppingListDetail>('private:test-scope:list:5')
      expect(restored?.sections[0]?.items[0]?.checked).toBe(false)
      expect(
        (wrapper.get('[data-testid="shopping-check-1"]').element as HTMLInputElement).checked,
      ).toBe(false)
    } finally {
      rejectOld()
      rejectNew()
      wrapper.unmount()
      client.clear()
    }
  })

  it('nie przyjmuje optimistic checked po 200 LWW, dopóki opóźniony GET nie został zastosowany', async () => {
    const { queue, client, wrapper } = await setup()
    let resolveGet!: (value: ShoppingListDetail) => void
    fetchShoppingList.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveGet = resolve
        }),
    )
    try {
      queue.online = true
      await queue.flush()
      await flushPromises()
      expect(queue.pendingCount).toBe(0)
      expect(
        (wrapper.get('[data-testid="shopping-check-1"]').element as HTMLInputElement).checked,
      ).toBe(true)
      expect(wrapper.get('[data-testid="lista-accept-open"]').attributes('disabled')).toBeDefined()
      resolveGet(detail())
      await vi.waitFor(() =>
        expect(queue.needsReconciliation({ kind: 'list', listId: 5, scope: 'test-scope' })).toBe(
          false,
        ),
      )
      await flushPromises()
      expect(
        (wrapper.get('[data-testid="shopping-check-1"]').element as HTMLInputElement).checked,
      ).toBe(false)
      // Po POTWIERDZONYM GET nowe, potwierdzone online odhaczenie jest przyjmowalne.
      await wrapper.get('[data-testid="shopping-check-2"]').trigger('change')
      await vi.waitFor(() =>
        expect(
          wrapper.get('[data-testid="lista-accept-open"]').attributes('disabled'),
        ).toBeUndefined(),
      )
    } finally {
      wrapper.unmount()
      client.clear()
    }
  })

  it('nie odblokowuje przyjęcia po błędzie GET ani po nowej intencji; ponowienie GET uzgadnia stan', async () => {
    const { queue, client, wrapper } = await setup()
    fetchShoppingList.mockRejectedValue(new Error('GET nie dotarł'))
    try {
      queue.online = true
      await queue.flush()
      await flushPromises()
      expect(queue.pendingCount).toBe(0)
      expect(wrapper.get('[data-testid="lista-refresh-error"]').text()).toContain(
        'Nie udało się odświeżyć',
      )
      expect(wrapper.get('[data-testid="lista-accept-open"]').attributes('disabled')).toBeDefined()
      await wrapper.get('[data-testid="shopping-check-2"]').trigger('change')
      await vi.waitFor(() =>
        expect(
          wrapper.get('[data-testid="shopping-check-2"]').attributes('disabled'),
        ).toBeUndefined(),
      )
      await vi.waitFor(() =>
        expect(wrapper.find('[data-testid="lista-refresh-error"]').exists()).toBe(true),
      )
      expect(wrapper.get('[data-testid="lista-accept-open"]').attributes('disabled')).toBeDefined()
      fetchShoppingList.mockResolvedValue(detail())
      await wrapper.get('[data-testid="lista-refresh-error"] button').trigger('click')
      await vi.waitFor(() =>
        expect(queue.needsReconciliation({ kind: 'list', listId: 5, scope: 'test-scope' })).toBe(
          false,
        ),
      )
      await flushPromises()
      expect(
        (wrapper.get('[data-testid="shopping-check-1"]').element as HTMLInputElement).checked,
      ).toBe(false)
    } finally {
      wrapper.unmount()
      client.clear()
    }
  })
})
