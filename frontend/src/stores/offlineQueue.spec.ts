/**
 * Kolejka offline — pięć scenariuszy wymaganych przez ADR-009 (karta B12 §Tests).
 *
 * Testujemy PRAWDZIWE IndexedDB (`fake-indexeddb`), a nie atrapę magazynu:
 * deduplikacja per pozycja i kolejność wysyłki wynikają z kluczy `db.ts`,
 * więc atrapa sprawdzałaby wyłącznie samą siebie. Zamockowane są tylko dwie
 * warstwy transportu (`shoppingLists`, `publicList`) — tam interesuje nas,
 * CO poleciało na serwer, a nie jak. Testy wyścigu dodatkowo wstrzymują
 * zakończenie prawdziwej operacji storage'u bramką Promise — bez opóźnień
 * zależnych od szybkości maszyny i bez zastępowania zawartości IndexedDB.
 *
 * Zegar: `checked_at` musi być w czasie SERWERA (`clock.ts`), więc scenariusz
 * korekty ustawia rozjechany zegar klienta i sprawdza wartość po korekcie.
 */

import 'fake-indexeddb/auto'

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type * as PublicListApi from '@/api/publicList'

import { ApiError } from '@/api/client'
import { PublicListRequestError, PublicListUnavailableError } from '@/api/publicList'
import * as offlineClock from '@/lib/offline/clock'
import { recordServerDate, resetClockSkew } from '@/lib/offline/clock'
import * as offlineDb from '@/lib/offline/db'
import {
  readQueue,
  readSnapshot,
  resetOfflineDb,
  saveSnapshot,
  targetKey,
  type QueueTarget,
} from '@/lib/offline/db'
import { useOfflineQueueStore } from '@/stores/offlineQueue'

const { updateShoppingListItem } = vi.hoisted(() => ({ updateShoppingListItem: vi.fn() }))
const { checkPublicListItem } = vi.hoisted(() => ({ checkPublicListItem: vi.fn() }))

vi.mock('@/api/shoppingLists', () => ({ updateShoppingListItem }))
vi.mock('@/api/publicList', async () => {
  const actual = await vi.importActual<typeof PublicListApi>('@/api/publicList')
  return { ...actual, checkPublicListItem }
})

const LIST: QueueTarget = { kind: 'list', listId: 7 }
const PUBLIC: QueueTarget = { kind: 'public', token: 'a'.repeat(43) }

function gate() {
  let release!: () => void
  const promise = new Promise<void>((resolve) => {
    release = resolve
  })
  return { promise, release }
}

/** Czyste IndexedDB przed każdym testem — kolejka przeżywa reload, więc i testy. */
async function wipeDatabase(): Promise<void> {
  // Otwarte połączenie blokuje usunięcie bazy — najpierw je zamykamy.
  await resetOfflineDb()
  await new Promise<void>((resolve) => {
    const request = indexedDB.deleteDatabase('pasnik-offline')
    request.onsuccess = () => resolve()
    request.onerror = () => resolve()
    request.onblocked = () => resolve()
  })
}

beforeEach(async () => {
  await wipeDatabase()
  setActivePinia(createPinia())
  resetClockSkew()
  updateShoppingListItem.mockReset()
  checkPublicListItem.mockReset()
})

describe('kolejka offline', () => {
  it.each([
    { status: 200, nextChecked: false, sameTime: false },
    { status: 200, nextChecked: false, sameTime: true },
    { status: 200, nextChecked: true, sameTime: false },
    { status: 422, nextChecked: false, sameTime: true },
  ])(
    'odpowiedź $status nie usuwa nowszej decyzji tej samej pozycji (checked=$nextChecked, ten sam czas=$sameTime)',
    async ({ status, nextChecked, sameTime }) => {
      const firstTime = new Date('2026-10-30T12:00:00.000Z')
      const nextTime = new Date(firstTime.getTime() + (sameTime ? 0 : 1))
      vi.spyOn(offlineClock, 'nowWithSkew')
        .mockReturnValueOnce(firstTime)
        .mockReturnValueOnce(nextTime)
      const store = useOfflineQueueStore()
      store.markOffline()
      await store.enqueue(PUBLIC, 1, true)
      const sending = gate()
      const finishSend = gate()
      checkPublicListItem.mockImplementationOnce(async () => {
        sending.release()
        await finishSend.promise
        if (status !== 200) {
          throw new PublicListRequestError(status)
        }
        return { id: 1, checked: true }
      })
      checkPublicListItem.mockResolvedValue({ id: 1, checked: nextChecked })

      store.markOnline()
      await sending.promise
      await store.enqueue(PUBLIC, 1, nextChecked)
      expect(store.pendingCount).toBe(1)
      expect(checkPublicListItem).toHaveBeenCalledTimes(1)
      finishSend.release()

      await vi.waitFor(() => {
        expect(checkPublicListItem).toHaveBeenCalledTimes(2)
        expect(store.pendingCount).toBe(0)
        expect(store.flushing).toBe(false)
      })
      expect(checkPublicListItem.mock.calls.map((call) => [call[2], call[3]])).toEqual([
        [true, firstTime.toISOString()],
        [nextChecked, nextTime.toISOString()],
      ])
      expect(await readQueue()).toEqual([])
    },
  )

  it.each([
    { status: 429, nextChecked: false, sameTime: false },
    { status: 503, nextChecked: false, sameTime: true },
    { status: 429, nextChecked: true, sameTime: false },
  ])(
    'odmowa $status nie zwiększa prób nowej decyzji tej samej pozycji (checked=$nextChecked, ten sam czas=$sameTime)',
    async ({ status, nextChecked, sameTime }) => {
      const firstTime = new Date('2026-10-30T12:00:00.000Z')
      const nextTime = new Date(firstTime.getTime() + (sameTime ? 0 : 1))
      vi.spyOn(offlineClock, 'nowWithSkew')
        .mockReturnValueOnce(firstTime)
        .mockReturnValueOnce(nextTime)
      const store = useOfflineQueueStore()
      store.markOffline()
      await store.enqueue(PUBLIC, 1, true)
      const sending = gate()
      const finishSend = gate()
      checkPublicListItem.mockImplementationOnce(async () => {
        sending.release()
        await finishSend.promise
        throw new PublicListRequestError(status)
      })
      const timers = vi.spyOn(globalThis, 'setTimeout')

      store.online = true
      const flushing = store.flush()
      await sending.promise
      await store.enqueue(PUBLIC, 1, nextChecked)
      finishSend.release()
      expect(await flushing).toBe(0)
      expect(store.flushing).toBe(false)
      expect(checkPublicListItem).toHaveBeenCalledTimes(1)
      const retryIndex = timers.mock.calls.findIndex((args) => args[1] === 15_000)
      expect(retryIndex).not.toBe(-1)
      clearTimeout(timers.mock.results[retryIndex]?.value as ReturnType<typeof setTimeout>)
      expect(await readQueue()).toEqual([
        expect.objectContaining({
          checked: nextChecked,
          checkedAt: nextTime.toISOString(),
          attempts: 0,
        }),
      ])
      expect(store.pendingCount).toBe(1)
      expect(store.isOffline).toBe(false)
    },
  )

  it('wysyła publiczne odhaczenie zapisane dopiero po zakończeniu flush online', async () => {
    const store = useOfflineQueueStore()
    store.markOffline()
    checkPublicListItem.mockResolvedValue({ id: 1, checked: false })

    const write = gate()
    const enqueueCheck = offlineDb.enqueueCheck
    vi.spyOn(offlineDb, 'enqueueCheck').mockImplementationOnce(async (...args) => {
      await write.promise
      await enqueueCheck(...args)
    })

    // UI już pokazał optimistic odznaczenie, ale zapis IndexedDB jeszcze trwa.
    const enqueueing = store.enqueue(PUBLIC, 1, false)
    store.markOnline()
    await vi.waitFor(() => expect(store.flushing).toBe(false))
    expect(checkPublicListItem).not.toHaveBeenCalled()

    write.release()
    await enqueueing

    await vi.waitFor(() => {
      expect(checkPublicListItem).toHaveBeenCalledTimes(1)
      expect(store.pendingCount).toBe(0)
      expect(store.flushing).toBe(false)
    })
    expect(checkPublicListItem).toHaveBeenCalledWith(PUBLIC.token, 1, false, expect.any(String))
    expect(await readQueue()).toEqual([])
  })

  it('wysyła nowy wpis spoza migawki trwającego flush, nadal sekwencyjnie', async () => {
    const store = useOfflineQueueStore()
    store.markOffline()
    await store.enqueue(PUBLIC, 1, true)
    const sending = gate()
    const finishSend = gate()
    checkPublicListItem.mockImplementationOnce(async () => {
      sending.release()
      await finishSend.promise
      return { id: 1, checked: true }
    })
    checkPublicListItem.mockResolvedValue({ id: 2, checked: false })

    store.markOnline()
    await sending.promise
    await store.enqueue(PUBLIC, 2, false)
    expect(checkPublicListItem).toHaveBeenCalledTimes(1)
    finishSend.release()

    await vi.waitFor(() => {
      expect(checkPublicListItem).toHaveBeenCalledTimes(2)
      expect(store.pendingCount).toBe(0)
      expect(store.flushing).toBe(false)
    })
    expect(checkPublicListItem.mock.calls.map((call) => call[1])).toEqual([1, 2])
    expect(await readQueue()).toEqual([])
  })

  it('odzyskuje wpis zapisany po ostatniej migawce kończącego się flush', async () => {
    const store = useOfflineQueueStore()
    store.markOffline()
    checkPublicListItem.mockResolvedValue({ id: 1, checked: false })
    const snapshotTaken = gate()
    const finishRefresh = gate()
    const read = offlineDb.readQueue
    let reads = 0
    vi.spyOn(offlineDb, 'readQueue').mockImplementation(async () => {
      const rows = await read()
      reads += 1
      if (reads === 2) {
        // Drugi odczyt to końcowy refresh pustego flush; migawka już powstała.
        snapshotTaken.release()
        await finishRefresh.promise
      }
      return rows
    })

    store.markOnline()
    await snapshotTaken.promise
    await store.enqueue(PUBLIC, 1, false)
    expect(store.pendingCount).toBe(1)
    expect(checkPublicListItem).not.toHaveBeenCalled()
    finishRefresh.release()

    await vi.waitFor(() => {
      expect(checkPublicListItem).toHaveBeenCalledTimes(1)
      expect(store.pendingCount).toBe(0)
      expect(store.flushing).toBe(false)
    })
    expect(await readQueue()).toEqual([])
  })

  it.each([0, 429, 503])(
    'nowy wpis podczas flush zakończonego statusem %i nie omija zatrzymania i backoffu',
    async (status) => {
      const store = useOfflineQueueStore()
      store.markOffline()
      await store.enqueue(PUBLIC, 1, true)
      const sending = gate()
      const finishSend = gate()
      checkPublicListItem.mockImplementationOnce(async () => {
        sending.release()
        await finishSend.promise
        throw new PublicListRequestError(status)
      })
      const timers = vi.spyOn(globalThis, 'setTimeout')

      store.online = true
      const flushing = store.flush()
      await sending.promise
      await store.enqueue(PUBLIC, 2, false)
      finishSend.release()
      expect(await flushing).toBe(0)

      // Pobudka z enqueue NIE może uruchomić drugiego flush po odmowie/braku sieci.
      expect(store.flushing).toBe(false)
      expect(checkPublicListItem).toHaveBeenCalledTimes(1)
      expect(store.isOffline).toBe(status === 0)
      expect(store.pendingCount).toBe(2)
      expect((await readQueue()).map((entry) => entry.attempts)).toEqual([status === 0 ? 0 : 1, 0])

      // Również kolejny zapis po zakończeniu flush nie skraca backoffu 15 s.
      await store.enqueue(PUBLIC, 3, true)
      expect(store.flushing).toBe(false)
      expect(checkPublicListItem).toHaveBeenCalledTimes(1)
      const retries = timers.mock.calls
        .map((args, index) => ({ args, result: timers.mock.results[index] }))
        .filter(({ args }) => args[1] === 15_000)
      expect(retries).toHaveLength(1)
      for (const { result } of retries) {
        // Timer sprawdzony; nie może wrócić do starego store w kolejnym teście.
        clearTimeout(result?.value as ReturnType<typeof setTimeout>)
      }
    },
  )

  it('po odzyskaniu sieci wysyła zaległe odhaczenia z checked_at i czyści kolejkę', async () => {
    const store = useOfflineQueueStore()
    const invalidate = vi.fn()
    store.subscribeToSync(LIST, invalidate)
    store.markOffline()

    await store.enqueue(LIST, 1, true)
    await store.enqueue(LIST, 2, true)
    await store.enqueue(LIST, 3, true)
    expect(store.pendingCount).toBe(3)
    expect(updateShoppingListItem).not.toHaveBeenCalled()

    updateShoppingListItem.mockResolvedValue({ id: 1, checked: true })
    store.online = true
    const sent = await store.flush()

    expect(sent).toBe(3)
    expect(updateShoppingListItem).toHaveBeenCalledTimes(3)
    for (const call of updateShoppingListItem.mock.calls) {
      expect(call[0]).toBe(7)
      expect(typeof call[2].checked_at).toBe('string')
    }
    // Kolejność wysyłki = kolejność odhaczania (pozycje 1, 2, 3).
    expect(updateShoppingListItem.mock.calls.map((call) => call[1])).toEqual([1, 2, 3])
    expect(await readQueue()).toEqual([])
    expect(store.pendingCount).toBe(0)
    expect(invalidate).toHaveBeenCalledTimes(1)
  })

  it('podwójne odhaczenie tej samej pozycji daje JEDEN PATCH z ostatnim stanem', async () => {
    const store = useOfflineQueueStore()
    store.markOffline()

    await store.enqueue(LIST, 42, true)
    await store.enqueue(LIST, 42, false)

    expect(store.pendingCount).toBe(1)
    updateShoppingListItem.mockResolvedValue({ id: 42, checked: false })
    store.online = true
    await store.flush()

    expect(updateShoppingListItem).toHaveBeenCalledTimes(1)
    expect(updateShoppingListItem.mock.calls[0]?.[2].checked).toBe(false)
  })

  it('konflikt LWW: serwer odrzuca starsze odhaczenie, a klient przyjmuje jego stan', async () => {
    const store = useOfflineQueueStore()
    const invalidate = vi.fn()
    store.subscribeToSync(LIST, invalidate)
    store.markOffline()
    await store.enqueue(LIST, 5, true)

    // Serwer zwraca 200 ze stanem AKTUALNYM (jego `checked_at` jest młodszy),
    // czyli nasze odhaczenie przegrało. Dla kolejki to sukces: wpis jest
    // załatwiony, a ponawianie nigdy by go nie „przepchnęło".
    updateShoppingListItem.mockResolvedValue({ id: 5, checked: false })
    store.online = true
    const sent = await store.flush()

    expect(sent).toBe(1)
    expect(await readQueue()).toEqual([])
    // Invalidate jest tu KLUCZOWE: bez niego UI zostałby z własnym, przegranym
    // stanem optimistic i pokazywał odhaczoną pozycję, której serwer nie ma.
    expect(invalidate).toHaveBeenCalledTimes(1)
  })

  it('410 przy synchronizacji czyści kolejkę tokenu i ustawia stan „wygasła”', async () => {
    const store = useOfflineQueueStore()
    await saveSnapshot(targetKey(PUBLIC), { name: 'Zakupy', items: [] })
    store.markOffline()
    await store.enqueue(PUBLIC, 1, true)
    await store.enqueue(PUBLIC, 2, true)

    checkPublicListItem.mockRejectedValue(new PublicListUnavailableError())
    store.online = true
    await store.flush()

    expect(store.isGone(PUBLIC)).toBe(true)
    expect(await readQueue()).toEqual([])
    expect(store.pendingCount).toBe(0)
    // Snapshot wygasłej listy znika: pokazywanie jej po 410 byłoby udawaniem,
    // że link jeszcze działa.
    expect(await readSnapshot(targetKey(PUBLIC))).toBeNull()
    // Bez pętli retry — token wygasł i drugie żądanie nie poszło.
    expect(checkPublicListItem).toHaveBeenCalledTimes(1)
  })

  it('koryguje zegar klienta: checked_at jest w czasie serwera, nie telefonu', async () => {
    // Telefon spieszy się o 10 minut względem serwera. Nie podmieniamy zegara
    // przez `vi.useFakeTimers()`: `fake-indexeddb` chodzi na prawdziwych
    // timerach, więc zamrożony czas zawiesiłby każdą operację na bazie.
    const DZIESIEC_MINUT = 10 * 60 * 1000
    const czasSerwera = new Date(Date.now() - DZIESIEC_MINUT)
    recordServerDate(czasSerwera.toUTCString())

    const store = useOfflineQueueStore()
    store.markOffline()
    await store.enqueue(LIST, 9, true)

    const [entry] = await readQueue()
    expect(entry).toBeDefined()
    const zapisany = new Date(entry?.checkedAt ?? 0).getTime()
    // Znacznik siedzi przy czasie SERWERA (nagłówek `Date` ma rozdzielczość
    // sekundy, stąd tolerancja), a nie przy zegarze telefonu.
    expect(Math.abs(zapisany - czasSerwera.getTime())).toBeLessThan(2000)
    expect(Date.now() - zapisany).toBeGreaterThan(DZIESIEC_MINUT - 2000)
  })

  it('429 nie gubi zmian: wpis zostaje w kolejce, a flush się zatrzymuje', async () => {
    // Limit 60/min/IP jest WSPÓLNY dla całej ścieżki publicznej (ustalenie R3),
    // więc kolejka z kilkudziesięcioma odhaczeniami wejdzie w niego przy
    // normalnej pracy. Traktowanie 429 jak porażki gubiłoby zakupy.
    const store = useOfflineQueueStore()
    store.markOffline()
    await store.enqueue(LIST, 1, true)
    await store.enqueue(LIST, 2, true)

    updateShoppingListItem.mockRejectedValue(
      new ApiError(429, { code: 'rate_limited', message: 'Za dużo żądań.', details: {} }),
    )
    store.online = true
    const sent = await store.flush()

    expect(sent).toBe(0)
    // Sekwencyjnie i z zatrzymaniem: drugi wpis nie poleciał w ten sam limit.
    expect(updateShoppingListItem).toHaveBeenCalledTimes(1)
    expect(store.pendingCount).toBe(2)
    // 429 znaczy „serwer odpowiedział", więc NIE jesteśmy offline — banner ma
    // mówić „zapisuję", a nie „tryb offline".
    expect(store.isOffline).toBe(false)
    // Licznik prób rośnie tylko dla odmowy serwera — to backstop przed wpisem,
    // którego serwer nie przyjmie nigdy.
    expect((await readQueue())[0]?.attempts).toBe(1)
  })

  it('brak sieci NIE zużywa prób — kwadrans bez zasięgu nie kasuje odhaczeń', async () => {
    // Regresja: gdyby błąd sieci liczył się jak odmowa serwera, ponawianie co
    // 15 s wyczerpywałoby `MAX_ATTEMPTS` po ~2 minutach offline i kasowało
    // zakupy dokładnie w scenariuszu, dla którego ta kolejka istnieje.
    const store = useOfflineQueueStore()
    store.markOffline()
    await store.enqueue(LIST, 1, true)

    updateShoppingListItem.mockRejectedValue(
      new ApiError(0, { code: 'network_error', message: 'Brak połączenia.', details: {} }),
    )
    store.online = true
    for (let attempt = 0; attempt < 3; attempt += 1) {
      store.online = true
      await store.flush()
    }

    expect(store.pendingCount).toBe(1)
    expect((await readQueue())[0]?.attempts).toBe(0)
    expect(store.isOffline).toBe(true)
  })

  it('zapis online usuwa zaległy wpis tej samej pozycji', async () => {
    const store = useOfflineQueueStore()
    store.markOffline()
    await store.enqueue(LIST, 3, true)
    expect(store.pendingFor(LIST)).toBe(1)

    await store.forget(LIST, 3)

    expect(store.pendingFor(LIST)).toBe(0)
    expect(await readQueue()).toEqual([])
  })
})
