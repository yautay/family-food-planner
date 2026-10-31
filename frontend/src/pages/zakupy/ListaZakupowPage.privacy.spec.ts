import 'fake-indexeddb/auto'
import { webcrypto } from 'node:crypto'
import { TextEncoder } from 'node:util'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import type { ShoppingListDetail, ShoppingListItem } from '@/api/shoppingLists'
import type * as ShoppingApi from '@/api/shoppingLists'
import { readSnapshot, resetOfflineDb } from '@/lib/offline/db'
import {
  clearPrivateOfflineSession,
  confirmPrivateOfflineSession,
  subscribePrivateOfflineScope,
} from '@/lib/offline/privateSession'
import { useAuthStore } from '@/stores/auth'
import ListaZakupowPage from './ListaZakupowPage.vue'

const { fetchShoppingList, updateShoppingListItem } = vi.hoisted(() => ({
  fetchShoppingList: vi.fn(),
  updateShoppingListItem: vi.fn(),
}))
vi.mock('@/api/shoppingLists', async (original) => ({
  ...(await original<typeof ShoppingApi>()),
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
const A = {
  id: 1,
  email: 'a@example.com',
  display_name: 'A',
  role: 'user' as const,
  ui_settings: {},
  household: null,
}
const B = { ...A, id: 2, email: 'b@example.com', display_name: 'B' }
let pinia: ReturnType<typeof createPinia>
let scopeA: string
function item(checked = false): ShoppingListItem {
  return {
    id: 1,
    label: 'Produkt',
    category_id: 10,
    product_id: 1,
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
    position: 0,
  }
}
function detail(name: string): ShoppingListDetail {
  return {
    id: 5,
    generation_id: 1,
    name,
    round_name: null,
    store_id: null,
    store_name: null,
    expires_at: '2030-01-01T00:00:00Z',
    share: null,
    sections: [{ category_id: 10, category_name: 'Sypkie', items: [item()] }],
    created_at: '2030-01-01T00:00:00Z',
    updated_at: '2030-01-01T00:00:00Z',
  }
}
function setup() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, networkMode: 'always' },
      mutations: { networkMode: 'always' },
    },
  })
  const unsubscribe = subscribePrivateOfflineScope(() => client.clear())
  const wrapper = mount(ListaZakupowPage, {
    global: {
      plugins: [pinia, [VueQueryPlugin, { queryClient: client }]],
      stubs: { RouterLink: { template: '<a><slot /></a>' } },
    },
  })
  return {
    client,
    wrapper,
    finish: () => {
      wrapper.unmount()
      unsubscribe()
      client.clear()
    },
  }
}
async function switchToB(): Promise<string> {
  clearPrivateOfflineSession()
  document.cookie = 'csrf_token=credential-b; Path=/'
  const scope = await confirmPrivateOfflineSession(B)
  useAuthStore().user = B
  useAuthStore().resolved = true
  return scope!
}
beforeEach(async () => {
  vi.stubGlobal('crypto', webcrypto)
  vi.stubGlobal('TextEncoder', TextEncoder)
  clearPrivateOfflineSession()
  document.cookie = 'csrf_token=credential-a; Path=/'
  await resetOfflineDb()
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.deleteDatabase('pasnik-offline')
    request.onsuccess = () => resolve()
    request.onerror = () => reject(request.error)
  })
  pinia = createPinia()
  setActivePinia(pinia)
  scopeA = (await confirmPrivateOfflineSession(A))!
  useAuthStore().user = A
  useAuthStore().resolved = true
  fetchShoppingList.mockReset()
  updateShoppingListItem.mockReset()
})
afterEach(async () => {
  disposePinia(pinia)
  clearPrivateOfflineSession()
  document.cookie = 'csrf_token=; Max-Age=0; Path=/'
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  await resetOfflineDb()
})

describe('asynchroniczne odpowiedzi prywatnej listy', () => {
  it('aktualne 404 usuwa cache/snapshot celu i pokazuje stan końcowy zamiast spinnera', async () => {
    fetchShoppingList.mockRejectedValue(
      new ApiError(404, { code: 'not_found', message: 'Nie znaleziono', details: {} }),
    )
    const { client, wrapper, finish } = setup()
    try {
      await vi.waitFor(() =>
        expect(wrapper.find('[data-testid="lista-zakupowa-brak"]').exists()).toBe(true),
      )
      expect(wrapper.find('[data-testid="lista-nazwa"]').exists()).toBe(false)
      expect(await readSnapshot(`private:${scopeA}:list:5`)).toBeNull()
      expect(
        client.getQueryData([...queryKeys.shopping.list(5), 'private', scopeA]),
      ).toBeUndefined()
    } finally {
      finish()
    }
  })
  it.each(['success', '401', '404'])(
    'spóźniony GET A (%s) nie renderuje/persystuje A ani nie unieważnia B',
    async (outcome) => {
      let resolveA!: (value: ShoppingListDetail) => void
      let rejectA!: (error: unknown) => void
      fetchShoppingList
        .mockImplementationOnce(
          () =>
            new Promise((resolve, reject) => {
              resolveA = resolve
              rejectA = reject
            }),
        )
        .mockResolvedValue(detail('Lista B'))
      const { client, wrapper, finish } = setup()
      try {
        await vi.waitFor(() => expect(fetchShoppingList).toHaveBeenCalledTimes(1))
        const scopeB = await switchToB()
        await vi.waitFor(() =>
          expect(wrapper.get('[data-testid="lista-nazwa"]').text()).toBe('Lista B'),
        )
        if (outcome === 'success') resolveA(detail('Prywatna lista A'))
        else
          rejectA(
            new ApiError(Number(outcome), { code: 'denied', message: 'Stara odmowa', details: {} }),
          )
        await flushPromises()
        expect(wrapper.text()).not.toContain('Prywatna lista A')
        expect(
          client.getQueryData([...queryKeys.shopping.list(5), 'private', scopeA]),
        ).toBeUndefined()
        expect(useAuthStore().user?.id).toBe(B.id)
        await vi.waitFor(async () =>
          expect((await readSnapshot<ShoppingListDetail>(`private:${scopeB}:list:5`))?.name).toBe(
            'Lista B',
          ),
        )
      } finally {
        finish()
      }
    },
  )

  it.each(['success', 'reject'])(
    'stary PATCH A (%s) nie aplikuje sukcesu ani rollbacku do cache B',
    async (outcome) => {
      fetchShoppingList
        .mockResolvedValueOnce(detail('Lista A'))
        .mockResolvedValue(detail('Lista B'))
      let resolvePatch!: (value: ShoppingListItem) => void
      let rejectPatch!: (error: unknown) => void
      updateShoppingListItem.mockImplementation(
        () =>
          new Promise((resolve, reject) => {
            resolvePatch = resolve
            rejectPatch = reject
          }),
      )
      const { client, wrapper, finish } = setup()
      try {
        await vi.waitFor(() =>
          expect(wrapper.find('[data-testid="shopping-check-1"]').exists()).toBe(true),
        )
        await wrapper.get('[data-testid="shopping-check-1"]').trigger('change')
        await vi.waitFor(() => expect(updateShoppingListItem).toHaveBeenCalledTimes(1))
        const scopeB = await switchToB()
        await vi.waitFor(() =>
          expect(wrapper.get('[data-testid="lista-nazwa"]').text()).toBe('Lista B'),
        )
        if (outcome === 'success') resolvePatch(item(true))
        else
          rejectPatch(
            new ApiError(422, { code: 'validation_error', message: 'Stara odmowa A', details: {} }),
          )
        await flushPromises()
        expect(
          (wrapper.get('[data-testid="shopping-check-1"]').element as HTMLInputElement).checked,
        ).toBe(false)
        expect(wrapper.text()).not.toContain('Stara odmowa A')
        expect(
          client.getQueryData([...queryKeys.shopping.list(5), 'private', scopeA]),
        ).toBeUndefined()
        const actual = client.getQueryData<ShoppingListDetail>([
          ...queryKeys.shopping.list(5),
          'private',
          scopeB,
        ])
        expect(actual?.sections[0]?.items[0]?.checked).toBe(false)
      } finally {
        finish()
      }
    },
  )

  it('bez localStorage potwierdzona sesja online nadal odczytuje i odhacza, z jawnym brakiem offline', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('Storage zablokowany')
    })
    fetchShoppingList.mockResolvedValue(detail('Lista online'))
    updateShoppingListItem.mockResolvedValue(item(true))
    const { wrapper, finish } = setup()
    try {
      await vi.waitFor(() =>
        expect(wrapper.get('[data-testid="lista-nazwa"]').text()).toBe('Lista online'),
      )
      expect(useAuthStore().isAuthenticated).toBe(true)
      expect(wrapper.get('[data-testid="lista-storage-error"]').text()).toContain(
        'offline jest niedostępny',
      )
      await wrapper.get('[data-testid="shopping-check-1"]').trigger('change')
      await vi.waitFor(() => expect(updateShoppingListItem).toHaveBeenCalledTimes(1))
      await flushPromises()
      expect(
        (wrapper.get('[data-testid="shopping-check-1"]').element as HTMLInputElement).checked,
      ).toBe(true)
    } finally {
      finish()
    }
  })
})
