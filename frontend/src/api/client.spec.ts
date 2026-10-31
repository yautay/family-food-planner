import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, apiFetch, setUnauthorizedHandler } from './client'
import { advanceSessionGeneration } from '@/lib/sessionGeneration'
import { clockSkewMs, resetClockSkew } from '@/lib/offline/clock'

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

  it('czas odczytu body nie przesuwa korekty zegara LWW z nagłówków', async () => {
    resetClockSkew()
    const initial = Date.parse('2031-01-01T12:00:00Z')
    const now = vi.spyOn(Date, 'now').mockReturnValue(initial)
    let finish!: (value: unknown) => void
    const response = jsonResponse({})
    response.headers.set('Date', new Date(initial + 60_000).toUTCString())
    vi.spyOn(response, 'json').mockReturnValue(
      new Promise((resolve) => {
        finish = resolve
      }),
    )
    mockFetch(response)
    const pending = apiFetch('/shopping/lists/1')
    await Promise.resolve()
    expect(clockSkewMs()).toBe(60_000)
    now.mockReturnValue(initial + 5 * 60_000)
    finish({ ok: true })
    await pending
    expect(clockSkewMs()).toBe(60_000)
    resetClockSkew()
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

  it('spóźnione 401 A po zmianie cookie nie wylogowuje B', async () => {
    document.cookie = 'csrf_token=credential-A; Path=/'
    let respond!: (value: Response) => void
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            respond = resolve
          }),
      ),
    )
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    const pending = apiFetch('/plan/days').catch((error: unknown) => error)
    document.cookie = 'csrf_token=credential-B; Path=/'
    respond(jsonResponse({ error: { code: 'unauthorized', message: 'expired', details: {} } }, 401))
    await pending
    expect(onUnauthorized).not.toHaveBeenCalled()
    document.cookie = 'csrf_token=; Max-Age=0; Path=/'
  })

  it('zmiana cookie podczas await body JSON odrzuca stare dane przed onSuccess', async () => {
    document.cookie = 'csrf_token=credential-A; Path=/'
    let body!: (value: unknown) => void
    const response = jsonResponse({})
    vi.spyOn(response, 'json').mockReturnValue(
      new Promise((resolve) => {
        body = resolve
      }),
    )
    mockFetch(response)
    const pending = apiFetch('/auth/me/ui-settings', { method: 'PATCH', json: {} })
    await Promise.resolve()
    document.cookie = 'csrf_token=credential-B; Path=/'
    body({ account: 'A' })
    await expect(pending).rejects.toBeInstanceOf(Error)
    document.cookie = 'csrf_token=; Max-Age=0; Path=/'
  })

  it('stare 401 po zmianie generacji tej samej sesji/cookie także nie wylogowuje obecnego konta', async () => {
    let respond!: (value: Response) => void
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            respond = resolve
          }),
      ),
    )
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    const pending = apiFetch('/recipes').catch((error: unknown) => error)
    advanceSessionGeneration()
    respond(jsonResponse({ error: { code: 'unauthorized', message: 'expired', details: {} } }, 401))
    await pending
    expect(handler).not.toHaveBeenCalled()
  })

  it('zmiana sesji podczas odczytu body błędu 401 nie uruchamia handlera', async () => {
    let body!: (value: unknown) => void
    const response = jsonResponse({}, 401)
    vi.spyOn(response, 'json').mockReturnValue(
      new Promise((resolve) => {
        body = resolve
      }),
    )
    mockFetch(response)
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    const pending = apiFetch('/recipes').catch((error: unknown) => error)
    await Promise.resolve()
    advanceSessionGeneration()
    body({ error: { code: 'unauthorized', message: 'expired', details: {} } })
    await pending
    expect(handler).not.toHaveBeenCalled()
  })

  it.each(['/auth/login', '/auth/logout'])(
    'normalne %s akceptuje oczekiwaną zmianę cookie po nagłówkach',
    async (path) => {
      document.cookie = 'csrf_token=before-auth; Path=/'
      vi.stubGlobal(
        'fetch',
        vi.fn(async () => {
          document.cookie = 'csrf_token=after-auth; Path=/'
          return jsonResponse({ ok: true })
        }),
      )
      await expect(apiFetch(path, { method: 'POST' })).resolves.toEqual({ ok: true })
      document.cookie = 'csrf_token=; Max-Age=0; Path=/'
    },
  )
})
