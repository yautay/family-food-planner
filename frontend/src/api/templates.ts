/**
 * Wywołania szablonów dnia/tygodnia i cykli: `/templates/*`, `/cycles`.
 * Typy z `generated.ts` (05_FRONTEND §2) — ręcznych interfejsów nie piszemy.
 *
 * Pydantic rozdziela kontrakt payloadu na dwa komponenty OpenAPI: `-Input`
 * (zapis: liczba ALBO string dziesiętny) i `-Output` (odczyt: zawsze string,
 * ADR-008). To nie przypadek generatora — to ten sam podział, co w backendzie,
 * więc trzymamy oba aliasy i używamy właściwego po właściwej stronie.
 */

import { apiFetch } from '@/api/client'
import type { components } from '@/api/generated'

export type DayTemplatePayload = components['schemas']['DayTemplatePayload-Output']
export type DayTemplatePayloadInput = components['schemas']['DayTemplatePayload-Input']
export type WeekTemplatePayload = components['schemas']['WeekTemplatePayload-Output']
export type WeekTemplatePayloadInput = components['schemas']['WeekTemplatePayload-Input']
export type TemplateMealPayloadInput = components['schemas']['TemplateMealPayload-Input']
export type TemplateItemPayloadInput = components['schemas']['TemplateItemPayload-Input']

export type TemplateSummary = components['schemas']['TemplateSummaryRead']
export type TemplateList = components['schemas']['TemplateListResponse']
export type DayTemplate = components['schemas']['DayTemplateReadFull']
export type WeekTemplate = components['schemas']['WeekTemplateReadFull']
export type DayTemplateWrite = components['schemas']['DayTemplateWriteRequest']
export type WeekTemplateWrite = components['schemas']['WeekTemplateWriteRequest']
export type InstantiateResult = components['schemas']['InstantiateResponse']

export type Cycle = components['schemas']['CycleRead']
export type CycleList = components['schemas']['CycleListResponse']
export type CycleWrite = components['schemas']['CycleWriteRequest']
export type CycleApply = components['schemas']['CycleApplyRequest']

// --- szablony dnia -------------------------------------------------------------------

export function fetchDayTemplates(): Promise<TemplateList> {
  return apiFetch<TemplateList>('/templates/days')
}

export function fetchDayTemplate(id: number): Promise<DayTemplate> {
  return apiFetch<DayTemplate>(`/templates/days/${id}`)
}

export function createDayTemplate(payload: DayTemplateWrite): Promise<DayTemplate> {
  return apiFetch<DayTemplate>('/templates/days', { method: 'POST', json: payload })
}

/** PUT nadpisuje CAŁY payload — edycji „per posiłek" nie ma (03_DATABASE §6). */
export function updateDayTemplate(id: number, payload: DayTemplateWrite): Promise<DayTemplate> {
  return apiFetch<DayTemplate>(`/templates/days/${id}`, { method: 'PUT', json: payload })
}

export function deleteDayTemplate(id: number): Promise<void> {
  return apiFetch<void>(`/templates/days/${id}`, { method: 'DELETE' })
}

export function instantiateDayTemplate(id: number, dates: string[]): Promise<InstantiateResult> {
  return apiFetch<InstantiateResult>(`/templates/days/${id}/instantiate`, {
    method: 'POST',
    json: { dates },
  })
}

// --- szablony tygodnia ---------------------------------------------------------------

export function fetchWeekTemplates(): Promise<TemplateList> {
  return apiFetch<TemplateList>('/templates/weeks')
}

export function fetchWeekTemplate(id: number): Promise<WeekTemplate> {
  return apiFetch<WeekTemplate>(`/templates/weeks/${id}`)
}

export function createWeekTemplate(payload: WeekTemplateWrite): Promise<WeekTemplate> {
  return apiFetch<WeekTemplate>('/templates/weeks', { method: 'POST', json: payload })
}

export function updateWeekTemplate(id: number, payload: WeekTemplateWrite): Promise<WeekTemplate> {
  return apiFetch<WeekTemplate>(`/templates/weeks/${id}`, { method: 'PUT', json: payload })
}

export function deleteWeekTemplate(id: number): Promise<void> {
  return apiFetch<void>(`/templates/weeks/${id}`, { method: 'DELETE' })
}

/** `weekStart` MUSI być poniedziałkiem — backend odpowiada 422 na inny dzień. */
export function instantiateWeekTemplate(id: number, weekStart: string): Promise<InstantiateResult> {
  return apiFetch<InstantiateResult>(`/templates/weeks/${id}/instantiate`, {
    method: 'POST',
    json: { week_start: weekStart },
  })
}

// --- cykle ---------------------------------------------------------------------------

export function fetchCycles(): Promise<CycleList> {
  return apiFetch<CycleList>('/cycles')
}

export function createCycle(payload: CycleWrite): Promise<Cycle> {
  return apiFetch<Cycle>('/cycles', { method: 'POST', json: payload })
}

export function updateCycle(id: number, payload: CycleWrite): Promise<Cycle> {
  return apiFetch<Cycle>(`/cycles/${id}`, { method: 'PUT', json: payload })
}

export function deleteCycle(id: number): Promise<void> {
  return apiFetch<void>(`/cycles/${id}`, { method: 'DELETE' })
}

export function applyCycle(id: number, range: CycleApply): Promise<InstantiateResult> {
  return apiFetch<InstantiateResult>(`/cycles/${id}/apply`, { method: 'POST', json: range })
}
