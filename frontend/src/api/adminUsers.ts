/**
 * Wywołania `/admin/users` (ADMIN). Typy z `generated.ts` — ręcznych interfejsów
 * odpowiedzi nie piszemy (05_FRONTEND §2).
 */

import { apiFetch } from '@/api/client'
import type { components } from '@/api/generated'
import type { AdminUsersFilters } from '@/api/queryKeys'

export type AdminUser = components['schemas']['UserRead']
export type AdminUserList = components['schemas']['UserListResponse']
export type AdminUserCreate = components['schemas']['UserCreateRequest']
export type AdminUserUpdate = components['schemas']['UserUpdateRequest']

export function fetchUsers(filters: AdminUsersFilters): Promise<AdminUserList> {
  return apiFetch<AdminUserList>('/admin/users', {
    query: { limit: filters.limit, offset: filters.offset, q: filters.q || undefined },
  })
}

export function createUser(payload: AdminUserCreate): Promise<AdminUser> {
  return apiFetch<AdminUser>('/admin/users', { method: 'POST', json: payload })
}

export function updateUser(id: number, payload: AdminUserUpdate): Promise<AdminUser> {
  return apiFetch<AdminUser>(`/admin/users/${id}`, { method: 'PATCH', json: payload })
}
