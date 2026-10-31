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
import { openDB } from 'idb'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  enqueueCheck,
  readQueue,
  readSnapshot,
  rejectQueuedIfUnchanged,
  resetOfflineDb,
  saveSnapshot,
  targetKey,
  type QueueTarget,
} from './db'

beforeEach(async () => {
  await resetOfflineDb()
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.deleteDatabase('pasnik-offline')
    request.onsuccess = () => resolve()
    request.onerror = () => reject(request.error)
  })
})

const targets: QueueTarget[] = [
  { kind: 'list', listId: 7, scope: 'test-scope' },
  { kind: 'public', token: 'a'.repeat(43) },
]

describe('terminalne odrzucenie IndexedDB', () => {
  it.each(targets)('usuwa tylko aktualną decyzję i jej snapshot ($kind)', async (target) => {
    await enqueueCheck(target, 1, true, new Date('2030-01-01T00:00:00Z'))
    const [entry] = await readQueue()
    await saveSnapshot(targetKey(target), { checked: true })
    expect(await rejectQueuedIfUnchanged(entry!)).toBe(true)
    expect(await readQueue()).toEqual([])
    expect(await readSnapshot(targetKey(target))).toBeNull()
  })

  it.each(targets)('stara odmowa zachowuje nowszy wpis i snapshot ($kind)', async (target) => {
    const time = new Date('2030-01-01T00:00:00Z')
    await enqueueCheck(target, 1, true, time)
    const [old] = await readQueue()
    // Nawet przy tej samej milisekundzie zmienione checked rozróżnia decyzję.
    await enqueueCheck(target, 1, false, time)
    await saveSnapshot(targetKey(target), { checked: false, name: 'Nowsza decyzja' })
    expect(await rejectQueuedIfUnchanged(old!)).toBe(false)
    expect(await readQueue()).toEqual([expect.objectContaining({ checked: false })])
    expect(await readSnapshot(targetKey(target))).toEqual({
      checked: false,
      name: 'Nowsza decyzja',
    })
  })

  it('inna transakcja nie widzi ack bez unieważnienia snapshotu', async () => {
    const target = targets[0]!
    await enqueueCheck(target, 1, true, new Date('2030-01-01T00:00:00Z'))
    const [entry] = await readQueue()
    await saveSnapshot(targetKey(target), { checked: true })
    const observer = await openDB('pasnik-offline', 1)
    let observed: Promise<unknown[]> | undefined
    const remove = IDBObjectStore.prototype.delete
    const spy = vi.spyOn(IDBObjectStore.prototype, 'delete').mockImplementation(function (
      this: IDBObjectStore,
      key,
    ) {
      const request = remove.call(this, key)
      if (this.name === 'mutation-queue' && observed === undefined) {
        // Prawdziwy konkurujący odczyt uruchamiamy na granicy ack. Czeka na
        // istniejącą transakcję, nie na arbitralny timer ani atrapę storage'u.
        const transaction = observer.transaction(['mutation-queue', 'list-snapshots'])
        observed = Promise.all([
          transaction.objectStore('mutation-queue').get(entry!.key),
          transaction.objectStore('list-snapshots').get(targetKey(target)),
        ])
      }
      return request
    })
    try {
      expect(await rejectQueuedIfUnchanged(entry!)).toBe(true)
      expect(observed).toBeDefined()
      expect(await observed).toEqual([undefined, undefined])
    } finally {
      spy.mockRestore()
      observer.close()
    }
  })
})
