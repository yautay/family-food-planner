import 'fake-indexeddb/auto'
import { webcrypto } from 'node:crypto'
import { TextEncoder } from 'node:util'
import { QueryClient } from '@tanstack/vue-query'
import { openDB } from 'idb'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, setUnauthorizedHandler } from '@/api/client'
import type * as ShoppingApi from '@/api/shoppingLists'
import type * as PublicApi from '@/api/publicList'
import * as storage from '@/lib/offline/db'
import {
  OfflineStorageError,
  readQueue,
  readSnapshot,
  resetOfflineDb,
  saveSnapshot,
  targetKey,
  type QueueTarget,
} from '@/lib/offline/db'
import { hydrateFromSnapshot } from '@/lib/offline/hydrate'
import { captureSessionGeneration } from '@/lib/sessionGeneration'
import {
  clearPrivateOfflineSession,
  confirmPrivateOfflineSession,
  getPrivateOfflineScope,
  restorePrivateOfflineSession,
} from '@/lib/offline/privateSession'
import { useAuthStore } from './auth'
import { useOfflineQueueStore } from './offlineQueue'

const { fetchCurrentUser, updateShoppingListItem, checkPublicListItem } = vi.hoisted(() => ({
  fetchCurrentUser: vi.fn(),
  updateShoppingListItem: vi.fn(),
  checkPublicListItem: vi.fn(),
}))
vi.mock('@/api/auth', () => ({ fetchCurrentUser, loginRequest: vi.fn(), logoutRequest: vi.fn() }))
vi.mock('@/api/shoppingLists', () => ({ updateShoppingListItem }))
vi.mock('@/api/publicList', async (original) => ({
  ...(await original<typeof PublicApi>()),
  checkPublicListItem,
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
let list: QueueTarget
const publicTarget: QueueTarget = { kind: 'public', token: 'a'.repeat(43) }
function gate() {
  let release!: () => void
  const promise = new Promise<void>((resolve) => {
    release = resolve
  })
  return { promise, release }
}
async function switchToB(): Promise<void> {
  clearPrivateOfflineSession()
  document.cookie = 'csrf_token=credential-b; Path=/'
  await confirmPrivateOfflineSession(B)
  useAuthStore().user = B
  useAuthStore().resolved = true
}
beforeEach(async () => {
  vi.stubGlobal('crypto', webcrypto)
  vi.stubGlobal('TextEncoder', TextEncoder)
  clearPrivateOfflineSession()
  document.cookie = 'csrf_token=credential-a; Path=/'
  history.replaceState({}, '', '/')
  await resetOfflineDb()
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.deleteDatabase('pasnik-offline')
    request.onsuccess = () => resolve()
    request.onerror = () => reject(request.error)
  })
  pinia = createPinia()
  setActivePinia(pinia)
  const scope = await confirmPrivateOfflineSession(A)
  list = { kind: 'list', listId: 7, scope: scope! }
  useAuthStore().user = A
  useAuthStore().resolved = true
  fetchCurrentUser.mockReset().mockResolvedValue(A)
  updateShoppingListItem.mockReset().mockResolvedValue({ id: 1, checked: true })
  checkPublicListItem.mockReset().mockResolvedValue({ id: 1, checked: true })
})
afterEach(async () => {
  setUnauthorizedHandler(undefined)
  disposePinia(pinia)
  clearPrivateOfflineSession()
  document.cookie = 'csrf_token=; Max-Age=0; Path=/'
  vi.unstubAllGlobals()
  await resetOfflineDb()
  history.replaceState({}, '', '/')
})

describe('scope prywatnej kolejki', () => {
  it.each([200, 403])(
    'zmiana roli podczas rzeczywistego PATCH%s zachowuje intencje, snapshot i próby do nowego potwierdzenia sesji',
    async (status) => {
      const actual = await vi.importActual<typeof ShoppingApi>('@/api/shoppingLists')
      const queue = useOfflineQueueStore()
      queue.markOffline()
      const snapshot = { name: 'Lista A', items: [{ id: 1, checked: true }] }
      await queue.enqueue(list, 1, true, snapshot)
      await queue.enqueue(list, 2, true, snapshot)
      const before = await readQueue()
      const sending = gate()
      const finish = gate()
      const fetch = vi.fn().mockImplementation(async () => {
        sending.release()
        await finish.promise
        return new Response(
          JSON.stringify(
            status === 200
              ? { id: 1, checked: true }
              : { error: { code: 'forbidden', message: 'Brak dostępu', details: {} } },
          ),
          {
            status,
            headers: { 'Content-Type': 'application/json' },
          },
        )
      })
      vi.stubGlobal('fetch', fetch)
      updateShoppingListItem.mockImplementation(actual.updateShoppingListItem)
      const notify = vi.fn()
      queue.subscribeToSync(list, notify)
      queue.online = true
      const flushing = queue.flush()
      await sending.promise
      const admin = { ...A, role: 'admin' as const }
      expect(useAuthStore().setUser(admin, captureSessionGeneration())).toBe(true)
      expect(getPrivateOfflineScope()).toBe(list.kind === 'list' ? list.scope : '')
      finish.release()
      expect(await flushing).toBe(0)
      expect(await readQueue()).toEqual(before)
      expect(await readSnapshot(targetKey(list))).toEqual(snapshot)
      expect(fetch).toHaveBeenCalledTimes(1)
      expect(queue.pendingCount).toBe(2)
      expect(queue.isOffline).toBe(false)
      expect(queue.errorFor(list)).toBeNull()
      expect(queue.needsReconciliation(list)).toBe(false)
      expect(notify).not.toHaveBeenCalled()

      const confirming = gate()
      const confirmed = gate()
      fetchCurrentUser.mockImplementationOnce(async () => {
        confirming.release()
        await confirmed.promise
        return admin
      })
      fetch.mockImplementation(
        async () =>
          new Response(JSON.stringify({ id: 1, checked: true }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
      )
      const resumed = queue.flush()
      await confirming.promise
      expect(fetch).toHaveBeenCalledTimes(1)
      expect(await readQueue()).toEqual(before)
      confirmed.release()
      expect(await resumed).toBe(2)
      expect(fetchCurrentUser).toHaveBeenCalledTimes(2)
      expect(fetch).toHaveBeenCalledTimes(3)
      expect(await readQueue()).toEqual([])
      expect(notify).toHaveBeenCalledTimes(1)
    },
  )

  it('awaria odczytu IDB nie zamienia znanych intencji w pustą, pozornie zapisaną kolejkę', async () => {
    const queue = useOfflineQueueStore()
    queue.markOffline()
    await queue.enqueue(list, 1, true)
    const read = storage.readQueue
    const spy = vi.spyOn(storage, 'readQueue').mockRejectedValue(new OfflineStorageError())
    try {
      queue.online = true
      expect(await queue.flush()).toBe(0)
      expect(queue.pendingCount).toBe(1)
      expect(queue.errorFor(list)).toContain('Nie udało się zapisać zmiany')
      expect(updateShoppingListItem).not.toHaveBeenCalled()
      spy.mockImplementation(read)
      await queue.refresh()
      expect(queue.pendingCount).toBe(1)
      expect(queue.errorFor(list)).toBeNull()
    } finally {
      spy.mockRestore()
    }
  })
  it.each(['list-snapshots', 'mutation-queue'])(
    'zmiana scope podczas zapisu %s wycofuje transakcję',
    async (storeName) => {
      const key = targetKey(list)
      const put = IDBObjectStore.prototype.put
      const spy = vi.spyOn(IDBObjectStore.prototype, 'put').mockImplementation(function (
        this: IDBObjectStore,
        ...args
      ) {
        const request = put.apply(this, args)
        if (this.name === storeName) clearPrivateOfflineSession()
        return request
      })
      try {
        if (storeName === 'list-snapshots')
          expect(await saveSnapshot(key, { name: 'Nieaktualny zapis A' })).toBe(false)
        else
          await expect(
            storage.enqueueCheck(list, 1, true, new Date(), { name: 'Nieaktualny zapis A' }),
          ).rejects.toBeInstanceOf(OfflineStorageError)
        const raw = await openDB('pasnik-offline', 1)
        try {
          expect(await raw.getAll('mutation-queue')).toEqual([])
          expect(await raw.getAll('list-snapshots')).toEqual([])
        } finally {
          raw.close()
        }
      } finally {
        spy.mockRestore()
      }
    },
  )

  it('wymusza rzeczywiste /me mimo resolved=true przed prywatną wysyłką', async () => {
    const queue = useOfflineQueueStore()
    queue.markOffline()
    await queue.enqueue(list, 1, true, { name: 'Lista A' })
    queue.online = true
    expect(await queue.flush()).toBe(1)
    expect(fetchCurrentUser).toHaveBeenCalledTimes(1)
    expect(updateShoppingListItem).toHaveBeenCalledTimes(1)
  })

  it('pure public replay nie pyta /me i nie wysyła zaległej prywatnej decyzji', async () => {
    const queue = useOfflineQueueStore()
    queue.markOffline()
    await queue.enqueue(list, 1, true)
    await queue.enqueue(publicTarget, 1, true)
    const raw = await openDB('pasnik-offline', 1)
    await raw.put('mutation-queue', {
      ...(await readQueue())[0]!,
      key: 'list:7#99',
      target: { kind: 'list', listId: 7 },
      itemId: 99,
    })
    raw.close()
    history.replaceState({}, '', `/l/${'a'.repeat(43)}`)
    queue.online = true
    expect(await queue.flush()).toBe(1)
    expect(fetchCurrentUser).not.toHaveBeenCalled()
    expect(updateShoppingListItem).not.toHaveBeenCalled()
    expect(checkPublicListItem).toHaveBeenCalledTimes(1)
    expect(await readQueue()).toHaveLength(2)
    expect(await readQueue()).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ target: list }),
        expect.objectContaining({ key: 'list:7#99' }),
      ]),
    )
  })

  it('B nie odczytuje ani nie replayuje A; legacy list:* pozostają w kwarantannie', async () => {
    const queue = useOfflineQueueStore()
    queue.markOffline()
    await queue.enqueue(list, 1, true, { name: 'Lista A' })
    const raw = await openDB('pasnik-offline', 1)
    const old = {
      ...(await readQueue())[0]!,
      key: 'list:7#9',
      target: { kind: 'list', listId: 7 },
      itemId: 9,
    }
    await raw.put('mutation-queue', old)
    await raw.put('list-snapshots', {
      key: 'list:7',
      payload: { name: 'Legacy A' },
      fetchedAt: '2030-01-01',
    })
    try {
      await switchToB()
      await queue.refresh()
      expect(queue.pendingCount).toBe(0)
      expect(await readSnapshot(targetKey(list))).toBeNull()
      expect(await readSnapshot('list:7')).toBeNull()
      queue.online = true
      expect(await queue.flush()).toBe(0)
      expect(fetchCurrentUser).not.toHaveBeenCalled()
      expect(updateShoppingListItem).not.toHaveBeenCalled()
      expect(await raw.get('mutation-queue', old.key)).toEqual(old)
      expect((await raw.getAll('mutation-queue')).length).toBe(2)
      expect(await raw.get('list-snapshots', 'list:7')).toBeDefined()
    } finally {
      raw.close()
    }
  })

  it('zmiana scope w trakcie pierwszego PATCH zatrzymuje drugi i zachowuje intencje A', async () => {
    const queue = useOfflineQueueStore()
    queue.markOffline()
    await queue.enqueue(list, 1, true)
    await queue.enqueue(list, 2, true)
    const sending = gate()
    const finish = gate()
    updateShoppingListItem.mockImplementationOnce(async () => {
      sending.release()
      await finish.promise
      return { id: 1, checked: true }
    })
    queue.online = true
    const flushing = queue.flush()
    await sending.promise
    await switchToB()
    finish.release()
    expect(await flushing).toBe(0)
    expect(updateShoppingListItem).toHaveBeenCalledTimes(1)
    expect(await readQueue()).toHaveLength(2)
    expect(queue.pendingCount).toBe(0)
  })

  it('cold marker bez potwierdzenia /me zachowuje kolejkę i nie wysyła offline', async () => {
    const queue = useOfflineQueueStore()
    queue.markOffline()
    await queue.enqueue(list, 1, true)
    await restorePrivateOfflineSession()
    fetchCurrentUser.mockRejectedValue(
      new ApiError(0, { code: 'network_error', message: 'Brak sieci', details: {} }),
    )
    queue.online = true
    expect(await queue.flush()).toBe(0)
    expect(updateShoppingListItem).not.toHaveBeenCalled()
    expect(queue.isOffline).toBe(true)
    expect(await readQueue()).toHaveLength(1)
    expect(useAuthStore().isAuthenticated).toBe(false)
    expect(useAuthStore().offlineSession).toBe(true)
  })

  it('401 podczas prywatnego PATCH zamyka sesję i nie przypisuje kolejki następnemu kontu', async () => {
    const actual = await vi.importActual<typeof ShoppingApi>('@/api/shoppingLists')
    const queue = useOfflineQueueStore()
    queue.markOffline()
    await queue.enqueue(list, 1, true)
    setUnauthorizedHandler(() => useAuthStore().clear())
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ error: { code: 'unauthorized', message: 'Brak sesji', details: {} } }),
            { status: 401, headers: { 'Content-Type': 'application/json' } },
          ),
        ),
    )
    updateShoppingListItem.mockImplementation(actual.updateShoppingListItem)
    queue.online = true
    expect(await queue.flush()).toBe(0)
    expect(useAuthStore().isAuthenticated).toBe(false)
    expect(getPrivateOfflineScope()).toBeNull()
    expect(await readQueue()).toHaveLength(1)
  })

  it('prywatne 404 unieważnia tylko konkretny snapshot i cel', async () => {
    const queue = useOfflineQueueStore()
    queue.markOffline()
    const other: QueueTarget = {
      ...list,
      kind: 'list',
      listId: 8,
      scope: list.kind === 'list' ? list.scope : '',
    }
    await queue.enqueue(list, 1, true, { name: 'Usunięta A7' })
    await saveSnapshot(targetKey(other), { name: 'Zachowana A8' })
    updateShoppingListItem.mockRejectedValue(
      new ApiError(404, { code: 'not_found', message: 'Nie znaleziono', details: {} }),
    )
    queue.online = true
    await queue.flush()
    expect(queue.isGone(list)).toBe(true)
    expect(queue.isGone(other)).toBe(false)
    expect(await readSnapshot(targetKey(list))).toBeNull()
    expect(await readSnapshot(targetKey(other))).toEqual({ name: 'Zachowana A8' })
  })

  it('brak IndexedDB nie udaje trwałego enqueue', async () => {
    const queue = useOfflineQueueStore()
    queue.markOffline()
    vi.stubGlobal('indexedDB', undefined)
    expect(await saveSnapshot(targetKey(list), { name: 'Nieutrwalona' })).toBe(false)
    await expect(queue.enqueue(list, 1, true, { name: 'Nieutrwalona' })).rejects.toBeInstanceOf(
      OfflineStorageError,
    )
    expect(queue.pendingCount).toBe(0)
    expect(updateShoppingListItem).not.toHaveBeenCalled()
  })

  it('stary odczyt IDB nie hydratuje cache po zmianie scope podczas await', async () => {
    await saveSnapshot(targetKey(list), { name: 'Prywatna A' })
    const loaded = gate()
    const finish = gate()
    const read = storage.readSnapshot
    vi.spyOn(storage, 'readSnapshot').mockImplementationOnce(async (key) => {
      const value = await read(key)
      loaded.release()
      await finish.promise
      return value
    })
    const client = new QueryClient()
    const hydrating = hydrateFromSnapshot(client, ['old-private'], targetKey(list))
    await loaded.promise
    await switchToB()
    finish.release()
    expect(await hydrating).toBe(false)
    expect(client.getQueryData(['old-private'])).toBeUndefined()
    client.clear()
  })
})
