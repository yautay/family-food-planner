import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, apiFetch, setUnauthorizedHandler } from './client'

function mockFetch(response: Response): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(response)),
  )
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function requestHeaders(): Headers {
  const mocked = fetch as unknown as ReturnType<typeof vi.fn>
  const [, init] = mocked.mock.calls[0] as [string, RequestInit]
  return init.headers as Headers
}

describe('apiFetch', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    setUnauthorizedHandler(undefined)
    document.cookie = 'csrf_token=; Max-Age=0; path=/'
  })

  it('zwraca sparsowane ciało odpowiedzi 2xx', async () => {
    mockFetch(jsonResponse({ status: 'ok', version: '0.1.0' }))

    const result = await apiFetch<{ status: string }>('/health')

    expect(result.status).toBe('ok')
  })

  it('woła backend pod prefiksem /api/v1 i wysyła cookie sesji', async () => {
    mockFetch(jsonResponse({ status: 'ok' }))

    await apiFetch('/health', { query: { verbose: true, pominiete: undefined } })

    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/health?verbose=true',
      expect.objectContaining({ credentials: 'include' }),
    )
  })

  it('mapuje kształt błędu 04_API na ApiError', async () => {
    mockFetch(
      jsonResponse(
        { error: { code: 'not_found', message: 'Nie znaleziono zasobu.', details: {} } },
        404,
      ),
    )

    await expect(apiFetch('/nope')).rejects.toMatchObject({
      status: 404,
      code: 'not_found',
      message: 'Nie znaleziono zasobu.',
    })
  })

  it('odpowiedź bez kontraktu błędu daje komunikat zastępczy po polsku', async () => {
    mockFetch(new Response('<html>502</html>', { status: 502 }))

    const error = await apiFetch('/health').catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('unexpected_error')
    expect((error as ApiError).message).toContain('Nie udało się połączyć z serwerem')
  })

  it('błąd sieci zgłasza ApiError ze statusem 0', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    )

    await expect(apiFetch('/health')).rejects.toMatchObject({ status: 0, code: 'network_error' })
  })
})

describe('CSRF (double-submit cookie, 07_SECURITY §3)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    document.cookie = 'csrf_token=; Max-Age=0; path=/'
  })

  it('dokleja X-CSRF-Token z cookie do mutacji', async () => {
    document.cookie = 'csrf_token=token-z-cookie'
    mockFetch(jsonResponse({}))

    await apiFetch('/auth/logout', { method: 'POST' })

    expect(requestHeaders().get('X-CSRF-Token')).toBe('token-z-cookie')
  })

  it('nie dokleja nagłówka do zapytań odczytu', async () => {
    document.cookie = 'csrf_token=token-z-cookie'
    mockFetch(jsonResponse({ status: 'ok' }))

    await apiFetch('/auth/me')

    expect(requestHeaders().has('X-CSRF-Token')).toBe(false)
  })

  it('czyta cookie z prefiksem __Host- (nazwa produkcyjna, B17)', async () => {
    // jsdom EGZEKWUJE reguły prefiksu (`__Host-` wymaga Secure, a origin testu to
    // http), więc cookie podstawiamy przez getter — liczy się to, że klient nie
    // zna nazwy z literału i znajduje wariant produkcyjny.
    const cookieGetter = vi.spyOn(document, 'cookie', 'get')
    cookieGetter.mockReturnValue('inne=1; __Host-csrf_token=token-prod')
    mockFetch(jsonResponse({}))

    await apiFetch('/auth/logout', { method: 'POST' })

    expect(requestHeaders().get('X-CSRF-Token')).toBe('token-prod')
    cookieGetter.mockRestore()
  })

  it('bez cookie nie wysyła pustego nagłówka', async () => {
    mockFetch(jsonResponse({}))

    await apiFetch('/auth/logout', { method: 'POST' })

    expect(requestHeaders().has('X-CSRF-Token')).toBe(false)
  })
})

describe('reakcja na 401', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    setUnauthorizedHandler(undefined)
  })

  it('woła zarejestrowany handler przy wygasłej sesji', async () => {
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    mockFetch(
      jsonResponse({ error: { code: 'unauthorized', message: 'Wymagane zalogowanie.' } }, 401),
    )

    await expect(apiFetch('/auth/me')).rejects.toBeInstanceOf(ApiError)
    expect(onUnauthorized).toHaveBeenCalledOnce()
  })

  it('nie woła handlera przy odpowiedzi poprawnej', async () => {
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    mockFetch(jsonResponse({ status: 'ok' }))

    await apiFetch('/health')

    expect(onUnauthorized).not.toHaveBeenCalled()
  })
})
