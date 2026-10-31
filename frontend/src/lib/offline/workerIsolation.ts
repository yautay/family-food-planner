/** Nowa nazwa jest granicą migracji ze starego, globalnego cache prywatnego API. */
const ISOLATED_WORKER = '/sw-private-v1.js'
const CLAIM_TIMEOUT_MS = 10_000

/**
 * Istniejący stary controller musi oddać kontrolę PRZED jakimkolwiek GET API.
 * Znany bezpieczny controller działa również cold offline, bez update/fetch.
 * Przy pierwszej wizycie bez controllera nie istnieje ścieżka do starego cache;
 * normalna rejestracja PWA nastąpi po uruchomieniu aplikacji.
 */
export async function ensureIsolatedServiceWorker(): Promise<void> {
  if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return
  const serviceWorker = navigator.serviceWorker
  if (serviceWorker.controller === null) return
  const expected = new URL(ISOLATED_WORKER, window.location.origin).href
  const safe = () => serviceWorker.controller?.scriptURL === expected
  if (safe()) return

  await new Promise<void>((resolve, reject) => {
    let settled = false
    const finish = (error?: Error) => {
      if (settled) return
      settled = true
      clearTimeout(timeout)
      serviceWorker.removeEventListener('controllerchange', check)
      if (error) reject(error)
      else resolve()
    }
    const check = () => {
      if (safe()) finish()
    }
    const timeout = setTimeout(() => {
      finish(new Error('Nie udało się bezpiecznie zaktualizować aplikacji.'))
    }, CLAIM_TIMEOUT_MS)
    serviceWorker.addEventListener('controllerchange', check)
    void serviceWorker
      .register(ISOLATED_WORKER, { scope: '/', updateViaCache: 'none' })
      .then(check)
      .catch(() => finish(new Error('Aktualizacja aplikacji wymaga połączenia z siecią.')))
    check()
  })
}
