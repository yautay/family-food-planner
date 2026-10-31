import { webcrypto } from 'node:crypto'
import { TextEncoder } from 'node:util'

import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import type { CurrentUser, fetchCurrentUser as RealFetchCurrentUser } from '@/api/auth'
import { StaleSessionResponseError } from '@/lib/sessionGeneration'
import {
  clearPrivateOfflineSession,
  confirmPrivateOfflineSession,
} from '@/lib/offline/privateSession'

import { authGuard, routes, scrollBehavior } from './router'
import { createMemoryHistory, createRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'

const { fetchCurrentUser } = vi.hoisted(() => ({ fetchCurrentUser: vi.fn() }))

vi.mock('@/api/auth', () => ({
  fetchCurrentUser,
  loginRequest: vi.fn(),
  logoutRequest: vi.fn(),
}))

const USER = {
  id: 1,
  email: 'anna@example.com',
  display_name: 'Anna',
  role: 'user' as const,
  ui_settings: {},
  household: null,
}

function target(fullPath: string, meta: Record<string, unknown> = {}) {
  return { fullPath, meta }
}

describe('guard routera', () => {
  let pinia: ReturnType<typeof createPinia>
  beforeEach(() => {
    vi.stubGlobal('crypto', webcrypto)
    vi.stubGlobal('TextEncoder', TextEncoder)
    clearPrivateOfflineSession()
    pinia = createPinia()
    setActivePinia(pinia)
    vi.clearAllMocks()
  })
  afterEach(() => {
    disposePinia(pinia)
    clearPrivateOfflineSession()
    document.cookie = 'csrf_token=; Max-Age=0; Path=/'
    vi.unstubAllGlobals()
  })

  it('bez sesji odsyła na /login i zapamiętuje adres powrotu', async () => {
    fetchCurrentUser.mockResolvedValue(null)

    const result = await authGuard(
      target('/plan-dnia/2031-03-05?from=2031-03-03&to=2031-03-09'),
      useAuthStore(),
    )

    expect(result).toEqual({
      name: 'login',
      query: { next: '/plan-dnia/2031-03-05?from=2031-03-03&to=2031-03-09' },
    })
  })

  it('z sesją przepuszcza na trasę chronioną', async () => {
    fetchCurrentUser.mockResolvedValue(USER)

    expect(await authGuard(target('/plan-dnia'), useAuthStore())).toBe(true)
  })

  it('zalogowanego na /login przenosi do planu dnia', async () => {
    fetchCurrentUser.mockResolvedValue(USER)

    const result = await authGuard(target('/login', { public: true }), useAuthStore())

    expect(result).toEqual({ name: 'plan-dnia' })
  })

  it.each([
    '/zakupy/listy/12?sklep=4#pozycja-8',
    '/przepisy?q=50%25+czekolady&tag=1&selectedDate=2029-06-04',
    '/przepisy?q=żółty+ser+%26+chleb+%23+1&tag=1&tag=2#szczegóły',
    '/przepisy?q=%C5%BC%C3%B3%C5%82ty%20ser%20%26%20chleb%20%23%201',
  ])('po potwierdzeniu sesji na login zachowuje lokalny cel %s', async (next) => {
    fetchCurrentUser.mockResolvedValue(USER)

    expect(
      await authGuard({ ...target('/login', { public: true }), query: { next } }, useAuthStore()),
    ).toBe(next)
  })

  it.each([
    undefined,
    null,
    ['/zakupy/listy/12'],
    'https://example.com/zakupy/listy/12',
    '//example.com/zakupy/listy/12',
    '/\\example.com/zakupy/listy/12',
    '/%5cexample.com/zakupy/listy/12',
    '/%2fexample.com/zakupy/listy/12',
    '/%252fexample.com/zakupy/listy/12',
    '/\n/example.com',
    '/login',
    '/login?next=/zakupy/listy/12',
    '/login/#powrot',
    '/LOGIN/',
    '/zakupy/../login?next=/zakupy/listy/12',
    '/zakupy/%2e%2e/login#powrot',
    '/zakupy/..//example.com',
    '/%6cogin',
  ])('odrzuca niebezpieczny lub zapętlony next %j', async (next) => {
    fetchCurrentUser.mockResolvedValue(USER)

    expect(
      await authGuard({ ...target('/login', { public: true }), query: { next } }, useAuthStore()),
    ).toEqual({ name: 'plan-dnia' })
  })

  it('niezalogowanego wpuszcza na /login', async () => {
    fetchCurrentUser.mockResolvedValue(null)

    expect(await authGuard(target('/login', { public: true }), useAuthStore())).toBe(true)
  })

  it('trasa administracyjna jest zamknięta dla zwykłego użytkownika', async () => {
    fetchCurrentUser.mockResolvedValue(USER)

    const result = await authGuard(target('/admin/uzytkownicy', { admin: true }), useAuthStore())

    expect(result).toEqual({ name: 'plan-dnia' })
  })

  it('administrator wchodzi na trasę administracyjną', async () => {
    fetchCurrentUser.mockResolvedValue({ ...USER, role: 'admin' })

    const result = await authGuard(target('/admin/uzytkownicy', { admin: true }), useAuthStore())

    expect(result).toBe(true)
  })

  it.each([null, USER])(
    'publiczna lista omija odczyt sesji także przy istniejącej sesji',
    async (user) => {
      const auth = useAuthStore()
      auth.user = user
      const ensure = vi.spyOn(auth, 'ensureLoaded')
      expect(await authGuard(target('/l/test', { anonymous: true }), auth)).toBe(true)
      expect(ensure).not.toHaveBeenCalled()
      expect(fetchCurrentUser).not.toHaveBeenCalled()
    },
  )

  it('trasa rodzin jest zamknięta dla zwykłego użytkownika', async () => {
    fetchCurrentUser.mockResolvedValue(USER)

    const result = await authGuard(target('/admin/rodziny', { admin: true }), useAuthStore())

    expect(result).toEqual({ name: 'plan-dnia' })
  })

  it('cold offline z markerem przepuszcza tylko nazwaną prywatną listę, bez uwierzytelnienia', async () => {
    document.cookie = 'csrf_token=test-credential; Path=/'
    await confirmPrivateOfflineSession(USER)
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true)
    fetchCurrentUser.mockRejectedValue(
      new ApiError(0, {
        code: 'network_error',
        message: 'Brak sieci',
        details: {},
      }),
    )
    const auth = useAuthStore()
    expect(await authGuard({ ...target('/zakupy/listy/12'), name: 'zakupy-lista' }, auth)).toBe(
      true,
    )
    expect(auth.isAuthenticated).toBe(false)
    expect(auth.user).toBeNull()
    for (const fullPath of ['/plan-dnia', '/zakupy', '/admin/uzytkownicy']) {
      expect(await authGuard(target(fullPath), auth)).toEqual({
        name: 'login',
        query: { next: fullPath },
      })
    }
  })

  it.each([0, 403, 404, 429, 500])(
    'brak zgodnego markera/status %s nie daje dostępu offline',
    async (status) => {
      fetchCurrentUser.mockRejectedValue(
        new ApiError(status, {
          code: 'test_error',
          message: 'Błąd',
          details: {},
        }),
      )
      const auth = useAuthStore()
      expect(
        await authGuard({ ...target('/zakupy/listy/12'), name: 'zakupy-lista' }, auth),
      ).toEqual({
        name: 'login',
        query: { next: '/zakupy/listy/12' },
      })
      expect(auth.offlineSession).toBe(false)
    },
  )

  it.each([403, 404, 429, 500])(
    'odpowiedź HTTP %s z poprawnym markerem także nie jest trybem offline',
    async (status) => {
      document.cookie = 'csrf_token=test-credential; Path=/'
      await confirmPrivateOfflineSession(USER)
      fetchCurrentUser.mockRejectedValue(
        new ApiError(status, {
          code: 'test_error',
          message: 'Błąd',
          details: {},
        }),
      )
      const auth = useAuthStore()
      expect(
        await authGuard({ ...target('/zakupy/listy/12'), name: 'zakupy-lista' }, auth),
      ).toEqual({
        name: 'login',
        query: { next: '/zakupy/listy/12' },
      })
      expect(auth.offlineSession).toBe(false)
    },
  )
})

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((finish) => {
    resolve = finish
  })
  return { promise, resolve }
}

describe('bootstrap routera z rzeczywistym store, klientem HTTP i generacją sesji', () => {
  let pinia: ReturnType<typeof createPinia>
  const fetchMock = vi.fn<typeof fetch>()
  const staleErrors: unknown[] = []

  beforeEach(async () => {
    vi.stubGlobal('crypto', webcrypto)
    vi.stubGlobal('TextEncoder', TextEncoder)
    vi.stubGlobal('fetch', fetchMock)
    clearPrivateOfflineSession()
    localStorage.clear()
    document.cookie = 'csrf_token=bootstrap-credential; Path=/'
    pinia = createPinia()
    setActivePinia(pinia)
    vi.clearAllMocks()
    fetchMock.mockReset()
    staleErrors.length = 0
    // Pozostałe testy guarda izolują API. Tutaj jedyny stub odpowiedzi jest
    // na granicy fetch: prawdziwe /me przechodzi przez apiFetch i jego ticket.
    const actual = await vi.importActual<{ fetchCurrentUser: typeof RealFetchCurrentUser }>(
      '@/api/auth',
    )
    fetchCurrentUser.mockImplementation(async () => {
      try {
        return await actual.fetchCurrentUser()
      } catch (error) {
        staleErrors.push(error)
        throw error
      }
    })
  })

  afterEach(() => {
    disposePinia(pinia)
    clearPrivateOfflineSession()
    localStorage.clear()
    document.cookie = 'csrf_token=; Max-Age=0; Path=/'
    vi.unstubAllGlobals()
  })

  function memoryRouter() {
    const component = { render: () => null }
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/login', name: 'login', component, meta: { public: true } },
        { path: '/plan-dnia', name: 'plan-dnia', component },
        { path: '/zakupy/listy/:id', name: 'zakupy-lista', component },
        { path: '/admin/uzytkownicy', name: 'admin-users', component, meta: { admin: true } },
      ],
    })
    router.beforeEach((to) => authGuard(to, useAuthStore()))
    return router
  }

  const A: CurrentUser = { ...USER, role: 'admin', household: { id: 4, name: 'Dom A' } }
  const B: CurrentUser = {
    ...USER,
    id: 2,
    email: 'bartek@example.com',
    display_name: 'Bartek',
    household: { id: 9, name: 'Dom B' },
  }

  async function interruptedBootstrap(next: string, current: CurrentUser | number) {
    // To zapis drugiej karty: marker jest prawidłowy, ale nowy store nie ma
    // jeszcze aktywnego zakresu ani potwierdzonego użytkownika.
    await confirmPrivateOfflineSession(A)
    const otherTabMarker = localStorage.getItem('pasnik-private-offline-v1')!
    clearPrivateOfflineSession()
    const firstStarted = deferred<void>()
    const secondStarted = deferred<void>()
    const oldResponse = deferred<Response>()
    const freshResponse = deferred<Response>()
    fetchMock
      .mockImplementationOnce(() => {
        firstStarted.resolve()
        return oldResponse.promise
      })
      .mockImplementationOnce(() => {
        secondStarted.resolve()
        return freshResponse.promise
      })
    const auth = useAuthStore()
    const router = memoryRouter()
    const navigation = router.push(next)
    await firstStarted.promise
    if (typeof current !== 'number' && current.id !== A.id) {
      document.cookie = 'csrf_token=bootstrap-credential-B; Path=/'
    }
    localStorage.setItem('pasnik-private-offline-v1', otherTabMarker)
    window.dispatchEvent(new StorageEvent('storage', { key: 'pasnik-private-offline-v1' }))
    const stale = new Response(JSON.stringify(A), { status: 200 })
    const readStaleBody = vi.spyOn(stale, 'json')
    oldResponse.resolve(stale)
    await secondStarted.promise

    expect(staleErrors).toHaveLength(1)
    expect(staleErrors[0]).toBeInstanceOf(StaleSessionResponseError)
    expect(readStaleBody).not.toHaveBeenCalled()
    expect(auth.user).toBeNull()
    expect(auth.resolved).toBe(false)
    expect(auth.offlineSession).toBe(false)
    expect(localStorage.getItem('pasnik-private-offline-v1')).toBe(otherTabMarker)

    freshResponse.resolve(
      typeof current === 'number'
        ? new Response(
            JSON.stringify({ error: { code: 'denied', message: 'Odmowa', details: {} } }),
            {
              status: current,
            },
          )
        : new Response(JSON.stringify(current), { status: 200 }),
    )
    await navigation
    expect(fetchMock).toHaveBeenCalledTimes(2)
    for (const [url, options] of fetchMock.mock.calls) {
      expect(url).toBe('/api/v1/auth/me')
      expect(options?.credentials).toBe('include')
    }
    return { auth, router }
  }

  it.each([
    ['to samo A', A],
    ['konto B', B],
    ['nowa rodzina A', { ...A, household: { id: 8, name: 'Nowy dom' } }],
    ['odebrana rola ADMIN', { ...A, role: 'user' as const }],
  ])('storage podczas /me zachowuje cel i przyjmuje wyłącznie świeże %s', async (_, current) => {
    const next = '/zakupy/listy/12?sklep=4#pozycja-8'
    const { auth, router } = await interruptedBootstrap(next, current)

    expect(router.currentRoute.value.fullPath).toBe(next)
    expect(auth.user).toEqual(current)
    expect(auth.household).toEqual(current.household)
    expect(auth.isAdmin).toBe(current.role === 'admin')
  })

  it.each([B, { ...A, role: 'user' as const }, A])(
    'powrót next ponownie sprawdza rolę aktualnego konta $id/$role zamiast starego ADMIN-a',
    async (current) => {
      const { auth, router } = await interruptedBootstrap('/admin/uzytkownicy', current)

      expect(auth.user).toEqual(current)
      expect(router.currentRoute.value.name).toBe(
        current.role === 'admin' ? 'admin-users' : 'plan-dnia',
      )
    },
  )

  it.each([401, 403, 404, 429, 500])(
    'świeża odmowa %s nie odtwarza A z markera ani nie otwiera next',
    async (status) => {
      const next = '/zakupy/listy/12'
      const { auth, router } = await interruptedBootstrap(next, status)

      expect(auth.user).toBeNull()
      expect(auth.isAuthenticated).toBe(false)
      expect(auth.offlineSession).toBe(false)
      expect(router.currentRoute.value.name).toBe('login')
      expect(router.currentRoute.value.query.next).toBe(next)
    },
  )
})

describe('mapa tras', () => {
  it('publiczna lista jest osobnym rekordem poza AppShell', () => {
    const record = routes.find((route) => route.name === 'publiczna-lista')!
    expect(record.path).toBe('/l/:token')
    expect(record.meta?.anonymous).toBe(true)
    expect(routes.find((route) => route.path === '/')?.children).not.toContain(record)
  })

  it('odtwarza scroll wstecz, resetuje dla nowej ścieżki i zachowuje przy query', () => {
    const router = createRouter({ history: createMemoryHistory(), routes })
    const from = { ...router.resolve('/przepisy'), name: 'przepisy' }
    const queryOnly = { ...router.resolve('/przepisy?search=owsianka'), name: 'przepisy' }
    const to = { ...router.resolve('/tydzien/2031-03-03'), name: 'tydzien' }
    expect(scrollBehavior(queryOnly, from, null)).toBe(false)
    expect(scrollBehavior(to, from, null)).toEqual({ top: 0, left: 0 })
    expect(scrollBehavior(to, from, { top: 750, left: 0 })).toEqual({ top: 750, left: 0 })
  })
  it('zawiera komplet sekcji z 05_FRONTEND §3', () => {
    const shell = routes.find((route) => route.path === '/')
    const names = (shell?.children ?? []).map((child) => child.name).filter(Boolean)

    // Trasy formularzy (`produkt-*`, `przepis-*`) są podstronami swoich sekcji
    // — nie dokładają pozycji do nawigacji (05_FRONTEND §3).
    expect(names).toEqual([
      'plan-dnia',
      'tydzien',
      'przepisy',
      'przepis-nowy',
      'przepis-szczegol',
      'przepis-edycja',
      'produkty',
      'produkt-nowy',
      'produkt-edycja',
      'spizarnia',
      'zakupy',
      // Trasa-zaślepka listy zakupowej (B10): podstrona sekcji „Zakupy", bez
      // własnej pozycji w nawigacji — pełny widok dostarcza B11.
      'zakupy-lista',
      'statystyki',
      // Tras `import` / `import-review` nie ma od BATCH_20: import jadłospisów
      // PDF został wycofany w całości (D25), a jedynym importem jest kopia
      // danych rodziny — sekcja w Ustawieniach, nie osobna gałąź aplikacji.
      'ustawienia',
      'admin-users',
      'admin-households',
      'admin-verification',
      // Dane instancji (B14): eksport/import logiczny — podsekcja administracji
      // zapowiedziana w 05_FRONTEND §3, nie nowa gałąź aplikacji.
      'admin-transfer',
    ])
  })

  it('nieznana ścieżka wraca do planu dnia', () => {
    const fallback = routes.find((route) => route.path === '/:pathMatch(.*)*')

    expect(fallback?.redirect).toEqual({ name: 'plan-dnia' })
  })
})
