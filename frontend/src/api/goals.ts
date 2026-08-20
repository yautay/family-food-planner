/**
 * Wywołania celów żywieniowych (`/goals`) i progów statusów
 * (`/auth/me/ui-settings`). Typy z `generated.ts` (05_FRONTEND §2).
 */

import { apiFetch } from '@/api/client'
import type { components } from '@/api/generated'

export type Goal = components['schemas']['GoalRead']
export type GoalList = components['schemas']['GoalListResponse']
export type GoalPayload = components['schemas']['GoalPayload']
export type CurrentUser = components['schemas']['CurrentUser']
export type NutritionThresholds = components['schemas']['NutritionThresholdsPayload']

/** Progi z decyzji D9 — te same wartości domyślne co po stronie silnika. */
export const DEFAULT_THRESHOLDS: NutritionThresholds = { low: 90, high: 110 }

export function fetchGoals(): Promise<GoalList> {
  return apiFetch<GoalList>('/goals')
}

export function createGoal(payload: GoalPayload): Promise<Goal> {
  return apiFetch<Goal>('/goals', { method: 'POST', json: payload })
}

export function updateGoal(id: number, payload: GoalPayload): Promise<Goal> {
  return apiFetch<Goal>(`/goals/${id}`, { method: 'PUT', json: payload })
}

export function deleteGoal(id: number): Promise<void> {
  return apiFetch<void>(`/goals/${id}`, { method: 'DELETE' })
}

export function updateThresholds(thresholds: NutritionThresholds): Promise<CurrentUser> {
  return apiFetch<CurrentUser>('/auth/me/ui-settings', {
    method: 'PATCH',
    json: { nutrition_thresholds: thresholds },
  })
}
