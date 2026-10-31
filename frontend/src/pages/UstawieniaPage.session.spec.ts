import { webcrypto } from 'node:crypto'
import { TextEncoder } from 'node:util'

import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '@/App.vue'
import type { CurrentUser } from '@/api/auth'
import { clearPrivateOfflineSession, getPrivateOfflineScope } from '@/lib/offline/privateSession'
import { useAuthStore } from '@/stores/auth'
import { advanceSessionGeneration } from '@/lib/sessionGeneration'

import UstawieniaPage from './UstawieniaPage.vue'
import AdminDanePage from './admin/AdminDanePage.vue'

const api = vi.hoisted(() => ({
  me: vi.fn(),
  login: vi.fn(),
  updateThresholds: vi.fn(),
  download: vi.fn(),
  saveBlob: vi.fn(),
}))
vi.mock('@/api/transfer', () => ({ downloadExport: api.download }))
vi.mock('@/lib/download', () => ({ saveBlob: api.saveBlob }))
vi.mock('@/api/auth', () => ({
  fetchCurrentUser: api.me,
  loginRequest: api.login,
  logoutRequest: vi.fn(),
}))
vi.mock('@/api/goals', () => ({
  DEFAULT_THRESHOLDS: { low: 90, high: 110 },
  fetchGoals: vi.fn().mockResolvedValue({ items: [], current: null }),
  createGoal: vi.fn(),
  deleteGoal: vi.fn(),
  updateThresholds: api.updateThresholds,
}))
vi.mock('@/api/households', () => ({
  fetchMyHousehold: vi.fn().mockResolvedValue({ household: null, members: [] }),
  fetchMyProfiles: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  createProfile: vi.fn(),
  deleteProfile: vi.fn(),
  updateProfile: vi.fn(),
}))
vi.mock('@/components/domain/SklepySection.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/domain/TransferImportDialog.vue', () => ({
  default: { template: '<div />' },
}))

const A: CurrentUser = {
  id: 1,
  email: 'a@example.test',
  display_name: 'A',
  role: 'admin',
  ui_settings: {},
  household: { id: 1, name: 'family-A' },
}
const disposers: (() => void)[] = []

beforeEach(() => {
  vi.stubGlobal('crypto', webcrypto)
  vi.stubGlobal('TextEncoder', TextEncoder)
  clearPrivateOfflineSession()
  document.cookie = 'csrf_token=settings-credential; Path=/'
  vi.clearAllMocks()
})
afterEach(() => {
  for (const dispose of disposers.splice(0).reverse()) dispose()
  clearPrivateOfflineSession()
  document.cookie = 'csrf_token=; Max-Age=0; Path=/'
  vi.unstubAllGlobals()
})

describe('odpowiedź ustawień należy do generacji sesji, w której rozpoczęto PATCH', () => {
  it.each(['account', 'household', 'current'] as const)(
    'callback PATCH zachowuje konto, DOM i zakres bieżącej sesji: %s',
    async (change) => {
      const pinia = createPinia()
      setActivePinia(pinia)
      disposers.push(() => disposePinia(pinia))
      const auth = useAuthStore()
      api.me.mockResolvedValue(A)
      await auth.ensureLoaded()
      let finishPatch!: (value: CurrentUser) => void
      api.updateThresholds.mockReturnValue(
        new Promise<CurrentUser>((resolve) => {
          finishPatch = resolve
        }),
      )
      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
      disposers.push(() => queryClient.clear())
      const view = defineComponent({
        setup() {
          return () =>
            h('div', [
              h(
                'p',
                { 'data-testid': 'identity' },
                `${auth.user?.display_name}:${auth.household?.name}`,
              ),
              h(UstawieniaPage),
            ])
        },
      })
      const router = createRouter({
        history: createMemoryHistory(),
        routes: [
          { path: '/settings', name: 'ustawienia', component: view },
          {
            path: '/login',
            name: 'login',
            meta: { public: true },
            component: { template: '<p>login</p>' },
          },
          { path: '/plan', name: 'plan-dnia', component: view },
        ],
      })
      await router.push('/settings')
      const wrapper = mount(App, {
        global: { plugins: [pinia, [VueQueryPlugin, { queryClient }], router] },
      })
      disposers.push(() => wrapper.unmount())
      await flushPromises()
      await wrapper.get('[data-testid="settings-tab-goals"]').trigger('click')
      await wrapper.get('[data-testid="thresholds-form"]').trigger('submit')
      await flushPromises()
      expect(api.updateThresholds).toHaveBeenCalledOnce()
      if (change === 'current') {
        const scope = getPrivateOfflineScope()
        const updated = { ...A, ui_settings: { nutrition_thresholds: { low: 80, high: 120 } } }
        finishPatch(updated)
        await flushPromises()
        expect(auth.user).toEqual(updated)
        expect(getPrivateOfflineScope()).toBe(scope)
        return
      }
      const B = {
        ...A,
        id: change === 'account' ? 2 : A.id,
        display_name: 'B',
        role: 'user' as const,
        household: { id: 2, name: 'family-B' },
      }
      if (change === 'account') {
        api.login.mockResolvedValue(B)
        await auth.login({ email: B.email, password: 'test-password-2026' })
      } else {
        api.me.mockResolvedValue(B)
        await auth.ensureLoaded(true)
      }
      await flushPromises()
      const scopeB = getPrivateOfflineScope()
      expect(scopeB).not.toBeNull()
      finishPatch(A)
      await flushPromises()
      expect(auth.user).toEqual(B)
      expect(wrapper.get('[data-testid="identity"]').text()).toBe('B:family-B')
      expect(getPrivateOfflineScope()).toBe(scopeB)
    },
  )
})

describe('plik eksportu przed callbackiem zapisu na dysk', () => {
  it.each([
    { label: 'rodzina', page: UstawieniaPage, button: 'transfer-export', stale: true },
    { label: 'instancja', page: AdminDanePage, button: 'admin-transfer-export', stale: true },
    { label: 'rodzina', page: UstawieniaPage, button: 'transfer-export', stale: false },
    { label: 'instancja', page: AdminDanePage, button: 'admin-transfer-export', stale: false },
  ])(
    '$label: zapis pliku wymaga tej samej sesji po resolve transportu (stale=$stale)',
    async ({ page, button, stale }) => {
      const pinia = createPinia()
      setActivePinia(pinia)
      disposers.push(() => disposePinia(pinia))
      let finish!: (file: { blob: Blob; filename: string }) => void
      api.download.mockReturnValue(
        new Promise((resolve) => {
          finish = resolve
        }),
      )
      const wrapper = mount(page, { global: { plugins: [pinia, VueQueryPlugin] } })
      disposers.push(() => wrapper.unmount())
      if (page === UstawieniaPage)
        await wrapper.get('[data-testid="settings-tab-data"]').trigger('click')
      await wrapper.get(`[data-testid="${button}"]`).trigger('click')
      await flushPromises()
      finish({ blob: new Blob(['private-A']), filename: 'private-A.zip' })
      // Promise transportu jest już resolved; options.onSuccess TanStack ruszy
      // dopiero w kolejnej microtask, po zmianie generacji.
      if (stale) advanceSessionGeneration()
      await flushPromises()
      if (stale) {
        expect(api.saveBlob).not.toHaveBeenCalled()
        expect(wrapper.text()).not.toContain('private-A.zip')
      } else {
        expect(api.saveBlob).toHaveBeenCalledOnce()
        expect(wrapper.text()).toContain('private-A.zip')
      }
    },
  )
  it.each([
    { page: UstawieniaPage, button: 'transfer-export', alert: 'transfer-error' },
    { page: AdminDanePage, button: 'admin-transfer-export', alert: 'admin-transfer-error' },
  ])(
    'spóźniony błąd eksportu nie pojawia się w wycofanej stronie: $button',
    async ({ page, button, alert }) => {
      const pinia = createPinia()
      setActivePinia(pinia)
      disposers.push(() => disposePinia(pinia))
      let reject!: (error: Error) => void
      api.download.mockReturnValue(
        new Promise((_resolve, fail) => {
          reject = fail
        }),
      )
      const wrapper = mount(page, { global: { plugins: [pinia, VueQueryPlugin] } })
      disposers.push(() => wrapper.unmount())
      if (page === UstawieniaPage)
        await wrapper.get('[data-testid="settings-tab-data"]').trigger('click')
      await wrapper.get(`[data-testid="${button}"]`).trigger('click')
      await flushPromises()
      advanceSessionGeneration()
      reject(new Error('private-old-session-error'))
      await flushPromises()
      expect(wrapper.find(`[data-testid="${alert}"]`).exists()).toBe(false)
      expect(api.saveBlob).not.toHaveBeenCalled()
    },
  )

  it('spóźniony błąd progów nie pojawia się po zmianie generacji', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    disposers.push(() => disposePinia(pinia))
    let reject!: (error: Error) => void
    api.updateThresholds.mockReturnValue(
      new Promise((_resolve, fail) => {
        reject = fail
      }),
    )
    const wrapper = mount(UstawieniaPage, { global: { plugins: [pinia, VueQueryPlugin] } })
    disposers.push(() => wrapper.unmount())
    await wrapper.get('[data-testid="settings-tab-goals"]').trigger('click')
    await wrapper.get('[data-testid="thresholds-form"]').trigger('submit')
    await flushPromises()
    advanceSessionGeneration()
    reject(new Error('retired thresholds'))
    await flushPromises()
    expect(wrapper.find('[data-testid="thresholds-error"]').exists()).toBe(false)
  })
})
