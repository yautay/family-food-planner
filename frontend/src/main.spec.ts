import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import type * as Vue from 'vue'

const mocks = vi.hoisted(() => {
  const events: string[] = []
  const router = {
    isReady: vi.fn().mockResolvedValue(undefined),
    currentRoute: { value: { meta: {} } },
  }
  const app = {
    use: vi.fn((plugin: unknown) => {
      if (plugin === router) events.push('router')
    }),
    mount: vi.fn(() => events.push('mount')),
  }
  return {
    app,
    router,
    events,
    gate: vi.fn(),
    purge: vi.fn(),
    clear: vi.fn(),
    start: vi.fn(() => events.push('queue')),
    register: vi.fn(() => events.push('register')),
  }
})

vi.mock('vue', async (original) => ({
  ...(await original<typeof Vue>()),
  createApp: () => mocks.app,
}))
vi.mock('@tanstack/vue-query', () => ({
  VueQueryPlugin: {},
  QueryClient: class {
    clear = mocks.clear
  },
}))
vi.mock('./App.vue', () => ({ default: {} }))
vi.mock('./router', () => ({ router: mocks.router }))
vi.mock('./api/client', () => ({ setUnauthorizedHandler: vi.fn() }))
vi.mock('./stores/auth', () => ({ useAuthStore: () => ({ user: null }) }))
vi.mock('./stores/offlineQueue', () => ({ useOfflineQueueStore: () => ({ start: mocks.start }) }))
vi.mock('./lib/offline/registerSW', () => ({ registerServiceWorker: mocks.register }))
vi.mock('./lib/offline/workerIsolation', () => ({ ensureIsolatedServiceWorker: mocks.gate }))
vi.mock('./lib/offline/privateSession', () => ({
  removeLegacyPrivateCaches: mocks.purge,
}))

beforeEach(() => {
  vi.resetModules()
  vi.clearAllMocks()
  vi.stubEnv('PROD', true)
  mocks.events.length = 0
  mocks.gate.mockResolvedValue(undefined)
  mocks.purge.mockResolvedValue(undefined)
  document.body.innerHTML = '<div id="app"></div>'
})

describe('bezpieczny rozruch PWA', () => {
  it('nie instaluje routera przed safe claim i purge; kolejka startuje po guardzie', async () => {
    let claim!: () => void
    let purged!: () => void
    mocks.gate.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          claim = resolve
        }),
    )
    mocks.purge.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          purged = resolve
        }),
    )
    await import('./main')
    expect(mocks.purge).not.toHaveBeenCalled()
    expect(mocks.events).toEqual([])
    claim()
    await flushPromises()
    expect(mocks.purge).toHaveBeenCalledOnce()
    expect(mocks.events).toEqual([])
    purged()
    await flushPromises()
    expect(mocks.events).toEqual(['router', 'mount', 'queue', 'register'])
    expect(mocks.router.isReady).toHaveBeenCalledOnce()
  })

  it.each(['gate', 'purge'] as const)(
    'awaria %s daje jawny stan bez routera/API i kolejki',
    async (stage) => {
      mocks[stage].mockRejectedValue(new Error('blocked'))
      await import('./main')
      await flushPromises()
      expect(mocks.events).toEqual([])
      expect(document.querySelector('[role="alert"]')?.textContent).toContain('Odśwież stronę')
    },
  )
})
