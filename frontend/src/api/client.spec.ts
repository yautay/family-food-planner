import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, apiFetch } from './client'

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

describe('apiFetch', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
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
