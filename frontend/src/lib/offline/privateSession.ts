/**
 * Lokalny zakres snapshotów, NIE uwierzytelnienie ani uprawnienie do API.
 * Zachowuje wyłącznie losowy namespace i solone pseudonimy ostatnio
 * potwierdzonego konta/rodziny oraz cookie CSRF. Surowe dane sesji nie są
 * utrwalane. Offline nie da się wykryć odwołania sesji ani zmiany rodziny;
 * przed wysyłką kolejki konieczny jest ponowny, rzeczywisty GET /auth/me.
 */
import type { CurrentUser } from '@/api/auth'
import { readCsrfToken } from '@/api/client'

const STORAGE_KEY = 'pasnik-private-offline-v1'
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
const DIGEST = /^[0-9a-f]{64}$/

interface ScopeRecord {
  version: 1
  scope: string
  salt: string
  principalDigest: string
  credentialDigest: string
}

interface ActiveScope {
  record: ScopeRecord
  /** Tylko w pamięci; nigdy localStorage/IndexedDB/logi. */
  credential: string
  confirmed: boolean
}

let active: ActiveScope | null = null
let generation = 0
export type PrivateOfflineScopeChangeReason = 'session-invalidated' | 'offline-unavailable'
const listeners = new Set<(scope: string | null, reason: PrivateOfflineScopeChangeReason) => void>()

function readRecord(): ScopeRecord | null {
  const raw = localStorage.getItem(STORAGE_KEY)
  if (raw === null) return null
  const value: unknown = JSON.parse(raw)
  if (typeof value !== 'object' || value === null) return null
  const row = value as Record<string, unknown>
  if (
    Object.keys(row).sort().join(',') !== 'credentialDigest,principalDigest,salt,scope,version' ||
    row.version !== 1 ||
    typeof row.scope !== 'string' ||
    !UUID.test(row.scope) ||
    typeof row.salt !== 'string' ||
    !UUID.test(row.salt) ||
    typeof row.principalDigest !== 'string' ||
    !DIGEST.test(row.principalDigest) ||
    typeof row.credentialDigest !== 'string' ||
    !DIGEST.test(row.credentialDigest)
  )
    return null
  return row as unknown as ScopeRecord
}

function publish(
  next: ActiveScope | null,
  reason: PrivateOfflineScopeChangeReason = 'session-invalidated',
  force = false,
): void {
  const previous = active?.record.scope ?? null
  active = next
  const scope = next?.record.scope ?? null
  if (previous !== scope || force) {
    for (const listener of listeners) listener(scope, reason)
  }
}

/** Unieważnia pamięć starej karty, pozostawiając marker zapisany przez nową. */
function invalidateMemory(reason: PrivateOfflineScopeChangeReason = 'session-invalidated'): void {
  generation += 1
  publish(null, reason, true)
}

function recordIsCurrent(record: ScopeRecord): boolean {
  // Caller rozróżnia niedostępny storage od rzeczywistej zmiany rekordu.
  return JSON.stringify(readRecord()) === JSON.stringify(record)
}

async function digest(parts: readonly unknown[]): Promise<string> {
  const data = new TextEncoder().encode(JSON.stringify(parts))
  const result = await crypto.subtle.digest('SHA-256', data)
  return Array.from(new Uint8Array(result), (byte) => byte.toString(16).padStart(2, '0')).join('')
}

/** Wyłącznie po potwierdzonej odpowiedzi /auth/me albo /auth/login. */
export async function confirmPrivateOfflineSession(
  user: Pick<CurrentUser, 'id' | 'household'>,
): Promise<string | null> {
  const ticket = ++generation
  try {
    const credential = readCsrfToken()
    if (!credential) {
      clearScope('offline-unavailable')
      return null
    }
    const previous = readRecord()
    const salt = previous?.salt ?? crypto.randomUUID()
    const [principalDigest, credentialDigest] = await Promise.all([
      digest([salt, 'principal', user.id, user.household?.id ?? null]),
      digest([salt, 'credential', credential]),
    ])
    if (ticket !== generation) return null
    if (
      readCsrfToken() !== credential ||
      (previous ? !recordIsCurrent(previous) : localStorage.getItem(STORAGE_KEY) !== null)
    ) {
      invalidateMemory()
      return null
    }

    const matches =
      previous?.principalDigest === principalDigest &&
      previous.credentialDigest === credentialDigest
    const record: ScopeRecord = matches
      ? previous
      : {
          version: 1,
          scope: crypto.randomUUID(),
          salt,
          principalDigest,
          credentialDigest,
        }
    // Potwierdzony inny principal/rodzina/credential unieważnia stary grant,
    // nawet jeżeli zastąpienie go trafi następnie na quota storage.
    // Nie kasujemy rekordu, który w międzyczasie zapisała druga karta.
    if (!matches && previous) {
      if (!recordIsCurrent(previous)) {
        invalidateMemory()
        return null
      }
      localStorage.removeItem(STORAGE_KEY)
      if (localStorage.getItem(STORAGE_KEY) !== null) {
        invalidateMemory()
        return null
      }
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(record))
    publish({ record, credential, confirmed: true })
    return record.scope
  } catch {
    if (ticket === generation) invalidateMemory('offline-unavailable')
    return null
  }
}

/** Odtwarza tylko zakres lokalnego odczytu, nigdy stan zalogowanego konta. */
export async function restorePrivateOfflineSession(): Promise<string | null> {
  const ticket = ++generation
  try {
    const record = readRecord()
    const credential = readCsrfToken()
    if (!record || !credential) {
      clearPrivateOfflineSession()
      return null
    }
    const credentialDigest = await digest([record.salt, 'credential', credential])
    if (ticket !== generation || readCsrfToken() !== credential || !recordIsCurrent(record)) {
      return null
    }
    if (credentialDigest !== record.credentialDigest) {
      clearPrivateOfflineSession()
      return null
    }
    publish({ record, credential, confirmed: false })
    return record.scope
  } catch {
    if (ticket === generation) invalidateMemory()
    return null
  }
}

/** Natychmiast zamyka lokalny zakres, także przed await wylogowania/logowania. */
export function clearPrivateOfflineSession(): void {
  clearScope('session-invalidated')
}

function clearScope(reason: PrivateOfflineScopeChangeReason): void {
  generation += 1
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Niedostępny storage oznacza brak bezpiecznego offline, nie crash strony.
  }
  publish(null, reason)
}

export function getPrivateOfflineScope(): string | null {
  try {
    if (active && (readCsrfToken() !== active.credential || !recordIsCurrent(active.record))) {
      invalidateMemory()
    }
  } catch {
    invalidateMemory('offline-unavailable')
  }
  return active?.record.scope ?? null
}

export function isPrivateOfflineScopeCurrent(scope: string): boolean {
  return getPrivateOfflineScope() === scope
}

export function isPrivateOfflineScopeConfirmed(scope: string): boolean {
  return isPrivateOfflineScopeCurrent(scope) && active?.confirmed === true
}

function onStorage(event: StorageEvent): void {
  if (event.key !== STORAGE_KEY && event.key !== null) return
  if (active) {
    getPrivateOfflineScope()
  } else {
    // Zmiana konta w drugiej karcie może wyprzedzić pierwszy GET /me tej
    // karty. Unieważnij także taki lot, bez kasowania jej nowego markera.
    generation += 1
    for (const listener of listeners) listener(null, 'session-invalidated')
  }
}

/** Powiadomienie synchroniczne: QueryClient.clear następuje przed nowym renderem. */
export function subscribePrivateOfflineScope(
  listener: (scope: string | null, reason: PrivateOfflineScopeChangeReason) => void,
): () => void {
  if (listeners.size === 0 && typeof window !== 'undefined') {
    window.addEventListener('storage', onStorage)
  }
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
    if (listeners.size === 0 && typeof window !== 'undefined') {
      window.removeEventListener('storage', onStorage)
    }
  }
}

/** Starszy SW przechowywał prywatne odpowiedzi globalnie po URL-u. */
export async function removeLegacyPrivateCaches(): Promise<void> {
  if (typeof caches === 'undefined') return
  await Promise.all(['pasnik-api', 'pasnik-uploads'].map((name) => caches.delete(name)))
}
