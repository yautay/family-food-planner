/**
 * Wywołania `/admin/households` (ADMIN). Typy z `generated.ts` (05_FRONTEND §2).
 */

import { apiFetch } from '@/api/client'
import type { components } from '@/api/generated'
import type { AdminHouseholdsFilters } from '@/api/queryKeys'

export type AdminHousehold = components['schemas']['HouseholdRead']
export type AdminHouseholdDetail = components['schemas']['HouseholdDetail']
export type AdminHouseholdList = components['schemas']['HouseholdListResponse']

export function fetchHouseholds(filters: AdminHouseholdsFilters): Promise<AdminHouseholdList> {
  return apiFetch<AdminHouseholdList>('/admin/households', {
    query: { limit: filters.limit, offset: filters.offset, q: filters.q || undefined },
  })
}

export function fetchHousehold(id: number): Promise<AdminHouseholdDetail> {
  return apiFetch<AdminHouseholdDetail>(`/admin/households/${id}`)
}

export function createHousehold(name: string): Promise<AdminHouseholdDetail> {
  return apiFetch<AdminHouseholdDetail>('/admin/households', { method: 'POST', json: { name } })
}

export function renameHousehold(id: number, name: string): Promise<AdminHouseholdDetail> {
  return apiFetch<AdminHouseholdDetail>(`/admin/households/${id}`, {
    method: 'PATCH',
    json: { name },
  })
}

export function deleteHousehold(id: number): Promise<void> {
  return apiFetch<void>(`/admin/households/${id}`, { method: 'DELETE' })
}

/** Pełna podmiana składu: konta spoza listy zostają odpięte od rodziny. */
export function setHouseholdMembers(id: number, userIds: number[]): Promise<AdminHouseholdDetail> {
  return apiFetch<AdminHouseholdDetail>(`/admin/households/${id}/members`, {
    method: 'PUT',
    json: { user_ids: userIds },
  })
}
