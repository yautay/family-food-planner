/**
 * Wywołania zakupów: `/shopping/*` (04_API §2).
 * Typy z `generated.ts` (05_FRONTEND §2) — ręcznych interfejsów nie piszemy.
 *
 * Podgląd generacji jest STANEM SERWERA (liczy go silnik z `params`), więc żyje
 * w TanStack Query, a nie w Pinia (ADR-007). W Pinia siedzi wyłącznie szkic
 * formularza — patrz `stores/shoppingDraft.ts`.
 */

import { apiFetch } from '@/api/client'
import type { components } from '@/api/generated'

export type RoundConfig = components['schemas']['RoundConfigRead']
export type RoundConfigList = components['schemas']['RoundConfigListResponse']
export type RoundConfigCreate = components['schemas']['RoundConfigCreateRequest']
export type RoundConfigUpdate = components['schemas']['RoundConfigUpdateRequest']
export type RoundMode = components['schemas']['RoundMode']
export type Generation = components['schemas']['GenerationRead']
export type GenerateRequest = components['schemas']['GenerateRequest']
export type ResolveRequest = components['schemas']['ResolveRequest']
export type PreviewRound = components['schemas']['PreviewRoundRead']
export type PreviewLine = components['schemas']['PreviewLineRead']
export type PreviewIssue = components['schemas']['PreviewIssueRead']
export type RetailOption = components['schemas']['RetailOptionRead']
export type FinalizeResponse = components['schemas']['FinalizeResponse']
export type ShoppingList = components['schemas']['ShoppingListRead']

export function fetchRoundConfigs(): Promise<RoundConfigList> {
  return apiFetch<RoundConfigList>('/shopping/round-configs')
}

export function createRoundConfig(payload: RoundConfigCreate): Promise<RoundConfig> {
  return apiFetch<RoundConfig>('/shopping/round-configs', { method: 'POST', json: payload })
}

export function updateRoundConfig(id: number, payload: RoundConfigUpdate): Promise<RoundConfig> {
  return apiFetch<RoundConfig>(`/shopping/round-configs/${id}`, {
    method: 'PATCH',
    json: payload,
  })
}

export function deleteRoundConfig(id: number): Promise<void> {
  return apiFetch<void>(`/shopping/round-configs/${id}`, { method: 'DELETE' })
}

/** POST `/shopping/generate` — zapisuje szkic generacji i zwraca podgląd. */
export function generateShopping(payload: GenerateRequest): Promise<Generation> {
  return apiFetch<Generation>('/shopping/generate', { method: 'POST', json: payload })
}

export function fetchGeneration(id: number): Promise<Generation> {
  return apiFetch<Generation>(`/shopping/generations/${id}`)
}

/**
 * Decyzje w podglądzie. Pole pominięte zostaje bez zmian, pole podane ZASTĘPUJE
 * cały zbiór — wysyłamy więc pełny stan zaznaczeń, nie różnicę.
 */
export function resolveGeneration(id: number, payload: ResolveRequest): Promise<Generation> {
  return apiFetch<Generation>(`/shopping/generations/${id}/resolve`, {
    method: 'POST',
    json: payload,
  })
}

export function finalizeGeneration(id: number): Promise<FinalizeResponse> {
  return apiFetch<FinalizeResponse>(`/shopping/generations/${id}/finalize`, { method: 'POST' })
}

/** DELETE jest MIĘKKIE: generacja dostaje status `discarded` (D10). */
export function discardGeneration(id: number): Promise<void> {
  return apiFetch<void>(`/shopping/generations/${id}`, { method: 'DELETE' })
}
