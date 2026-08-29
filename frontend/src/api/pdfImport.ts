/**
 * Import jadłospisów PDF: `/import/pdf` i `/import/jobs` (04_API §2, BATCH_15).
 * Typy z `generated.ts` (05_FRONTEND §2) — ręcznych interfejsów nie piszemy.
 *
 * Upload idzie przez `apiFetch` z `FormData`, więc dostaje cookie sesji
 * i nagłówek CSRF za darmo — plik jest zwykłą mutacją, a nie osobnym kanałem.
 * Nazwa modułu to `pdfImport`, nie `import`: `import` jest w TS słowem
 * kluczowym i `import * from '@/api/import'` czyta się jak błąd składni.
 */

import { apiFetch } from '@/api/client'
import type { components } from '@/api/generated'

export type ImportJobStatus = components['schemas']['ImportJobStatus']
export type ImportJobSummary = components['schemas']['ImportJobSummary']
export type ImportJobDetail = components['schemas']['ImportJobDetail']
export type ImportJobListResponse = components['schemas']['ImportJobListResponse']

/** Sufit listy jobów — importów jest z natury mało, paginacji nie pokazujemy. */
export const JOBS_PAGE_SIZE = 50

/** Limit z 07_SECURITY §6. Walidacja po stronie klienta to UX; prawdą jest serwer. */
export const MAX_PDF_MB = 25

/**
 * Kształt `parse_report`. Świadomie NIE pochodzi z `generated.ts`: backend
 * wystawia to pole jako wolny obiekt JSON (jego kontraktem jest
 * `parser.build_parse_report`, nie schemat Pydantic), więc typ opisujemy tu
 * raz i czytamy przez `parseReportOf`, zamiast rozsypywać rzutowania po widoku.
 */
export interface DayChecksum {
  day: string
  expected: string | null
  computed: string
  ok: boolean
}

export interface ParseReport {
  pages: { total: number; days: number; skipped_shopping: number; skipped_exchanges: number }
  days: number
  meals: number
  staged_recipes: number
  ingredients: number
  issues: { blocker: number; warning: number }
  match: { exact: number; none: number }
  day_checksums: DayChecksum[]
  warnings: string[]
}

/** `parse_report` joba albo `null`, gdy job nie doszedł do parsowania. */
export function parseReportOf(job: ImportJobDetail | null | undefined): ParseReport | null {
  return (job?.parse_report as ParseReport | undefined) ?? null
}

/** Procent składników zmapowanych dokładnie; `null`, gdy nie ma czego liczyć. */
export function exactMatchPercent(report: ParseReport | null): number | null {
  if (!report) return null
  const total = report.match.exact + report.match.none
  return total === 0 ? null : Math.round((report.match.exact / total) * 100)
}

/** Wgranie pliku → job (serwer parsuje synchronicznie i zwraca gotowy raport). */
export function uploadPdf(file: File): Promise<ImportJobDetail> {
  const form = new FormData()
  form.append('file', file)
  return apiFetch<ImportJobDetail>('/import/pdf', { method: 'POST', form })
}

/** Lista importów użytkownika, najnowsze pierwsze. */
export function listJobs(): Promise<ImportJobListResponse> {
  return apiFetch<ImportJobListResponse>('/import/jobs', {
    query: { limit: JOBS_PAGE_SIZE, offset: 0 },
  })
}

/** Szczegóły importu razem z pełnym raportem parsowania. */
export function getJob(id: number): Promise<ImportJobDetail> {
  return apiFetch<ImportJobDetail>(`/import/jobs/${id}`)
}

/** Usunięcie importu — kasuje staging i plik na dysku. */
export function deleteJob(id: number): Promise<void> {
  return apiFetch<void>(`/import/jobs/${id}`, { method: 'DELETE' })
}
