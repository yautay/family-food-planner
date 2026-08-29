import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { authGuard, routes } from './router'
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

    const result = await authGuard(target('/plan-dnia'), useAuthStore())

    expect(result).toEqual({ name: 'login', query: { next: '/plan-dnia' } })
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

  it('trasa rodzin jest zamknięta dla zwykłego użytkownika', async () => {
    fetchCurrentUser.mockResolvedValue(USER)

    const result = await authGuard(target('/admin/rodziny', { admin: true }), useAuthStore())

    expect(result).toEqual({ name: 'plan-dnia' })
  })
})

describe('mapa tras', () => {
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
      // Import jadłospisów PDF (B15): pierwsza NOWA sekcja od czasu spisania
      // mapy 05_FRONTEND §3 — mapa powstawała przed audytem PDF-ów, więc
      // dokument dostał ten wiersz razem z trasą i pozycją nawigacji.
      'import',
      // Review pojedynczego importu (B16) jest PODSTRONĄ importu — osobna
      // trasa, ale ta sama pozycja nawigacji (05_FRONTEND §3).
      'import-review',
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
