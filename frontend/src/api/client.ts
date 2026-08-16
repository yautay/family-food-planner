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

export const API_PREFIX = '/api/v1'

/** Cookie CSRF ustawiane przez backend — celowo bez HttpOnly. */
export const CSRF_COOKIE = 'csrf_token'
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

type UnauthorizedHandler = () => void

let unauthorizedHandler: UnauthorizedHandler | undefined

/**
 * Rejestruje reakcję na 401 (wywoływane raz, w `main.ts`). Dzięki temu klient
 * HTTP nie musi znać routera ani store'ów.
 */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | undefined): void {
  unauthorizedHandler = handler
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
  /** Parametry zapytania; wartości `undefined` są pomijane. */
  query?: Record<string, string | number | boolean | undefined>
}

function buildUrl(path: string, query: ApiRequestOptions['query']): string {
  const url = `${API_PREFIX}${path.startsWith('/') ? path : `/${path}`}`
  if (!query) {
    return url
  }
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) {
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
  const { json, query, headers, ...rest } = options
  const method = (rest.method ?? 'GET').toUpperCase()

  const requestHeaders = new Headers(headers)
  requestHeaders.set('Accept', 'application/json')
  if (json !== undefined) {
    requestHeaders.set('Content-Type', 'application/json')
  }
  if (UNSAFE_METHODS.has(method) && !requestHeaders.has(CSRF_HEADER)) {
    const token = readCookie(CSRF_COOKIE)
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
      body: json === undefined ? undefined : JSON.stringify(json),
    })
  } catch (cause) {
    throw new ApiError(
      0,
      { code: 'network_error', message: FALLBACK_MESSAGE, details: {} },
      { cause },
    )
  }

  if (response.status === 401) {
    unauthorizedHandler?.()
  }

  if (!response.ok) {
    throw await toApiError(response)
  }

  if (response.status === 204 || response.headers.get('Content-Length') === '0') {
    return undefined as T
  }

  return (await response.json()) as T
}
