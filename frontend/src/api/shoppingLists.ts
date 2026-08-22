/**
 * Wywołania list zakupowych: `/shopping/lists/*` (04_API §2).
 * Typy z `generated.ts` (05_FRONTEND §2) — ręcznych interfejsów nie piszemy.
 *
 * Osobny moduł od `shopping.ts`, bo osobny obszar: tam generacja (podgląd,
 * tury, finalizacja), tu życie GOTOWEJ listy w sklepie. Publiczna strona
 * `/l/:token` ma jeszcze własny, lekki klient — `publicList.ts`.
 */

import { apiFetch } from '@/api/client'
import type { components } from '@/api/generated'

export type ShoppingListDetail = components['schemas']['ShoppingListDetailRead']
export type ShoppingListSummary = components['schemas']['ShoppingListSummaryRead']
export type ShoppingListsResponse = components['schemas']['ShoppingListsResponse']
export type ListSection = components['schemas']['ListSectionRead']
export type ShoppingListItem = components['schemas']['ShoppingListItemRead']
export type ListUpdate = components['schemas']['ListUpdateRequest']
export type ListItemUpdate = components['schemas']['ListItemUpdateRequest']
export type Share = components['schemas']['ShareRead']
export type ShareCreate = components['schemas']['ShareCreateRequest']
export type AcceptToPantry = components['schemas']['AcceptToPantryResponse']
export type ShoppingListStatus = components['schemas']['ShoppingListStatus']

export interface ShoppingListsFilters {
  limit: number
  offset: number
  status?: ShoppingListStatus
}

export function fetchShoppingLists(filters: ShoppingListsFilters): Promise<ShoppingListsResponse> {
  return apiFetch<ShoppingListsResponse>('/shopping/lists', { query: { ...filters } })
}

export function fetchShoppingList(id: number): Promise<ShoppingListDetail> {
  return apiFetch<ShoppingListDetail>(`/shopping/lists/${id}`)
}

/** PATCH listy: nazwa i sklep. Zmiana sklepu PRZESORTOWUJE sekcje (AC 1). */
export function updateShoppingList(id: number, payload: ListUpdate): Promise<ShoppingListDetail> {
  return apiFetch<ShoppingListDetail>(`/shopping/lists/${id}`, { method: 'PATCH', json: payload })
}

export function deleteShoppingList(id: number): Promise<void> {
  return apiFetch<void>(`/shopping/lists/${id}`, { method: 'DELETE' })
}

/** Odhaczenie albo „mam już w domu". `checked_at` ustawia serwer (ADR-009). */
export function updateShoppingListItem(
  listId: number,
  itemId: number,
  payload: ListItemUpdate,
): Promise<ShoppingListItem> {
  return apiFetch<ShoppingListItem>(`/shopping/lists/${listId}/items/${itemId}`, {
    method: 'PATCH',
    json: payload,
  })
}

/** Udostępnienie: ZAWSZE nowy token, także po odwołaniu (ADR-010). */
export function shareShoppingList(id: number, payload: ShareCreate): Promise<Share> {
  return apiFetch<Share>(`/shopping/lists/${id}/share`, { method: 'POST', json: payload })
}

export function revokeShoppingListShare(id: number): Promise<void> {
  return apiFetch<void>(`/shopping/lists/${id}/share`, { method: 'DELETE' })
}

/** Akcja JAWNA (02_DOMAIN §8) — nic nie wchodzi do spiżarni w tle. */
export function acceptListToPantry(id: number): Promise<AcceptToPantry> {
  return apiFetch<AcceptToPantry>(`/shopping/lists/${id}/accept-to-pantry`, { method: 'POST' })
}

/**
 * Ścieżka względna z API (`/l/{token}`) → pełny adres do wysłania.
 *
 * Origin bierzemy z przeglądarki, bo backend nie wie, pod jaką domeną stoi
 * reverse proxy (karta B11, Implementation Notes pkt 7). Ten sam adres idzie
 * do QR-a, do schowka i do Web Share API.
 */
export function absoluteShareUrl(path: string): string {
  return `${window.location.origin}${path}`
}
