import { webcrypto } from 'node:crypto'
import { TextEncoder } from 'node:util'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  clearPrivateOfflineSession,
  confirmPrivateOfflineSession,
  getPrivateOfflineScope,
  isPrivateOfflineScopeConfirmed,
  isPrivateOfflineScopeCurrent,
  removeLegacyPrivateCaches,
  restorePrivateOfflineSession,
  subscribePrivateOfflineScope,
} from './privateSession'

const KEY = 'pasnik-private-offline-v1'
const USER = { id: 3245, household: { id: 8765, name: 'Rodzina testowa' } }
const unsubscribers: (() => void)[] = []

function cookie(value = 'credential-test-one'): void {
  document.cookie = `csrf_token=${value}; Path=/`
}

describe('lokalny zakres prywatnej listy', () => {
  beforeEach(() => {
    vi.stubGlobal('crypto', webcrypto)
    vi.stubGlobal('TextEncoder', TextEncoder)
    clearPrivateOfflineSession()
    cookie()
  })

  afterEach(() => {
    for (const unsubscribe of unsubscribers.splice(0)) unsubscribe()
    clearPrivateOfflineSession()
    document.cookie = 'csrf_token=; Max-Age=0; Path=/'
    vi.unstubAllGlobals()
  })

  it('utrwala tylko losowy zakres i solone pseudonimy, bez danych konta i cookie', async () => {
    const scope = await confirmPrivateOfflineSession(USER)
    expect(scope).toMatch(/^[0-9a-f-]{36}$/)
    const raw = localStorage.getItem(KEY)!
    expect(Object.keys(JSON.parse(raw)).sort()).toEqual([
      'credentialDigest',
      'principalDigest',
      'salt',
      'scope',
      'version',
    ])
    for (const value of ['"id":3245', '"id":8765', USER.household.name, 'credential-test-one']) {
      expect(raw).not.toContain(value)
    }
    expect(isPrivateOfflineScopeConfirmed(scope!)).toBe(true)
  })

  it('zachowuje zakres/pending po ponownym potwierdzeniu tego samego konta i rodziny', async () => {
    const scope = await confirmPrivateOfflineSession(USER)
    expect(await restorePrivateOfflineSession()).toBe(scope)
    expect(isPrivateOfflineScopeConfirmed(scope!)).toBe(false)
    expect(await confirmPrivateOfflineSession(USER)).toBe(scope)
    expect(isPrivateOfflineScopeConfirmed(scope!)).toBe(true)
  })

  it.each([
    { id: 999, household: USER.household },
    { ...USER, household: { id: 888, name: 'Inna rodzina' } },
    { ...USER, household: null },
  ])('zmiana konta lub rodziny zamyka poprzedni zakres', async (next) => {
    const previous = await confirmPrivateOfflineSession(USER)
    const scope = await confirmPrivateOfflineSession(next)
    expect(scope).not.toBe(previous)
    expect(isPrivateOfflineScopeCurrent(previous!)).toBe(false)
    expect(isPrivateOfflineScopeConfirmed(scope!)).toBe(true)
  })

  it('rotacja cookie zamyka odczyt i nie odtwarza starego markera', async () => {
    const previous = await confirmPrivateOfflineSession(USER)
    cookie('credential-test-two')
    expect(isPrivateOfflineScopeCurrent(previous!)).toBe(false)
    expect(await restorePrivateOfflineSession()).toBeNull()
    expect(localStorage.getItem(KEY)).toBeNull()
    expect(await confirmPrivateOfflineSession(USER)).not.toBe(previous)
  })

  it('brak cookie zamyka lokalny odczyt', async () => {
    await confirmPrivateOfflineSession(USER)
    document.cookie = 'csrf_token=; Max-Age=0; Path=/'
    expect(await restorePrivateOfflineSession()).toBeNull()
    expect(getPrivateOfflineScope()).toBeNull()
  })

  it('clear natychmiast powiadamia cache i nie pozwala spóźnionemu digest odtworzyć zakresu', async () => {
    await confirmPrivateOfflineSession(USER)
    const listener = vi.fn()
    unsubscribers.push(subscribePrivateOfflineScope(listener))
    const pending = confirmPrivateOfflineSession(USER)
    clearPrivateOfflineSession()
    expect(listener).toHaveBeenCalledWith(null, 'session-invalidated')
    expect(getPrivateOfflineScope()).toBeNull()
    expect(await pending).toBeNull()
    expect(localStorage.getItem(KEY)).toBeNull()
  })

  it('storage event usuwa stan starej karty, zachowując marker drugiej karty', async () => {
    await confirmPrivateOfflineSession(USER)
    const listener = vi.fn()
    unsubscribers.push(subscribePrivateOfflineScope(listener))
    const newer = { ...JSON.parse(localStorage.getItem(KEY)!), scope: webcrypto.randomUUID() }
    localStorage.setItem(KEY, JSON.stringify(newer))
    window.dispatchEvent(new StorageEvent('storage', { key: KEY }))
    expect(getPrivateOfflineScope()).toBeNull()
    expect(listener).toHaveBeenCalledWith(null, 'session-invalidated')
    expect(JSON.parse(localStorage.getItem(KEY)!).scope).toBe(newer.scope)
  })

  it('awaria storage/crypto i niepoprawny marker kończą się brakiem dostępu offline', async () => {
    localStorage.setItem(KEY, '{')
    expect(await restorePrivateOfflineSession()).toBeNull()
    localStorage.removeItem(KEY)
    vi.spyOn(Storage.prototype, 'setItem').mockImplementationOnce(() => {
      throw new DOMException('blocked', 'SecurityError')
    })
    expect(await confirmPrivateOfflineSession(USER)).toBeNull()
    vi.stubGlobal('crypto', {})
    expect(await restorePrivateOfflineSession()).toBeNull()
    expect(await confirmPrivateOfflineSession(USER)).toBeNull()
  })

  it('nie przywraca wstrzykniętych dodatkowych pól do markera', async () => {
    await confirmPrivateOfflineSession(USER)
    const stored = JSON.parse(localStorage.getItem(KEY)!)
    localStorage.setItem(KEY, JSON.stringify({ ...stored, user: USER }))
    expect(await restorePrivateOfflineSession()).toBeNull()
  })

  it.each([
    { id: 999, household: USER.household },
    { ...USER, household: { id: 888, name: 'Inna rodzina' } },
  ])(
    'quota podczas potwierdzonej zmiany konta/rodziny nie pozostawia starego grantu',
    async (next) => {
      await confirmPrivateOfflineSession(USER)
      vi.spyOn(Storage.prototype, 'setItem').mockImplementationOnce(() => {
        throw new DOMException('full', 'QuotaExceededError')
      })
      expect(await confirmPrivateOfflineSession(next)).toBeNull()
      expect(localStorage.getItem(KEY)).toBeNull()
      expect(await restorePrivateOfflineSession()).toBeNull()
    },
  )

  it('spóźniona zmiana rodziny nie usuwa markera zapisanego przez drugą kartę', async () => {
    await confirmPrivateOfflineSession(USER)
    const pending = confirmPrivateOfflineSession({ ...USER, household: null })
    const newer = { ...JSON.parse(localStorage.getItem(KEY)!), scope: webcrypto.randomUUID() }
    const raw = JSON.stringify(newer)
    localStorage.setItem(KEY, raw)
    window.dispatchEvent(new StorageEvent('storage', { key: KEY }))
    expect(await pending).toBeNull()
    expect(localStorage.getItem(KEY)).toBe(raw)
  })

  it('usuwa tylko stare globalne cache API/uploadów, zachowując precache shella', async () => {
    const remove = vi.fn().mockResolvedValue(true)
    vi.stubGlobal('caches', { delete: remove })
    await removeLegacyPrivateCaches()
    expect(remove.mock.calls).toEqual([['pasnik-api'], ['pasnik-uploads']])
  })
})
