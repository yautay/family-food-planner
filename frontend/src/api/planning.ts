/**
 * Wywołania modułu planu dnia: `/plan/*`.
 * Typy z `generated.ts` (05_FRONTEND §2) — ręcznych interfejsów nie piszemy.
 *
 * Każda mutacja odpowiada CAŁYM dniem po zmianie, więc komponenty nie muszą
 * dopytywać o stan; do cache'u i tak trafia to przez `invalidateQueries`.
 */

import { apiFetch } from '@/api/client'
import type { components } from '@/api/generated'

export type PlanDay = components['schemas']['DayRead']
export type PlanDays = components['schemas']['DaysResponse']
export type PlanMeal = components['schemas']['MealRead']
export type PlanItem = components['schemas']['PlanItemRead']
export type PlanServingSplit = components['schemas']['PlanServingSplitRead']
export type PlanServingSplitInput = components['schemas']['PlanServingSplitInput']
export type GoalMetric = components['schemas']['GoalMetricRead']
export type GoalStatus = components['schemas']['GoalStatus']
export type FitToTarget = components['schemas']['FitToTargetResponse']
export type MealCreate = components['schemas']['MealCreateRequest']
export type MealUpdate = components['schemas']['MealUpdateRequest']
export type ItemCreate = components['schemas']['ItemCreateRequest']
export type ItemUpdate = components['schemas']['ItemUpdateRequest']
export type PlanCopy = components['schemas']['PlanCopyRequest']
export type PlanDayUpsert = components['schemas']['PlanDayUpsertRequest']

export function fetchPlanDays(from: string, to: string): Promise<PlanDays> {
  return apiFetch<PlanDays>('/plan/days', { query: { from, to } })
}

export function fetchPlanDay(day: string): Promise<PlanDay> {
  return apiFetch<PlanDay>(`/plan/days/${day}`)
}

export function upsertPlanDay(day: string, payload: PlanDayUpsert): Promise<PlanDay> {
  return apiFetch<PlanDay>(`/plan/days/${day}`, { method: 'PUT', json: payload })
}

export function createMeal(day: string, payload: MealCreate): Promise<PlanDay> {
  return apiFetch<PlanDay>(`/plan/days/${day}/meals`, { method: 'POST', json: payload })
}

export function updateMeal(mealId: number, payload: MealUpdate): Promise<PlanDay> {
  return apiFetch<PlanDay>(`/plan/meals/${mealId}`, { method: 'PATCH', json: payload })
}

export function deleteMeal(mealId: number): Promise<PlanDay> {
  return apiFetch<PlanDay>(`/plan/meals/${mealId}`, { method: 'DELETE' })
}

export function addItem(mealId: number, payload: ItemCreate): Promise<PlanDay> {
  return apiFetch<PlanDay>(`/plan/meals/${mealId}/items`, { method: 'POST', json: payload })
}

export function updateItem(itemId: number, payload: ItemUpdate): Promise<PlanDay> {
  return apiFetch<PlanDay>(`/plan/items/${itemId}`, { method: 'PATCH', json: payload })
}

export function deleteItem(itemId: number): Promise<PlanDay> {
  return apiFetch<PlanDay>(`/plan/items/${itemId}`, { method: 'DELETE' })
}

/** Zwraca PROPOZYCJĘ mnożnika — zapis to osobny, jawny PATCH pozycji. */
export function fitItemToTarget(itemId: number): Promise<FitToTarget> {
  return apiFetch<FitToTarget>(`/plan/items/${itemId}/fit-to-target`, { method: 'POST' })
}

export function copyPlan(payload: PlanCopy): Promise<PlanDays> {
  return apiFetch<PlanDays>('/plan/copy', { method: 'POST', json: payload })
}
