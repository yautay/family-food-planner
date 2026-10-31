import { webcrypto } from 'node:crypto'
import { TextEncoder } from 'node:util'

import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import { captureSessionGeneration, StaleSessionResponseError } from '@/lib/sessionGeneration'
import {
  clearPrivateOfflineSession,
  confirmPrivateOfflineSession,
  getPrivateOfflineScope,
  isPrivateOfflineScopeConfirmed,
} from '@/lib/offline/privateSession'

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
    document.cookie = 'csrf_token=test-credential; Path=/'
    loginRequest.mockResolvedValue(USER)
    const auth = useAuthStore()

    await auth.login({ email: 'anna@example.com', password: 'haslo-testowe-2026' })

    expect(auth.isAuthenticated).toBe(true)
    expect(getPrivateOfflineScope()).not.toBeNull()
    expect(loginRequest).toHaveBeenCalledWith({
      email: 'anna@example.com',
      password: 'haslo-testowe-2026',
    })
  })

  it('login unieważniony podczas rzeczywistego potwierdzania offline odrzuca sukces', async () => {
    document.cookie = 'csrf_token=test-credential; Path=/'
    loginRequest.mockResolvedValue(USER)
    let finishPrincipal!: (value: ArrayBuffer) => void
    let finishCredential!: (value: ArrayBuffer) => void
    const digest = vi
      .spyOn(crypto.subtle, 'digest')
      .mockReturnValueOnce(
        new Promise<ArrayBuffer>((resolve) => {
          finishPrincipal = resolve
        }),
      )
      .mockReturnValueOnce(
        new Promise<ArrayBuffer>((resolve) => {
          finishCredential = resolve
        }),
      )
    try {
      const auth = useAuthStore()
      const pendingLogin = auth.login({ email: USER.email, password: 'haslo-testowe-2026' })
      const rejected = expect(pendingLogin).rejects.toBeInstanceOf(StaleSessionResponseError)
      await vi.waitFor(() => expect(digest).toHaveBeenCalledTimes(2))
      auth.clear()
      finishPrincipal(new ArrayBuffer(32))
      finishCredential(new ArrayBuffer(32))
      await rejected
      expect(auth.isAuthenticated).toBe(false)
      expect(getPrivateOfflineScope()).toBeNull()
    } finally {
      digest.mockRestore()
    }
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

  it('bez rodziny household jest pusty', async () => {
    fetchCurrentUser.mockResolvedValue(USER)
    const auth = useAuthStore()

    await auth.ensureLoaded()

    expect(auth.household).toBeNull()
  })

  it('udostępnia rodzinę z /auth/me', async () => {
    fetchCurrentUser.mockResolvedValue({ ...USER, household: { id: 4, name: 'Kowalscy' } })
    const auth = useAuthStore()

    await auth.ensureLoaded()

    expect(auth.household).toEqual({ id: 4, name: 'Kowalscy' })
  })

  it('wylogowanie czyści także rodzinę', async () => {
    loginRequest.mockResolvedValue({ ...USER, household: { id: 4, name: 'Kowalscy' } })
    logoutRequest.mockResolvedValue(undefined)
    const auth = useAuthStore()
    await auth.login({ email: 'anna@example.com', password: 'haslo-testowe-2026' })

    await auth.logout()

    expect(auth.household).toBeNull()
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

  it('błąd transportu przy optymistycznym onLine odtwarza tylko zakres listy, bez fake auth', async () => {
    document.cookie = 'csrf_token=test-credential; Path=/'
    const scope = await confirmPrivateOfflineSession(USER)
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true)
    fetchCurrentUser.mockRejectedValue(
      new ApiError(0, {
        code: 'network_error',
        message: 'Brak sieci',
        details: {},
      }),
    )
    const auth = useAuthStore()
    await auth.ensureLoaded()
    expect(auth.user).toBeNull()
    expect(auth.isAuthenticated).toBe(false)
    expect(auth.isAdmin).toBe(false)
    expect(auth.resolved).toBe(false)
    expect(auth.offlineSession).toBe(true)
    expect(getPrivateOfflineScope()).toBe(scope)
    expect(isPrivateOfflineScopeConfirmed(scope!)).toBe(false)

    fetchCurrentUser.mockResolvedValue(USER)
    await auth.ensureLoaded(true)
    expect(auth.offlineSession).toBe(false)
    expect(auth.isAuthenticated).toBe(true)
    expect(getPrivateOfflineScope()).toBe(scope)
    expect(isPrivateOfflineScopeConfirmed(scope!)).toBe(true)
  })

  it('potwierdzony brak sesji usuwa marker także po starcie offline', async () => {
    document.cookie = 'csrf_token=test-credential; Path=/'
    await confirmPrivateOfflineSession(USER)
    fetchCurrentUser.mockResolvedValue(null)
    const auth = useAuthStore()
    await auth.ensureLoaded()
    expect(auth.offlineSession).toBe(false)
    expect(getPrivateOfflineScope()).toBeNull()
  })

  it('spóźnione /me po clear nie odtwarza konta ani lokalnego zakresu', async () => {
    let respond!: (value: typeof USER) => void
    fetchCurrentUser.mockReturnValue(
      new Promise<typeof USER>((resolve) => {
        respond = resolve
      }),
    )
    const auth = useAuthStore()
    const pending = auth.ensureLoaded()
    auth.clear()
    respond(USER)
    await pending
    expect(auth.user).toBeNull()
    expect(getPrivateOfflineScope()).toBeNull()
  })

  it('spóźnione login po clear nie odtwarza konta ani lokalnego zakresu', async () => {
    let respond!: (value: typeof USER) => void
    loginRequest.mockReturnValue(
      new Promise<typeof USER>((resolve) => {
        respond = resolve
      }),
    )
    const auth = useAuthStore()
    const pending = auth.login({ email: USER.email, password: 'haslo-testowe-2026' })
    const rejected = expect(pending).rejects.toBeInstanceOf(StaleSessionResponseError)
    auth.clear()
    respond(USER)
    await rejected
    expect(auth.user).toBeNull()
    expect(getPrivateOfflineScope()).toBeNull()
  })

  it('zmiana konta w drugiej karcie unieważnia również pierwszy trwający GET /me', async () => {
    document.cookie = 'csrf_token=test-credential; Path=/'
    await confirmPrivateOfflineSession(USER)
    const otherTabMarker = localStorage.getItem('pasnik-private-offline-v1')!
    clearPrivateOfflineSession()
    let respond!: (value: typeof USER) => void
    fetchCurrentUser.mockReturnValue(
      new Promise<typeof USER>((resolve) => {
        respond = resolve
      }),
    )
    const auth = useAuthStore()
    const pending = auth.ensureLoaded()
    localStorage.setItem('pasnik-private-offline-v1', otherTabMarker)
    window.dispatchEvent(new StorageEvent('storage', { key: 'pasnik-private-offline-v1' }))
    respond(USER)
    await pending
    expect(auth.user).toBeNull()
    expect(localStorage.getItem('pasnik-private-offline-v1')).toBe(otherTabMarker)
  })

  it('logout zamyka zakres przed odpowiedzią serwera', async () => {
    document.cookie = 'csrf_token=test-credential; Path=/'
    fetchCurrentUser.mockResolvedValue(USER)
    const auth = useAuthStore()
    await auth.ensureLoaded()
    let finish!: () => void
    logoutRequest.mockReturnValue(
      new Promise<void>((resolve) => {
        finish = resolve
      }),
    )
    const pending = auth.logout()
    expect(auth.isAuthenticated).toBe(false)
    expect(getPrivateOfflineScope()).toBeNull()
    finish()
    await pending
  })

  it.each(['write', 'read-after-digest'] as const)(
    'udany force /me zachowuje sesję ONLINE po awarii storage %s aktywnego zakresu offline',
    async (failure) => {
      document.cookie = 'csrf_token=test-credential; Path=/'
      fetchCurrentUser.mockResolvedValue(USER)
      const auth = useAuthStore()
      await auth.ensureLoaded()
      expect(getPrivateOfflineScope()).not.toBeNull()
      if (failure === 'write') {
        vi.spyOn(Storage.prototype, 'setItem').mockImplementationOnce(() => {
          throw new DOMException('full', 'QuotaExceededError')
        })
      } else {
        const record = localStorage.getItem('pasnik-private-offline-v1')
        vi.spyOn(Storage.prototype, 'getItem')
          .mockReturnValueOnce(record)
          .mockImplementationOnce(() => {
            throw new DOMException('blocked', 'SecurityError')
          })
      }
      await auth.ensureLoaded(true)
      expect(auth.user).toEqual(USER)
      expect(auth.resolved).toBe(true)
      expect(auth.isAuthenticated).toBe(true)
      expect(auth.offlineSession).toBe(false)
      expect(getPrivateOfflineScope()).toBeNull()
    },
  )

  it('setUser wymaga ticketa z początku operacji i odrzuca brak ticketa', async () => {
    const auth = useAuthStore()
    // @ts-expect-error Każda odpowiedź aktualizująca auth wymaga ticketa.
    expect(auth.setUser(USER)).toBe(false)
    const ticket = captureSessionGeneration()
    auth.clear()
    expect(auth.setUser(USER, ticket)).toBe(false)
    expect(auth.user).toBeNull()
    expect(auth.setUser(USER, captureSessionGeneration())).toBe(true)
  })
})
