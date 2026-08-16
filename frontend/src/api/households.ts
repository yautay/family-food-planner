/**
 * Wywołania `/households/my` — moja rodzina i profile jej członków.
 * Typy z `generated.ts` (05_FRONTEND §2) — ręcznych interfejsów nie piszemy.
 */

import { apiFetch } from '@/api/client'
import type { components } from '@/api/generated'

export type MyHousehold = components['schemas']['MyHouseholdResponse']
export type HouseholdSummary = components['schemas']['HouseholdSummary']
export type HouseholdMember = components['schemas']['HouseholdMember']
export type MemberProfile = components['schemas']['MemberProfileRead']
export type MemberProfileList = components['schemas']['MemberProfileListResponse']
export type MemberProfileCreate = components['schemas']['MemberProfileCreateRequest']
export type MemberProfileUpdate = components['schemas']['MemberProfileUpdateRequest']

export function fetchMyHousehold(): Promise<MyHousehold> {
  return apiFetch<MyHousehold>('/households/my')
}

export function fetchMyProfiles(): Promise<MemberProfileList> {
  return apiFetch<MemberProfileList>('/households/my/profiles')
}

export function createProfile(payload: MemberProfileCreate): Promise<MemberProfile> {
  return apiFetch<MemberProfile>('/households/my/profiles', { method: 'POST', json: payload })
}

export function updateProfile(id: number, payload: MemberProfileUpdate): Promise<MemberProfile> {
  return apiFetch<MemberProfile>(`/households/my/profiles/${id}`, {
    method: 'PATCH',
    json: payload,
  })
}

export function deleteProfile(id: number): Promise<void> {
  return apiFetch<void>(`/households/my/profiles/${id}`, { method: 'DELETE' })
}
