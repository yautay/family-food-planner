/**
 * Wywołania produktów sklepowych: `/retail-products` (04_API §2).
 * Typy z `generated.ts` (05_FRONTEND §2) — ręcznych interfejsów nie piszemy.
 */

import { apiFetch } from '@/api/client'
import type { components } from '@/api/generated'

export type RetailProduct = components['schemas']['RetailProductRead']
export type RetailProductList = components['schemas']['RetailProductListResponse']
export type RetailProductCreate = components['schemas']['RetailProductCreateRequest']
export type RetailProductUpdate = components['schemas']['RetailProductUpdateRequest']
export type PackageUnit = components['schemas']['AmountUnit']

export interface RetailFilters {
  limit: number
  offset: number
  canonical_product_id?: number
  store_id?: number
  q?: string
  include_archived?: boolean
}

export function fetchRetailProducts(filters: RetailFilters): Promise<RetailProductList> {
  return apiFetch<RetailProductList>('/retail-products', { query: { ...filters } })
}

export function createRetailProduct(payload: RetailProductCreate): Promise<RetailProduct> {
  return apiFetch<RetailProduct>('/retail-products', { method: 'POST', json: payload })
}

export function updateRetailProduct(
  id: number,
  payload: RetailProductUpdate,
): Promise<RetailProduct> {
  return apiFetch<RetailProduct>(`/retail-products/${id}`, { method: 'PATCH', json: payload })
}

export function deleteRetailProduct(id: number): Promise<void> {
  return apiFetch<void>(`/retail-products/${id}`, { method: 'DELETE' })
}

/** PUT (nie POST jak przy przepisach) — kontrakt `/retail-products/{id}/photo`. */
export function uploadRetailPhoto(id: number, file: File): Promise<RetailProduct> {
  const form = new FormData()
  form.append('file', file)
  return apiFetch<RetailProduct>(`/retail-products/${id}/photo`, { method: 'PUT', form })
}

export function deleteRetailPhoto(id: number): Promise<RetailProduct> {
  return apiFetch<RetailProduct>(`/retail-products/${id}/photo`, { method: 'DELETE' })
}
