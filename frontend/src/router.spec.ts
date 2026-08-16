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
})

describe('mapa tras', () => {
  it('zawiera komplet sekcji z 05_FRONTEND §3', () => {
    const shell = routes.find((route) => route.path === '/')
    const names = (shell?.children ?? []).map((child) => child.name).filter(Boolean)

    expect(names).toEqual([
      'plan-dnia',
      'tydzien',
      'przepisy',
      'produkty',
      'spizarnia',
      'zakupy',
      'statystyki',
      'ustawienia',
      'admin-users',
    ])
  })

  it('nieznana ścieżka wraca do planu dnia', () => {
    const fallback = routes.find((route) => route.path === '/:pathMatch(.*)*')

    expect(fallback?.redirect).toEqual({ name: 'plan-dnia' })
  })
})
