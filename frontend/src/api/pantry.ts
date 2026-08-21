/**
 * Wywołania spiżarni: `/pantry` (04_API §2).
 * Typy z `generated.ts` (05_FRONTEND §2) — ręcznych interfejsów nie piszemy.
 */

import { apiFetch } from '@/api/client'
import type { components } from '@/api/generated'

export type PantryItem = components['schemas']['PantryItemRead']
export type PantryList = components['schemas']['PantryListResponse']
export type PantryItemCreate = components['schemas']['PantryItemCreateRequest']
export type PantryItemUpdate = components['schemas']['PantryItemUpdateRequest']
export type PantrySort = components['schemas']['PantrySort']

export interface PantryFilters {
  limit: number
  offset: number
  q?: string
  category_id?: number
  sort?: PantrySort
  expires_within_days?: number
}

export function fetchPantryItems(filters: PantryFilters): Promise<PantryList> {
  return apiFetch<PantryList>('/pantry', { query: { ...filters } })
}

export function createPantryItem(payload: PantryItemCreate): Promise<PantryItem> {
  return apiFetch<PantryItem>('/pantry', { method: 'POST', json: payload })
}

/** PATCH — pola pominięte zostają bez zmian; `{ amount: '0' }` to wyzerowanie. */
export function updatePantryItem(id: number, payload: PantryItemUpdate): Promise<PantryItem> {
  return apiFetch<PantryItem>(`/pantry/${id}`, { method: 'PATCH', json: payload })
}

export function deletePantryItem(id: number): Promise<void> {
  return apiFetch<void>(`/pantry/${id}`, { method: 'DELETE' })
}
