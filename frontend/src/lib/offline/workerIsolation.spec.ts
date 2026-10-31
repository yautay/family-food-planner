import { afterEach, describe, expect, it, vi } from 'vitest'

import { ensureIsolatedServiceWorker } from './workerIsolation'

function workerContainer(scriptURL: string | null) {
  const events = new EventTarget()
  const container = {
    controller: scriptURL === null ? null : { scriptURL },
    register: vi.fn().mockResolvedValue({}),
    addEventListener: events.addEventListener.bind(events),
    removeEventListener: events.removeEventListener.bind(events),
  }
  vi.stubGlobal('navigator', { serviceWorker: container })
  return { container, events }
}

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('migracja izolacji service workera', () => {
  it('znany bezpieczny controller działa offline bez rejestracji ani update', async () => {
    const { container } = workerContainer(new URL('/sw-private-v1.js', location.origin).href)
    await ensureIsolatedServiceWorker()
    expect(container.register).not.toHaveBeenCalled()
  })

  it('pierwsza wizyta i brak obsługi SW nie blokują zwykłej aplikacji', async () => {
    const { container } = workerContainer(null)
    await ensureIsolatedServiceWorker()
    expect(container.register).not.toHaveBeenCalled()
    vi.stubGlobal('navigator', {})
    await ensureIsolatedServiceWorker()
  })

  it('stary controller blokuje kontynuację aż nowy worker przejmie kontrolę', async () => {
    const { container, events } = workerContainer(new URL('/sw.js', location.origin).href)
    const continuation = vi.fn()
    const pending = ensureIsolatedServiceWorker().then(continuation)
    await Promise.resolve()
    expect(container.register).toHaveBeenCalledWith('/sw-private-v1.js', {
      scope: '/',
      updateViaCache: 'none',
    })
    expect(continuation).not.toHaveBeenCalled()
    events.dispatchEvent(new Event('controllerchange'))
    expect(continuation).not.toHaveBeenCalled()
    container.controller = { scriptURL: new URL('/sw-private-v1.js', location.origin).href }
    events.dispatchEvent(new Event('controllerchange'))
    await pending
    expect(continuation).toHaveBeenCalledOnce()
  })

  it('inna domena albo scope w URL workera nie udają bezpiecznego controllera', async () => {
    const { container, events } = workerContainer('https://other.invalid/sw-private-v1.js')
    const continuation = vi.fn()
    const pending = ensureIsolatedServiceWorker().then(continuation)
    container.controller = { scriptURL: new URL('/nested/sw-private-v1.js', location.origin).href }
    events.dispatchEvent(new Event('controllerchange'))
    await Promise.resolve()
    expect(continuation).not.toHaveBeenCalled()
    container.controller = { scriptURL: new URL('/sw-private-v1.js', location.origin).href }
    events.dispatchEvent(new Event('controllerchange'))
    await pending
  })

  it('offline starego workera kończy się kontrolowaną odmową, bez kontynuacji', async () => {
    const { container } = workerContainer(new URL('/sw.js', location.origin).href)
    container.register.mockRejectedValue(new TypeError('offline'))
    await expect(ensureIsolatedServiceWorker()).rejects.toThrow('wymaga połączenia')
  })

  it('brak claim nie odblokowuje prywatnego API po timeout', async () => {
    vi.useFakeTimers()
    workerContainer(new URL('/sw.js', location.origin).href)
    const assertion = expect(ensureIsolatedServiceWorker()).rejects.toThrow('bezpiecznie')
    await vi.advanceTimersByTimeAsync(10_000)
    await assertion
  })
})
