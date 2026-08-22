/**
 * Hydratacja listy ze snapshotu IndexedDB (karta B12 §Tests — komponenty).
 *
 * Sprawdzamy zachowanie, na którym stoi AC 2 („otwarta wcześniej lista renderuje
 * się po odcięciu sieci"): snapshot ma trafić do cache'u TanStack Query, ale
 * NIGDY nie może nadpisać danych świeższych ani udawać danych świeżych.
 */

import 'fake-indexeddb/auto'

import { QueryClient } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it } from 'vitest'

import { resetOfflineDb, saveSnapshot } from '@/lib/offline/db'
import { hydrateFromSnapshot } from '@/lib/offline/hydrate'

const KEY = ['shopping', 'lists', 'detail', 7] as const
const SNAPSHOT_KEY = 'list:7'

interface Lista {
  name: string
}

beforeEach(async () => {
  await resetOfflineDb()
  await new Promise<void>((resolve) => {
    const request = indexedDB.deleteDatabase('ffp-offline')
    request.onsuccess = () => resolve()
    request.onerror = () => resolve()
    request.onblocked = () => resolve()
  })
})

describe('hydrateFromSnapshot', () => {
  it('wstawia zapisaną listę do cache’u, gdy zapytanie nie ma danych', async () => {
    const client = new QueryClient()
    await saveSnapshot(SNAPSHOT_KEY, { name: 'Zakupy 07.01' })

    const hydrated = await hydrateFromSnapshot<Lista>(client, KEY, SNAPSHOT_KEY)

    expect(hydrated).toBe(true)
    expect(client.getQueryData<Lista>(KEY)?.name).toBe('Zakupy 07.01')
  })

  it('nie nadpisuje danych, które zapytanie już ma', async () => {
    const client = new QueryClient()
    client.setQueryData<Lista>(KEY, { name: 'Świeże z serwera' })
    await saveSnapshot(SNAPSHOT_KEY, { name: 'Stary snapshot' })

    const hydrated = await hydrateFromSnapshot<Lista>(client, KEY, SNAPSHOT_KEY)

    expect(hydrated).toBe(false)
    expect(client.getQueryData<Lista>(KEY)?.name).toBe('Świeże z serwera')
  })

  it('brak snapshotu to brak zmian — strona pokaże zwykły stan „nie znaleziono”', async () => {
    const client = new QueryClient()

    const hydrated = await hydrateFromSnapshot<Lista>(client, KEY, SNAPSHOT_KEY)

    expect(hydrated).toBe(false)
    expect(client.getQueryData(KEY)).toBeUndefined()
  })

  it('hydratowane dane są od razu NIEŚWIEŻE — inaczej staleTime blokowałby refetch', async () => {
    const client = new QueryClient()
    await saveSnapshot(SNAPSHOT_KEY, { name: 'Zakupy 07.01' })

    await hydrateFromSnapshot<Lista>(client, KEY, SNAPSHOT_KEY)

    const state = client.getQueryState(KEY)
    expect(state?.dataUpdatedAt).toBe(1)
    // `staleTime` z `main.ts` to 30 s; znacznik z 1970 gwarantuje, że wejście
    // na listę z zasięgiem natychmiast pobierze świeżą wersję.
    expect(Date.now() - (state?.dataUpdatedAt ?? 0)).toBeGreaterThan(30_000)
  })
})
