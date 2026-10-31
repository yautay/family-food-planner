import 'fake-indexeddb/auto'
import { webcrypto } from 'node:crypto'
import { TextEncoder } from 'node:util'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CurrentUser } from '@/api/auth'
import { readQueue, resetOfflineDb, type QueueTarget } from '@/lib/offline/db'
import {
  clearPrivateOfflineSession,
  confirmPrivateOfflineSession,
  getPrivateOfflineScope,
} from '@/lib/offline/privateSession'
import { captureSessionGeneration } from '@/lib/sessionGeneration'
import { useAuthStore } from './auth'
import { useOfflineQueueStore } from './offlineQueue'

// Prawdziwe auth, klient HTTP, sync i IDB; zastępujemy tylko granicę fetch.
const A: CurrentUser = {
  id: 1,
  email: 'a@example.com',
  display_name: 'A',
  role: 'user',
  ui_settings: {},
  household: null,
}
const B: CurrentUser = { ...A, id: 2, email: 'b@example.com', display_name: 'B' }
const publicTarget: QueueTarget = { kind: 'public', token: 'a'.repeat(43) }
const fetchMock = vi.fn<typeof fetch>()
let pinia: ReturnType<typeof createPinia>
let list: QueueTarget

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function gate() {
  let release!: () => void
  const promise = new Promise<void>((resolve) => {
    release = resolve
  })
  return { promise, release }
}

beforeEach(async () => {
  // IDB używa prawdziwego setImmediate; kontrolujemy tylko backoff kolejki.
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  vi.stubGlobal('crypto', webcrypto)
  vi.stubGlobal('TextEncoder', TextEncoder)
  vi.stubGlobal('fetch', fetchMock)
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
  fetchMock.mockReset().mockImplementation(async (url) => {
    return response(String(url).endsWith('/auth/me') ? A : { id: 1, checked: true })
  })
})

afterEach(async () => {
  vi.clearAllTimers()
  vi.useRealTimers()
  disposePinia(pinia)
  clearPrivateOfflineSession()
  document.cookie = 'csrf_token=; Max-Age=0; Path=/'
  vi.unstubAllGlobals()
  await resetOfflineDb()
  history.replaceState({}, '', '/')
})

describe('odzyskanie sieci przez potwierdzony transport kolejki', () => {
  it.each(['private', 'public'])(
    'udany %s replay bez zdarzenia online odblokowuje kolejne enqueue',
    async (kind) => {
      const target = kind === 'private' ? list : publicTarget
      if (kind === 'public') history.replaceState({}, '', `/l/${publicTarget.token}`)
      const queue = useOfflineQueueStore()
      queue.markOffline()
      await queue.enqueue(target, 1, true)
      expect(fetchMock).not.toHaveBeenCalled()

      expect(await queue.flush()).toBe(1)
      expect(queue.online).toBe(true)
      expect(queue.isOffline).toBe(false)
      expect(await readQueue()).toEqual([])
      const firstRequests = fetchMock.mock.calls.map(([url]) => String(url))
      expect(firstRequests).toEqual(
        kind === 'private'
          ? ['/api/v1/auth/me', '/api/v1/shopping/lists/7/items/1']
          : [`/api/v1/public/lists/${publicTarget.token}/items/1`],
      )

      await queue.enqueue(target, 2, false)
      await vi.waitFor(() => expect(queue.pendingCount).toBe(0))
      expect(fetchMock).toHaveBeenCalledTimes(kind === 'private' ? 4 : 2)
      const [, request] = fetchMock.mock.calls.at(-1)!
      expect(request?.method).toBe('PATCH')
      expect(JSON.parse(String(request?.body))).toMatchObject({ checked: false })
      expect(queue.isOffline).toBe(false)
    },
  )

  it.each(['validation', 'replay'])(
    'błąd transportu przy %s pozostawia offline i nie zużywa prób',
    async (stage) => {
      const queue = useOfflineQueueStore()
      queue.markOffline()
      await queue.enqueue(list, 1, true)
      const before = await readQueue()
      fetchMock.mockImplementation(async (url) => {
        if (stage === 'replay' && String(url).endsWith('/auth/me')) return response(A)
        throw new TypeError('Brak sieci')
      })

      expect(await queue.flush()).toBe(0)
      expect(queue.isOffline).toBe(true)
      expect(await readQueue()).toEqual(before)
      expect(fetchMock).toHaveBeenCalledTimes(stage === 'validation' ? 1 : 2)
    },
  )

  it.each(['generation', 'account'])(
    'spóźniony PATCH po zmianie %s nie podnosi statusu nowej sesji',
    async (change) => {
      const queue = useOfflineQueueStore()
      queue.markOffline()
      await queue.enqueue(list, 1, true)
      const before = await readQueue()
      const sending = gate()
      const finish = gate()
      fetchMock.mockImplementation(async (url) => {
        if (String(url).endsWith('/auth/me')) return response(A)
        sending.release()
        await finish.promise
        return response({ id: 1, checked: true })
      })

      const flushing = queue.flush()
      await sending.promise
      if (change === 'generation') {
        expect(useAuthStore().setUser({ ...A, role: 'admin' }, captureSessionGeneration())).toBe(
          true,
        )
        expect(getPrivateOfflineScope()).toBe(list.kind === 'list' ? list.scope : '')
      } else {
        useAuthStore().clear()
        document.cookie = 'csrf_token=credential-b; Path=/'
        await confirmPrivateOfflineSession(B)
        useAuthStore().user = B
        useAuthStore().resolved = true
      }
      finish.release()

      expect(await flushing).toBe(0)
      expect(queue.isOffline).toBe(true)
      expect(await readQueue()).toEqual(before)
      expect(queue.needsReconciliation(list)).toBe(false)
      expect(fetchMock).toHaveBeenCalledTimes(2)
    },
  )
})
