/**
 * Warstwa HTTP frontendu (05_FRONTEND §2).
 *
 * Jedyne miejsce, w którym aplikacja woła backend. Zasady:
 * - cookie sesyjne zawsze wysyłane (`credentials: 'include'`) — ADR-003,
 * - odpowiedź błędu w kształcie 04_API §1 mapowana na `ApiError`,
 * - typy odpowiedzi pochodzą z `generated.ts` (task fe-types), nie z ręcznych
 *   interfejsów.
 *
 * Nagłówek `X-CSRF-Token` doklejany jest do metod zmieniających stan
 * (double-submit cookie, 07_SECURITY §3); odpowiedź 401 zgłaszana jest
 * zarejestrowanemu handlerowi (główna aplikacja czyści wtedy sesję).
 */

import { recordServerDate } from '@/lib/offline/clock'
import {
  captureSessionGeneration,
  isSessionGenerationCurrent,
  StaleSessionResponseError,
} from '@/lib/sessionGeneration'

export const API_PREFIX = '/api/v1'

/**
 * Cookie CSRF ustawiane przez backend — celowo bez HttpOnly.
 *
 * Nazwa zależy od środowiska backendu (07_SECURITY §3, BATCH_17): na produkcji
 * cookie nosi prefiks `__Host-` (wiąże je z jednym hostem, wymaga `Secure`),
 * w dev/test prefiksu nie ma, bo `http://localhost` nie ma TLS. Przeglądarka
 * nie zna `APP_ENV`, więc sprawdza obie kandydatki — pierwsza z wartością wygrywa.
 * Literał nazwy w kodzie klienta = po zmianie prefiksu double-submit cicho
 * przestaje działać, a testy tego nie złapią (jadą po HTTP).
 */
export const CSRF_COOKIE_CANDIDATES = ['__Host-csrf_token', 'csrf_token'] as const
export const CSRF_HEADER = 'X-CSRF-Token'

/** Metody wymagające tokenu CSRF (zgodnie z middleware backendu). */
const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

/** Odczyt cookie po nazwie; `document` może nie istnieć (SSR/testy node). */
export function readCookie(name: string): string | undefined {
  if (typeof document === 'undefined') {
    return undefined
  }
  const prefix = `${name}=`
  for (const part of document.cookie.split(';')) {
    const trimmed = part.trim()
    if (trimmed.startsWith(prefix)) {
      return decodeURIComponent(trimmed.slice(prefix.length))
    }
  }
  return undefined
}

/** Wartość cookie CSRF niezależnie od tego, pod którą nazwą ustawił je backend. */
export function readCsrfToken(): string | undefined {
  for (const name of CSRF_COOKIE_CANDIDATES) {
    const value = readCookie(name)
    if (value) {
      return value
    }
  }
  return undefined
}

type UnauthorizedHandler = () => void

let unauthorizedHandler: UnauthorizedHandler | undefined

/**
 * Rejestruje reakcję na 401 (wywoływane raz, w `main.ts`). Dzięki temu klient
 * HTTP nie musi znać routera ani store'ów.
 */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | undefined): void {
  unauthorizedHandler = handler
}

/**
 * Efekty uboczne, które MUSI wykonać każda odpowiedź backendu — także ta spoza
 * `apiFetch` (eksport transferu pobiera ZIP-a własnym `fetch`, bo `apiFetch`
 * czyta JSON). Bez tego wygasła sesja na takiej ścieżce nie odsyłałaby na
 * `/login`, a kolejka offline nie znałaby zegara serwera (ADR-009).
 */
export interface SessionRequestTicket {
  readonly generation: number
  /** Wyłącznie transient memory; nigdy persistence/logi. */
  readonly credential: string | undefined
}

export function captureSessionRequest(): SessionRequestTicket {
  return { generation: captureSessionGeneration(), credential: readCsrfToken() }
}

export function assertSessionRequestCurrent(ticket: SessionRequestTicket): void {
  if (!isSessionGenerationCurrent(ticket.generation) || ticket.credential !== readCsrfToken()) {
    throw new StaleSessionResponseError()
  }
}

/** Korekta LWW następuje przy nagłówkach, niezależnie od czasu odczytu body. */
export function observeResponseHeaders(response: Response, ticket: SessionRequestTicket): void {
  assertSessionRequestCurrent(ticket)
  recordServerDate(response.headers.get('Date'))
}

/** Efekty sesji dopiero po sprawdzeniu generacji kompletnej odpowiedzi. */
export function observeResponse(response: Response, ticket: SessionRequestTicket): void {
  assertSessionRequestCurrent(ticket)
  if (response.status === 401) {
    unauthorizedHandler?.()
  }
}

export interface ApiErrorBody {
  code: string
  message: string
  details: Record<string, unknown>
}

/** Błąd zwrócony przez API w kontrakcie `{"error": {code, message, details}}`. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>

  constructor(status: number, body: ApiErrorBody, options?: ErrorOptions) {
    super(body.message, options)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code
    this.details = body.details
  }
}

const FALLBACK_MESSAGE = 'Nie udało się połączyć z serwerem. Sprawdź połączenie i spróbuj ponownie.'

export interface ApiRequestOptions extends Omit<RequestInit, 'body'> {
  /** Ciało żądania — serializowane do JSON (pomijane dla GET). */
  json?: unknown
  /** Ciało multipart (upload plików) — wyklucza się z `json`; Content-Type
   *  ustawia przeglądarka (boundary), więc nagłówka nie dotykamy. */
  form?: FormData
  /** Parametry zapytania; wartości `undefined` są pomijane, tablica =
   *  parametr powtórzony (`?tag=1&tag=2`). */
  query?: Record<string, string | number | boolean | undefined | readonly (string | number)[]>
}

function buildUrl(path: string, query: ApiRequestOptions['query']): string {
  const url = `${API_PREFIX}${path.startsWith('/') ? path : `/${path}`}`
  if (!query) {
    return url
  }
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined) {
      continue
    }
    if (Array.isArray(value)) {
      for (const item of value) {
        params.append(key, String(item))
      }
    } else {
      params.append(key, String(value))
    }
  }
  const queryString = params.toString()
  return queryString ? `${url}?${queryString}` : url
}

function isApiErrorBody(value: unknown): value is { error: ApiErrorBody } {
  if (typeof value !== 'object' || value === null || !('error' in value)) {
    return false
  }
  const error = (value as { error: unknown }).error
  return (
    typeof error === 'object' &&
    error !== null &&
    typeof (error as ApiErrorBody).code === 'string' &&
    typeof (error as ApiErrorBody).message === 'string'
  )
}

async function toApiError(response: Response): Promise<ApiError> {
  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    payload = undefined
  }
  if (isApiErrorBody(payload)) {
    return new ApiError(response.status, {
      code: payload.error.code,
      message: payload.error.message,
      details: payload.error.details ?? {},
    })
  }
  return new ApiError(response.status, {
    code: 'unexpected_error',
    message: FALLBACK_MESSAGE,
    details: {},
  })
}

/**
 * Wywołanie API. Rzuca `ApiError` dla odpowiedzi != 2xx oraz dla błędu sieci
 * (wtedy `status = 0`) — obsługę komunikatu robi warstwa wywołująca.
 */
export async function apiFetch<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const ticket = captureSessionRequest()
  const { json, form, query, headers, ...rest } = options
  const method = (rest.method ?? 'GET').toUpperCase()

  const requestHeaders = new Headers(headers)
  requestHeaders.set('Accept', 'application/json')
  if (json !== undefined) {
    requestHeaders.set('Content-Type', 'application/json')
  }
  if (UNSAFE_METHODS.has(method) && !requestHeaders.has(CSRF_HEADER)) {
    const token = readCsrfToken()
    if (token) {
      requestHeaders.set(CSRF_HEADER, token)
    }
  }

  let response: Response
  try {
    response = await fetch(buildUrl(path, query), {
      ...rest,
      headers: requestHeaders,
      credentials: 'include',
      body: form ?? (json === undefined ? undefined : JSON.stringify(json)),
    })
  } catch (cause) {
    assertSessionRequestCurrent(ticket)
    throw new ApiError(
      0,
      { code: 'network_error', message: FALLBACK_MESSAGE, details: {} },
      { cause },
    )
  }

  // Login/logout normalnie zmieniają cookie przy nagłówkach. Późniejsza
  // zmiana podczas czytania body jest już inną sesją, tak jak dla reszty API.
  const changesCookie = method === 'POST' && ['/auth/login', '/auth/logout'].includes(path)
  if (!isSessionGenerationCurrent(ticket.generation)) throw new StaleSessionResponseError()
  const responseTicket = changesCookie ? { ...ticket, credential: readCsrfToken() } : ticket
  observeResponseHeaders(response, responseTicket)

  if (!response.ok) {
    const error = await toApiError(response)
    observeResponse(response, responseTicket)
    throw error
  }

  if (response.status === 204 || response.headers.get('Content-Length') === '0') {
    observeResponse(response, responseTicket)
    return undefined as T
  }

  const result = (await response.json()) as T
  observeResponse(response, responseTicket)
  return result
}
