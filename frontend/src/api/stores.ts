/**
 * Wywołania sklepów: `/stores` i `/stores/{id}/category-order` (04_API §2).
 * Typy z `generated.ts` (05_FRONTEND §2) — ręcznych interfejsów nie piszemy.
 */

import { apiFetch } from '@/api/client'
import type { components } from '@/api/generated'

export type Store = components['schemas']['StoreRead']
export type StoreList = components['schemas']['StoreListResponse']
export type StoreCreate = components['schemas']['StoreCreateRequest']
export type StoreUpdate = components['schemas']['StoreUpdateRequest']
export type CategoryOrderEntry = components['schemas']['StoreCategoryOrderEntry']
export type CategoryOrder = components['schemas']['StoreCategoryOrderResponse']

export interface StoreFilters {
  /** Sklepy archiwalne (ADR-012) — domyślnie ukryte, jak w pickerach. */
  include_archived?: boolean
}

export function fetchStores(filters: StoreFilters = {}): Promise<StoreList> {
  return apiFetch<StoreList>('/stores', { query: { ...filters } })
}

export function createStore(payload: StoreCreate): Promise<Store> {
  return apiFetch<Store>('/stores', { method: 'POST', json: payload })
}

export function updateStore(id: number, payload: StoreUpdate): Promise<Store> {
  return apiFetch<Store>(`/stores/${id}`, { method: 'PATCH', json: payload })
}

export function deleteStore(id: number): Promise<void> {
  return apiFetch<void>(`/stores/${id}`, { method: 'DELETE' })
}

export function fetchCategoryOrder(storeId: number): Promise<CategoryOrder> {
  return apiFetch<CategoryOrder>(`/stores/${storeId}/category-order`)
}

/** PUT — pełna podmiana kolejności; pozycje liczy serwer z indeksów listy. */
export function setCategoryOrder(storeId: number, categoryIds: number[]): Promise<CategoryOrder> {
  return apiFetch<CategoryOrder>(`/stores/${storeId}/category-order`, {
    method: 'PUT',
    json: { category_ids: categoryIds },
  })
}
