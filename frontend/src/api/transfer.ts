/**
 * Transfer danych: `/transfer/export` i `/transfer/import` (04_API §2, BATCH_14).
 * Typy z `generated.ts` (05_FRONTEND §2) — ręcznych interfejsów nie piszemy.
 *
 * Eksport wyłamuje się z `apiFetch`, bo odpowiedzią jest ZIP, a nie JSON:
 * `apiFetch` woła `response.json()` i na binarnej treści by padł. Zostaje
 * jednak przy TYCH SAMYCH regułach (cookie sesji + nagłówek CSRF), więc
 * `downloadExport` składa je z eksportowanych stałych klienta, a nie z własnych.
 */

import {
  API_PREFIX,
  ApiError,
  CSRF_COOKIE,
  CSRF_HEADER,
  apiFetch,
  observeResponse,
  readCookie,
} from '@/api/client'
import type { components } from '@/api/generated'

export type TransferScope = components['schemas']['TransferScope']
export type DryRunReport = components['schemas']['DryRunReport']
export type Collision = components['schemas']['CollisionRead']
export type CollisionAction = components['schemas']['CollisionAction']
export type CollisionDecision = components['schemas']['CollisionDecision']
export type ImportSummary = components['schemas']['ImportSummary']

/** Nazwa pliku, gdy serwer nie poda `Content-Disposition` (np. stary proxy). */
function fallbackFilename(): string {
  return `pasnik-export-${new Date().toISOString().slice(0, 10)}.zip`
}

/** `attachment; filename="x.zip"` → `x.zip`; brak nagłówka → nazwa zastępcza. */
export function filenameFromDisposition(header: string | null): string {
  const captured = header?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i)?.[1]
  return captured ? decodeURIComponent(captured) : fallbackFilename()
}

export interface ExportedFile {
  blob: Blob
  filename: string
}

/**
 * Pobiera archiwum eksportu. Zwraca blob — zapis na dysk robi komponent,
 * bo tylko on wie, czy działa w przeglądarce (test jednostkowy nie ma DOM-u).
 */
export async function downloadExport(scope: TransferScope = 'user'): Promise<ExportedFile> {
  const token = readCookie(CSRF_COOKIE)
  const response = await fetch(`${API_PREFIX}/transfer/export?scope=${scope}`, {
    method: 'POST',
    credentials: 'include',
    headers: token ? { [CSRF_HEADER]: token } : {},
  })
  // Te same efekty uboczne, co w `apiFetch` — wygasła sesja MUSI odesłać
  // na `/login`, a nie tylko pokazać czerwony komunikat na stronie.
  observeResponse(response)

  if (!response.ok) {
    let message = 'Nie udało się przygotować eksportu.'
    let code = 'unexpected_error'
    try {
      const body = (await response.json()) as { error?: { code: string; message: string } }
      if (body.error) {
        message = body.error.message
        code = body.error.code
      }
    } catch {
      // Odpowiedź bez JSON-a (proxy, timeout) — zostaje komunikat domyślny.
    }
    throw new ApiError(response.status, { code, message, details: {} })
  }
  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(response.headers.get('Content-Disposition')),
  }
}

/** Wgranie archiwum → raport DRY-RUN. Serwer NIC przy tym nie zapisuje. */
export function uploadForDryRun(file: File): Promise<DryRunReport> {
  const form = new FormData()
  form.append('file', file)
  return apiFetch<DryRunReport>('/transfer/import', { method: 'POST', form })
}

/** Zastosowanie importu z decyzjami dla kolizji (pominięta = „użyj istniejącego"). */
export function applyImport(
  importId: string,
  decisions: CollisionDecision[],
): Promise<ImportSummary> {
  return apiFetch<ImportSummary>(`/transfer/import/${importId}/apply`, {
    method: 'POST',
    json: { decisions },
  })
}
