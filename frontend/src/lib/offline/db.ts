/**
 * IndexedDB listy zakupowej: snapshot treści + kolejka odhaczeń (ADR-009).
 *
 * Dwa magazyny, bo dwa różne czasy życia:
 *
 * - **`list-snapshots`** — ostatnia znana treść otwartej listy. Nadpisywana
 *   przy każdej pełnej odpowiedzi serwera i po każdej lokalnej zmianie stanu
 *   checkboxa, żeby przeładowanie strony w sklepie bez zasięgu pokazało to,
 *   co użytkownik widział przed sekundą, a nie pusty ekran.
 * - **`mutation-queue`** — odhaczenia, które nie doszły na serwer. Żyją, dopóki
 *   nie zostaną wysłane; przeżywają reload i zamknięcie karty.
 *
 * **Klucz kolejki jest DETERMINISTYCZNY** (`{target}#{itemId}`), a nie
 * autoinkrementalny: `put()` po takim kluczu daje deduplikację per pozycja za
 * darmo. Bez tego dwukrotne odhaczenie tej samej rzeczy offline (kliknięcie,
 * rozmyślenie się, kliknięcie ponownie) wysłałoby po odzyskaniu sieci dwa
 * PATCH-e, z których pierwszy niósłby stan już nieaktualny. Kolejność wysyłki
 * bierzemy z `queuedAt`, nie z klucza.
 *
 * Snapshot prywatny zachowuje prywatną odpowiedź listy, także received_at.
 * Izoluje go losowy scope potwierdzonej sesji; odczyt i każdy zapis sprawdzają
 * aktualność scope ponownie po await. Starsze list:* pozostają w kwarantannie.
 * Publiczny snapshot nadal ma wyłącznie PublicListRead i osobny klucz tokenu.
 * Tokeny ani namespace nie trafiają do konsoli i raportów błędów.
 *
 * Bez IndexedDB odczyt snapshotu zwraca brak danych. Zapis intencji i odczyt
 * kolejki zgłaszają kontrolowany OfflineStorageError: UI wycofuje checkbox
 * i pokazuje błąd zamiast udawać trwały zapis lub pustą kolejkę. Dostępna
 * sesja online nadal pozwala korzystać z API.
 */

import { openDB, type DBSchema, type IDBPDatabase } from 'idb'
import { isPrivateOfflineScopeCurrent } from './privateSession'

const DB_NAME = 'pasnik-offline'
const DB_VERSION = 1
const SNAPSHOTS = 'list-snapshots'
const QUEUE = 'mutation-queue'

/** Adresat mutacji: lista zalogowanego albo publiczny link (ADR-010). */
export type QueueTarget =
  { kind: 'list'; listId: number; scope: string } | { kind: 'public'; token: string }

/** Klucz obu magazynów — ta sama lista ma ten sam klucz w snapshotcie i kolejce. */
export function targetKey(target: QueueTarget): string {
  return target.kind === 'list'
    ? `private:${target.scope}:list:${target.listId}`
    : `public:${target.token}`
}

/** Nie przypisujemy starych list:* ani obcego scope do bieżącego konta. */
export function isQueueTargetCurrent(target: QueueTarget): boolean {
  return (
    target.kind === 'public' ||
    (typeof target.scope === 'string' && isPrivateOfflineScopeCurrent(target.scope))
  )
}

export function isSnapshotKeyCurrent(key: string): boolean {
  if (key.startsWith('public:')) return true
  const match = /^private:([^:]+):list:\d+(?:#\d+)?$/.exec(key)
  return match !== null && isPrivateOfflineScopeCurrent(match[1]!)
}

export class OfflineStorageError extends Error {
  constructor() {
    super('Nie udało się zapisać zmiany na tym urządzeniu. Połącz się z siecią i spróbuj ponownie.')
  }
}

export interface ListSnapshot {
  /** `private:{scope}:list:{id}` albo `public:{token}`. */
  key: string
  /** Payload odpowiedzi w kształcie, w jakim renderuje go strona. */
  payload: unknown
  /** ISO8601 — kiedy snapshot powstał (UI może pokazać „dane sprzed…"). */
  fetchedAt: string
}

export interface QueuedCheck {
  key: string
  target: QueueTarget
  itemId: number
  checked: boolean
  /** Moment DECYZJI w zegarze serwera (`clock.ts`) — na nim stoi LWW. */
  checkedAt: string
  /** Moment wejścia do kolejki — wyłącznie kolejność wysyłki. */
  queuedAt: string
  attempts: number
}

interface OfflineDB extends DBSchema {
  [SNAPSHOTS]: { key: string; value: ListSnapshot }
  [QUEUE]: { key: string; value: QueuedCheck }
}

let handle: Promise<IDBPDatabase<OfflineDB>> | null = null

function available(): boolean {
  return typeof indexedDB !== 'undefined'
}

function db(): Promise<IDBPDatabase<OfflineDB>> {
  handle ??= openDB<OfflineDB>(DB_NAME, DB_VERSION, {
    upgrade(database) {
      if (!database.objectStoreNames.contains(SNAPSHOTS)) {
        database.createObjectStore(SNAPSHOTS, { keyPath: 'key' })
      }
      if (!database.objectStoreNames.contains(QUEUE)) {
        database.createObjectStore(QUEUE, { keyPath: 'key' })
      }
    },
  })
  return handle
}

/**
 * Wykonaj operację na bazie; awaria storage'u NIE może wysadzić strony.
 *
 * Tryb prywatny Safari i wyczerpana kwota rzucają na `openDB`. Lista zakupowa
 * ma wtedy działać jak przed B12 (online), a nie pokazać białego ekranu.
 */
async function withDb<T>(
  operation: (database: IDBPDatabase<OfflineDB>) => Promise<T>,
  fallback: T,
) {
  if (!available()) {
    return fallback
  }
  try {
    return await operation(await db())
  } catch {
    return fallback
  }
}

/**
 * Zamień cokolwiek na CZYSTĄ strukturę danych, zanim trafi do IndexedDB.
 *
 * IndexedDB zapisuje przez structured clone, a ten **rzuca `DataCloneError` na
 * proxy Vue** — a dokładnie proxy dostajemy z cache'u TanStack Query
 * (`useQuery().data` jest częścią reaktywnego wyniku). Bez tej konwersji zapis
 * po cichu padał: `withDb` łykał wyjątek, snapshot i kolejka zostawały puste,
 * a UI wyglądał POPRAWNIE, bo optimistic update żyje w pamięci. Wyszło dopiero
 * w E2E na prawdziwym Chromium — `fake-indexeddb` w vitest przyjmował
 * przekazywane tam obiekty literalne bez szemrania.
 *
 * Droga przez JSON jest tu bezstratna z definicji: zapisujemy wyłącznie
 * odpowiedzi API (stringi, liczby, boole, `null`, tablice, obiekty) i własne
 * wpisy kolejki złożone z prymitywów. Żadnych `Date`, `Map` ani `undefined`.
 */
function plain<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

// --- snapshot treści listy ------------------------------------------------------

export async function saveSnapshot(key: string, payload: unknown): Promise<boolean> {
  if (!isSnapshotKeyCurrent(key)) return false
  return withDb(async (database) => {
    if (!isSnapshotKeyCurrent(key)) return false
    const transaction = database.transaction(SNAPSHOTS, 'readwrite')
    await transaction.store.put({
      key,
      payload: plain(payload),
      fetchedAt: new Date().toISOString(),
    })
    if (!isSnapshotKeyCurrent(key)) {
      transaction.abort()
      await transaction.done.catch(() => {})
      return false
    }
    await transaction.done
    return isSnapshotKeyCurrent(key)
  }, false)
}

export async function readSnapshot<T>(key: string): Promise<T | null> {
  if (!isSnapshotKeyCurrent(key)) return null
  const row = await withDb((database) => database.get(SNAPSHOTS, key), undefined)
  return row === undefined || !isSnapshotKeyCurrent(key) ? null : (row.payload as T)
}

export async function deleteSnapshot(key: string): Promise<void> {
  if (!isSnapshotKeyCurrent(key)) return
  await withDb(async (database) => {
    if (!isSnapshotKeyCurrent(key)) return
    await database.delete(SNAPSHOTS, key)
  }, undefined)
}

// --- kolejka odhaczeń -----------------------------------------------------------

/** Klucz wpisu kolejki: jedna pozycja listy = najwyżej jeden wpis. */
export function queueKey(target: QueueTarget, itemId: number): string {
  return `${targetKey(target)}#${itemId}`
}

/**
 * Wstaw albo NADPISZ odhaczenie tej pozycji.
 *
 * `queuedAt` zachowujemy z wpisu, który już czekał: pozycja odhaczona jako
 * pierwsza ma pójść na serwer jako pierwsza, nawet jeśli użytkownik zmienił
 * przy niej zdanie na końcu.
 */
export async function enqueueCheck(
  target: QueueTarget,
  itemId: number,
  checked: boolean,
  checkedAt: Date,
  snapshot?: unknown,
): Promise<void> {
  if (!isQueueTargetCurrent(target)) throw new OfflineStorageError()
  const key = queueKey(target, itemId)
  const saved = await withDb(async (database) => {
    if (!isQueueTargetCurrent(target)) return false
    const transaction = database.transaction([QUEUE, SNAPSHOTS], 'readwrite')
    const queue = transaction.objectStore(QUEUE)
    const existing = await queue.get(key)
    if (!isQueueTargetCurrent(target)) {
      transaction.abort()
      await transaction.done.catch(() => {})
      return false
    }
    await queue.put({
      key,
      target: plain(target),
      itemId,
      checked,
      checkedAt: checkedAt.toISOString(),
      queuedAt: existing?.queuedAt ?? new Date().toISOString(),
      attempts: 0,
    })
    // UI zapisuje optimistic snapshot już PRZED żądaniem online. Starsza
    // odmowa mogła go w tym czasie unieważnić. Fallback network0 odtwarza go
    // atomowo razem z NOWĄ intencją, także gdy cache nie zmienił się ponownie.
    if (snapshot !== undefined) {
      await transaction.objectStore(SNAPSHOTS).put({
        key: targetKey(target),
        payload: plain(snapshot),
        fetchedAt: new Date().toISOString(),
      })
    }
    if (!isQueueTargetCurrent(target)) {
      transaction.abort()
      await transaction.done.catch(() => {})
      return false
    }
    await transaction.done
    return isQueueTargetCurrent(target)
  }, false)
  if (!saved) throw new OfflineStorageError()
}

/** Cała kolejka w kolejności wejścia — flush idzie po niej sekwencyjnie. */
export async function readQueue(): Promise<QueuedCheck[]> {
  const rows = await withDb((database) => database.getAll(QUEUE), null)
  if (rows === null) throw new OfflineStorageError()
  return [...rows].sort((a, b) => a.queuedAt.localeCompare(b.queuedAt))
}

export async function deleteQueued(key: string): Promise<void> {
  if (!isSnapshotKeyCurrent(key)) return
  await withDb(async (database) => {
    if (!isSnapshotKeyCurrent(key)) return
    await database.delete(QUEUE, key)
  }, undefined)
}

/** Usuń tylko wysłaną decyzję — w trakcie PATCH mogła powstać nowa pod tym samym kluczem. */
export async function deleteQueuedIfUnchanged(entry: QueuedCheck): Promise<void> {
  if (!isQueueTargetCurrent(entry.target)) return
  await withDb(async (database) => {
    const transaction = database.transaction(QUEUE, 'readwrite')
    const row = await transaction.store.get(entry.key)
    if (!isQueueTargetCurrent(entry.target)) {
      transaction.abort()
      await transaction.done.catch(() => {})
      return
    }
    if (row && row.checkedAt === entry.checkedAt && row.checked === entry.checked) {
      await transaction.store.delete(entry.key)
    }
    await transaction.done
  }, undefined)
}

/**
 * Terminalna odmowa bieżącej decyzji unieważnia jej optimistic snapshot.
 * Porównanie wersji, ack i usunięcie snapshotu należą do JEDNEJ transakcji:
 * enqueue nowszej decyzji nie może wejść pomiędzy ack a kasowanie snapshotu.
 */
export async function rejectQueuedIfUnchanged(entry: QueuedCheck): Promise<boolean> {
  if (!isQueueTargetCurrent(entry.target)) return false
  return withDb(async (database) => {
    const transaction = database.transaction([QUEUE, SNAPSHOTS], 'readwrite')
    const queue = transaction.objectStore(QUEUE)
    const row = await queue.get(entry.key)
    if (!isQueueTargetCurrent(entry.target)) {
      transaction.abort()
      await transaction.done.catch(() => {})
      return false
    }
    const current =
      row !== undefined && row.checkedAt === entry.checkedAt && row.checked === entry.checked
    if (current) {
      await queue.delete(entry.key)
      await transaction.objectStore(SNAPSHOTS).delete(targetKey(entry.target))
    }
    await transaction.done
    return current
  }, false)
}

/** Wpisy jednej listy — używane po 410 (token wygasł, nie ma dokąd wysyłać). */
export async function clearQueueFor(target: QueueTarget): Promise<void> {
  if (!isQueueTargetCurrent(target)) return
  const prefix = `${targetKey(target)}#`
  await withDb(async (database) => {
    for (const row of await database.getAll(QUEUE)) {
      if (!isQueueTargetCurrent(target)) return
      if (row.key.startsWith(prefix)) {
        await database.delete(QUEUE, row.key)
      }
    }
  }, undefined)
}

/**
 * Zamknij połączenie i zapomnij uchwyt. WYŁĄCZNIE dla testów.
 *
 * Moduł trzyma jedno połączenie na całe życie karty (tak ma być w przeglądarce),
 * ale otwarte połączenie BLOKUJE `indexedDB.deleteDatabase`, więc bez tego
 * każdy test czyszczący bazę wisiałby na `onblocked`. Wzorzec jak
 * `resetClockSkew` w `clock.ts`.
 */
export async function resetOfflineDb(): Promise<void> {
  if (handle === null) {
    return
  }
  const pending = handle
  handle = null
  try {
    ;(await pending).close()
  } catch {
    // Połączenie mogło się nie otworzyć — nie ma czego zamykać.
  }
}

/** Odmowa dotyczy wysłanej decyzji, nie jej ewentualnego następcy pod tym samym kluczem. */
export async function bumpAttempts(entry: QueuedCheck): Promise<void> {
  if (!isQueueTargetCurrent(entry.target)) return
  await withDb(async (database) => {
    const transaction = database.transaction(QUEUE, 'readwrite')
    const row = await transaction.store.get(entry.key)
    if (!isQueueTargetCurrent(entry.target)) {
      transaction.abort()
      await transaction.done.catch(() => {})
      return
    }
    if (row && row.checkedAt === entry.checkedAt && row.checked === entry.checked) {
      await transaction.store.put({ ...row, attempts: row.attempts + 1 })
    }
    await transaction.done
  }, undefined)
}
