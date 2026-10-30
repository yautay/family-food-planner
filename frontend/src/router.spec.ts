import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
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
