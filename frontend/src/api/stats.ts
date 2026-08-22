/**
 * Wywołania statystyk: `GET /stats/daily`.
 * Typy z `generated.ts` (05_FRONTEND §2) — ręcznych interfejsów nie piszemy.
 *
 * Endpoint jest tylko do odczytu: agregaty liczą się w locie z planu i celów,
 * nic nie jest cache'owane po stronie serwera (02_DOMAIN §13.2), a po stronie
 * przeglądarki trzyma je TanStack Query — nie Pinia (ADR-007).
 */

import { apiFetch } from '@/api/client'
import type { components } from '@/api/generated'

export type DailyStats = components['schemas']['StatsDailyResponse']
export type StatsDay = components['schemas']['StatsDayRead']
export type StatsGoal = components['schemas']['StatsGoalRead']
export type StatsStatus = components['schemas']['StatsStatusRead']
export type StatsSummary = components['schemas']['StatsSummaryRead']

/** Ten sam sufit, co po stronie serwera (`MAX_STATS_RANGE_DAYS`) — 422 przy przekroczeniu. */
export const MAX_STATS_RANGE_DAYS = 92

export function fetchDailyStats(from: string, to: string): Promise<DailyStats> {
  return apiFetch<DailyStats>('/stats/daily', { query: { from, to } })
}
