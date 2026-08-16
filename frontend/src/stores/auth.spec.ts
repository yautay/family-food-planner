import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'

import { useAuthStore } from './auth'

const { fetchCurrentUser, loginRequest, logoutRequest } = vi.hoisted(() => ({
  fetchCurrentUser: vi.fn(),
  loginRequest: vi.fn(),
  logoutRequest: vi.fn(),
}))

vi.mock('@/api/auth', () => ({ fetchCurrentUser, loginRequest, logoutRequest }))

const USER = {
  id: 1,
  email: 'anna@example.com',
  display_name: 'Anna',
  role: 'user' as const,
  ui_settings: {},
  household: null,
}

describe('authStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('startuje bez sesji i bez rozstrzygnięcia', () => {
    const auth = useAuthStore()

    expect(auth.user).toBeNull()
    expect(auth.isAuthenticated).toBe(false)
    expect(auth.resolved).toBe(false)
  })

  it('ensureLoaded pobiera użytkownika z /auth/me', async () => {
    fetchCurrentUser.mockResolvedValue(USER)
    const auth = useAuthStore()

    await auth.ensureLoaded()

    expect(auth.user?.email).toBe('anna@example.com')
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.resolved).toBe(true)
  })

  it('ensureLoaded pyta serwer tylko raz', async () => {
    fetchCurrentUser.mockResolvedValue(USER)
    const auth = useAuthStore()

    await Promise.all([auth.ensureLoaded(), auth.ensureLoaded()])
    await auth.ensureLoaded()

    expect(fetchCurrentUser).toHaveBeenCalledOnce()
  })

  it('brak sesji (401 zmapowane na null) zostawia użytkownika pustego', async () => {
    fetchCurrentUser.mockResolvedValue(null)
    const auth = useAuthStore()

    await auth.ensureLoaded()

    expect(auth.user).toBeNull()
    expect(auth.isAuthenticated).toBe(false)
    expect(auth.resolved).toBe(true)
  })

  it('login zapisuje zalogowanego użytkownika', async () => {
    loginRequest.mockResolvedValue(USER)
    const auth = useAuthStore()

    await auth.login({ email: 'anna@example.com', password: 'haslo-testowe-2026' })

    expect(auth.isAuthenticated).toBe(true)
    expect(loginRequest).toHaveBeenCalledWith({
      email: 'anna@example.com',
      password: 'haslo-testowe-2026',
    })
  })

  it('nieudany login nie ustawia sesji', async () => {
    loginRequest.mockRejectedValue(
      new ApiError(401, {
        code: 'unauthorized',
        message: 'Nieprawidłowy email lub hasło.',
        details: {},
      }),
    )
    const auth = useAuthStore()

    await expect(auth.login({ email: 'anna@example.com', password: 'zle' })).rejects.toBeInstanceOf(
      ApiError,
    )
    expect(auth.isAuthenticated).toBe(false)
  })

  it('rozpoznaje rolę administratora', async () => {
    fetchCurrentUser.mockResolvedValue({ ...USER, role: 'admin' })
    const auth = useAuthStore()

    await auth.ensureLoaded()

    expect(auth.isAdmin).toBe(true)
  })

  it('logout czyści sesję', async () => {
    loginRequest.mockResolvedValue(USER)
    logoutRequest.mockResolvedValue(undefined)
    const auth = useAuthStore()
    await auth.login({ email: 'anna@example.com', password: 'haslo-testowe-2026' })

    await auth.logout()

    expect(auth.user).toBeNull()
    expect(auth.isAuthenticated).toBe(false)
  })

  it('logout czyści sesję nawet gdy żądanie padnie', async () => {
    loginRequest.mockResolvedValue(USER)
    logoutRequest.mockRejectedValue(new Error('brak sieci'))
    const auth = useAuthStore()
    await auth.login({ email: 'anna@example.com', password: 'haslo-testowe-2026' })

    await expect(auth.logout()).rejects.toThrow()

    expect(auth.isAuthenticated).toBe(false)
  })
})
