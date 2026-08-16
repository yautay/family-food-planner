/**
 * Wywołania katalogu produktów: `/products`, `/categories`, przeliczniki jednostek.
 * Typy z `generated.ts` (05_FRONTEND §2) — ręcznych interfejsów nie piszemy.
 */

import { apiFetch } from '@/api/client'
import type { components } from '@/api/generated'

export type Product = components['schemas']['ProductRead']
export type ProductDetail = components['schemas']['ProductDetail']
export type ProductList = components['schemas']['ProductListResponse']
export type ProductCreate = components['schemas']['ProductCreateRequest']
export type ProductUpdate = components['schemas']['ProductUpdateRequest']
export type ProductNutritionPayload = components['schemas']['ProductNutritionRequest']
export type Category = components['schemas']['CategoryRead']
export type CategoryList = components['schemas']['CategoryListResponse']
export type CategoryCreate = components['schemas']['CategoryCreateRequest']
export type UnitWeight = components['schemas']['UnitWeightRead']
export type UnitWeightList = components['schemas']['UnitWeightListResponse']
export type UnitWeightCreate = components['schemas']['UnitWeightCreateRequest']
export type UnitWeightUpdate = components['schemas']['UnitWeightUpdateRequest']
export type MeasureKind = components['schemas']['MeasureKind']
export type Perishability = components['schemas']['Perishability']
export type VerificationStatus = components['schemas']['VerificationStatus']

export interface ProductFilters {
  limit: number
  offset: number
  q?: string
  category_id?: number
  verification_status?: VerificationStatus
  include_archived?: boolean
}

export function fetchProducts(filters: ProductFilters): Promise<ProductList> {
  return apiFetch<ProductList>('/products', { query: { ...filters } })
}

export function fetchProduct(id: number): Promise<ProductDetail> {
  return apiFetch<ProductDetail>(`/products/${id}`)
}

export function createProduct(payload: ProductCreate): Promise<ProductDetail> {
  return apiFetch<ProductDetail>('/products', { method: 'POST', json: payload })
}

export function updateProduct(id: number, payload: ProductUpdate): Promise<ProductDetail> {
  return apiFetch<ProductDetail>(`/products/${id}`, { method: 'PATCH', json: payload })
}

export function deleteProduct(id: number): Promise<void> {
  return apiFetch<void>(`/products/${id}`, { method: 'DELETE' })
}

/** PUT — pełna podmiana wartości; pole pominięte zostaje wyczyszczone. */
export function setProductNutrition(
  id: number,
  payload: ProductNutritionPayload,
): Promise<ProductDetail> {
  return apiFetch<ProductDetail>(`/products/${id}/nutrition`, { method: 'PUT', json: payload })
}

export function verifyProduct(id: number): Promise<ProductDetail> {
  return apiFetch<ProductDetail>(`/products/${id}/verify`, { method: 'POST' })
}

export function setProductArchived(id: number, archived: boolean): Promise<ProductDetail> {
  return apiFetch<ProductDetail>(`/products/${id}/archive`, {
    method: archived ? 'POST' : 'DELETE',
  })
}

export function fetchCategories(): Promise<CategoryList> {
  return apiFetch<CategoryList>('/categories')
}

export function createCategory(payload: CategoryCreate): Promise<Category> {
  return apiFetch<Category>('/categories', { method: 'POST', json: payload })
}

export function fetchUnitWeights(productId: number): Promise<UnitWeightList> {
  return apiFetch<UnitWeightList>(`/products/${productId}/unit-weights`)
}

export function createUnitWeight(
  productId: number,
  payload: UnitWeightCreate,
): Promise<UnitWeight> {
  return apiFetch<UnitWeight>(`/products/${productId}/unit-weights`, {
    method: 'POST',
    json: payload,
  })
}

export function updateUnitWeight(
  productId: number,
  unitWeightId: number,
  payload: UnitWeightUpdate,
): Promise<UnitWeight> {
  return apiFetch<UnitWeight>(`/products/${productId}/unit-weights/${unitWeightId}`, {
    method: 'PATCH',
    json: payload,
  })
}

export function deleteUnitWeight(productId: number, unitWeightId: number): Promise<void> {
  return apiFetch<void>(`/products/${productId}/unit-weights/${unitWeightId}`, {
    method: 'DELETE',
  })
}
