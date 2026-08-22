/**
 * Hydratacja widoku listy ze snapshotu IndexedDB (ADR-009).
 *
 * Snapshot ląduje w CACHE'U TanStack Query, a nie w osobnym ref-ie strony.
 * To jedna decyzja, z której wynikają trzy rzeczy naraz: render, optimistic
 * update i rollback działają offline dokładnie tym samym kodem, co online —
 * bo dla komponentu nie ma różnicy, skąd dane w cache'u się wzięły. Wariant
 * z osobnym ref-em („dane albo snapshot") wymagałby drugiej ścieżki dla
 * odhaczania, bo `setQueryData` nie miałoby czego podmienić.
 *
 * `updatedAt: 1` (czyli „dane z 1970") jest tu ISTOTNE. `setQueryData` bez tej
 * opcji stempluje wpis czasem bieżącym, `staleTime: 30_000` z `main.ts` uznaje
 * go za świeży i wejście na listę Z ZASIĘGIEM pokazywałoby przez pół minuty
 * wczorajszą wersję, zamiast od razu pobrać nową.
 */

import type { QueryClient, QueryKey } from '@tanstack/vue-query'

import { readSnapshot } from '@/lib/offline/db'

/**
 * Wstaw snapshot do cache'u, jeśli zapytanie nie ma jeszcze danych.
 *
 * Zwraca `true`, gdy coś wstawiono. Sprawdzenie „czy są dane" powtarzamy PO
 * odczycie z IndexedDB, bo odczyt jest asynchroniczny i w tym czasie mogła
 * dojść odpowiedź serwera — nadpisanie jej starym snapshotem byłoby cofnięciem
 * świeższego stanu.
 */
export async function hydrateFromSnapshot<T>(
  client: QueryClient,
  queryKey: QueryKey,
  snapshotKey: string,
): Promise<boolean> {
  if (client.getQueryData(queryKey) !== undefined) {
    return false
  }
  const snapshot = await readSnapshot<T>(snapshotKey)
  if (snapshot === null || client.getQueryData(queryKey) !== undefined) {
    return false
  }
  client.setQueryData<T>(queryKey, snapshot, { updatedAt: 1 })
  return true
}
