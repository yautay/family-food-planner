/**
 * Wywołania API uwierzytelniania. Typy pochodzą z `generated.ts` (task fe-types).
 */

import { ApiError, apiFetch } from '@/api/client'
import type { components } from '@/api/generated'

export type CurrentUser = components['schemas']['CurrentUser']
export type LoginPayload = components['schemas']['LoginRequest']

/** `GET /auth/me` — brak sesji (401) to normalny stan, nie błąd. */
export async function fetchCurrentUser(): Promise<CurrentUser | null> {
  try {
    return await apiFetch<CurrentUser>('/auth/me')
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return null
    }
    throw error
  }
}

export function loginRequest(payload: LoginPayload): Promise<CurrentUser> {
  return apiFetch<CurrentUser>('/auth/login', { method: 'POST', json: payload })
}

export function logoutRequest(): Promise<void> {
  return apiFetch<void>('/auth/logout', { method: 'POST' })
}
