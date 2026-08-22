/**
 * Publiczna lista zakupowa (`/api/v1/public/lists/*`, ADR-010).
 *
 * OSOBNY, lekki klient — świadomie NIE `apiFetch`. Trzy powody, wszystkie
 * z karty B11 (Implementation Notes pkt 1) i 07_SECURITY:
 *
 * 1. **Bez cookies.** `credentials: 'omit'` znaczy, że strona z linkiem nie
 *    wysyła cudzej sesji, nawet gdy ktoś otworzy link na zalogowanej
 *    przeglądarce. Autoryzuje token z URL-a i nic więcej.
 * 2. **Bez tokenu CSRF.** Ścieżka `/api/v1/public/` jest z niego zwolniona po
 *    stronie serwera, więc doklejanie nagłówka byłoby udawaniem ochrony.
 * 3. **410 to normalny stan, nie awaria.** Wygasły albo odwołany link ma
 *    pokazać przyjazny ekran, dlatego rozróżniamy go typem błędu, a nie
 *    parsowaniem komunikatu w komponencie.
 *
 * Rozbudowa `client.ts` o tryby warunkowe byłaby gorsza: jeden `if` w warstwie
 * HTTP całej aplikacji łatwo pomylić, a wtedy publiczna strona wysyłałaby
 * sesję rodziny osobie z linkiem.
 */

import { API_PREFIX } from '@/api/client'
import type { components } from '@/api/generated'

export type PublicList = components['schemas']['PublicListRead']
export type PublicListItem = components['schemas']['PublicListItemRead']

/** Ekran „wygasło" pokrywa 410 ORAZ 404 — nie zdradzamy, czy token istniał. */
export class PublicListUnavailableError extends Error {
  constructor() {
    super('Ta lista zakupowa już wygasła lub została usunięta.')
    this.name = 'PublicListUnavailableError'
  }
}

/** Każdy inny błąd (sieć, 5xx, rate limit) — strona pokazuje „spróbuj ponownie". */
export class PublicListRequestError extends Error {
  readonly status: number

  constructor(status: number) {
    super('Nie udało się wczytać listy. Odśwież stronę i spróbuj ponownie.')
    this.name = 'PublicListRequestError'
    this.status = status
  }
}

const UNAVAILABLE_STATUSES = new Set([404, 410])

async function publicFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_PREFIX}/public${path}`, {
      ...init,
      // Bez cookies: token z URL-a jest JEDYNYM upoważnieniem tej strony.
      credentials: 'omit',
      headers: { Accept: 'application/json', ...(init.headers ?? {}) },
    })
  } catch {
    throw new PublicListRequestError(0)
  }

  if (UNAVAILABLE_STATUSES.has(response.status)) {
    throw new PublicListUnavailableError()
  }
  if (!response.ok) {
    throw new PublicListRequestError(response.status)
  }
  return (await response.json()) as T
}

export function fetchPublicList(token: string): Promise<PublicList> {
  return publicFetch<PublicList>(`/lists/${encodeURIComponent(token)}`)
}

/** Token pozwala zmienić WYŁĄCZNIE `checked` — innych pól tu nie ma (ADR-010). */
export function checkPublicListItem(
  token: string,
  itemId: number,
  checked: boolean,
): Promise<PublicListItem> {
  return publicFetch<PublicListItem>(`/lists/${encodeURIComponent(token)}/items/${itemId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ checked }),
  })
}
