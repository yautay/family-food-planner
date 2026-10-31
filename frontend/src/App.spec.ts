import { webcrypto } from 'node:crypto'
import { TextEncoder } from 'node:util'

import {
  QueryClient,
  VueQueryPlugin,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { defineComponent, h, nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { CurrentUser } from '@/api/auth'
import { ApiError } from '@/api/client'
import { clearPrivateOfflineSession } from '@/lib/offline/privateSession'
import { useAuthStore } from '@/stores/auth'

import App from './App.vue'

const { fetchCurrentUser, loginRequest } = vi.hoisted(() => ({
  fetchCurrentUser: vi.fn(),
  loginRequest: vi.fn(),
}))
vi.mock('@/api/auth', () => ({ fetchCurrentUser, loginRequest, logoutRequest: vi.fn() }))

const USER: CurrentUser = {
  id: 1,
  email: 'a@example.test',
  display_name: 'A',
  role: 'user',
  ui_settings: {},
  household: null,
}
const KEY = ['private-data']
const resources: (() => void)[] = []

beforeEach(() => {
  vi.stubGlobal('crypto', webcrypto)
  vi.stubGlobal('TextEncoder', TextEncoder)
  clearPrivateOfflineSession()
  document.cookie = 'csrf_token=app-test-credential; Path=/'
  vi.clearAllMocks()
})
afterEach(() => {
  for (const dispose of resources.splice(0).reverse()) dispose()
  clearPrivateOfflineSession()
  document.cookie = 'csrf_token=; Max-Age=0; Path=/'
  vi.unstubAllGlobals()
})

async function setup(path: string, user = USER) {
  const pinia = createPinia()
  setActivePinia(pinia)
  resources.push(() => disposePinia(pinia))
  const auth = useAuthStore()
  fetchCurrentUser.mockResolvedValue(user)
  await auth.ensureLoaded()
  let respondA!: (value: string) => void
  const pendingA = new Promise<string>((resolve) => {
    respondA = resolve
  })
  const observers: ReturnType<typeof useQuery<string>>[] = []
  const clients: QueryClient[] = []
  let failMutation!: (error: Error) => void
  const mutationResponse = new Promise<void>((_resolve, reject) => {
    failMutation = reject
  })
  const mutations: { mutate: () => void }[] = []
  let initialRead = true
  const view = defineComponent({
    setup() {
      const client = useQueryClient()
      clients.push(client)
      const query = useQuery<string>({
        queryKey: KEY,
        queryFn: () => {
          if (auth.user?.id !== 1) return Promise.resolve('private-B')
          if (initialRead) {
            initialRead = false
            return Promise.resolve('private-A')
          }
          return pendingA
        },
        staleTime: Infinity,
      })
      observers.push(query)
      const mutation = useMutation({
        mutationFn: () => mutationResponse,
        onMutate: () => client.getQueryData<string>(KEY),
        onError: (_error, _variables, previous) => {
          client.setQueryData(KEY, previous)
        },
      })
      mutations.push({ mutate: () => mutation.mutate(undefined) })
      return () => h('p', { 'data-testid': 'private-data' }, query.data.value ?? 'loading')
    },
  })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/plan', name: 'plan-dnia', component: view },
      { path: '/recipe', name: 'przepis-szczegol', component: view },
      { path: '/admin', name: 'admin-users', meta: { admin: true }, component: view },
      { path: '/list', name: 'zakupy-lista', component: { template: '<p>offline-list</p>' } },
      {
        path: '/l/token',
        name: 'publiczna-lista',
        meta: { anonymous: true },
        component: { template: '<p>public</p>' },
      },
      {
        path: '/login',
        name: 'login',
        meta: { public: true },
        component: { template: '<p>login</p>' },
      },
    ],
  })
  await router.push(path)
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  resources.push(() => queryClient.clear())
  const wrapper = mount(App, {
    global: { plugins: [pinia, [VueQueryPlugin, { queryClient }], router] },
  })
  resources.push(() => wrapper.unmount())
  await flushPromises()
  return {
    auth,
    wrapper,
    router,
    queryClient,
    observers,
    respondA,
    clients,
    mutations,
    failMutation,
  }
}

describe('zamykanie chronionych widoków przy zmianie sesji', () => {
  it.each(['/plan', '/recipe', '/admin'])(
    '%s odmontowuje aktywny observer A po storage-event i nie renderuje late A po login B',
    async (path) => {
      const { auth, wrapper, queryClient, observers, respondA, clients } = await setup(path, {
        ...USER,
        role: 'admin',
      })
      expect(wrapper.text()).toContain('private-A')
      const previous = observers[0]!
      const pending = previous.refetch()
      const record = JSON.parse(localStorage.getItem('pasnik-private-offline-v1')!)
      localStorage.setItem(
        'pasnik-private-offline-v1',
        JSON.stringify({ ...record, scope: webcrypto.randomUUID() }),
      )
      window.dispatchEvent(new StorageEvent('storage', { key: 'pasnik-private-offline-v1' }))
      queryClient.clear()
      await nextTick()
      // Real QueryObserver zachowuje A po clear; DOM musi być odmontowany.
      expect(previous.data.value).toBe('private-A')
      expect(wrapper.find('[data-testid="private-data"]').exists()).toBe(false)

      loginRequest.mockResolvedValue({ ...USER, id: 2, role: 'admin' })
      await auth.login({ email: 'b@example.test', password: 'test-password-2026' })
      await flushPromises()
      expect(wrapper.text()).toContain('private-B')
      respondA('late-private-A')
      await pending
      await flushPromises()
      expect(wrapper.text()).not.toContain('private-A')
      expect(wrapper.text()).toContain('private-B')
      expect(clients.at(-1)!.getQueryData(KEY)).toBe('private-B')
    },
  )

  it('potwierdzona utrata roli admin odmontowuje aktywny widok administracji', async () => {
    const { auth, wrapper, observers } = await setup('/admin', { ...USER, role: 'admin' })
    expect(wrapper.text()).toContain('private-A')
    fetchCurrentUser.mockResolvedValue(USER)
    await auth.ensureLoaded(true)
    await nextTick()
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.isAdmin).toBe(false)
    expect(observers[0]!.data.value).toBe('private-A')
    expect(wrapper.find('[data-testid="private-data"]').exists()).toBe(false)
  })

  it('publiczny widok nie wymaga zalogowanego konta ani odczytu /me', async () => {
    const { auth, wrapper, router } = await setup('/l/token')
    auth.clear()
    fetchCurrentUser.mockClear()
    await nextTick()
    expect(wrapper.text()).toBe('public')
    await router.push('/login')
    expect(wrapper.text()).toBe('login')
    expect(fetchCurrentUser).not.toHaveBeenCalled()
  })

  it('lokalny grant po błędzie transportu otwiera tylko listę, bez uwierzytelnienia innych widoków', async () => {
    const { auth, wrapper, router } = await setup('/list')
    fetchCurrentUser.mockRejectedValue(
      new ApiError(0, { code: 'network_error', message: 'offline', details: {} }),
    )
    await auth.ensureLoaded(true)
    await nextTick()
    expect(auth.user).toBeNull()
    expect(auth.offlineSession).toBe(true)
    expect(wrapper.text()).toBe('offline-list')
    await router.push('/recipe')
    expect(wrapper.find('[data-testid="private-data"]').exists()).toBe(false)
  })

  it('late onError rollback starej realnej mutacji A nie wpisuje danych do klienta B', async () => {
    const { auth, wrapper, clients, mutations, failMutation } = await setup('/plan')
    const retiredClient = clients[0]!
    mutations[0]!.mutate()
    await flushPromises()
    loginRequest.mockResolvedValue({ ...USER, id: 2 })
    await auth.login({ email: 'b@example.test', password: 'test-password-2026' })
    await flushPromises()
    const currentClient = clients.at(-1)!
    expect(wrapper.text()).toContain('private-B')
    failMutation(new Error('late error A'))
    await flushPromises()
    expect(retiredClient.getQueryData(KEY)).toBe('private-A')
    expect(currentClient.getQueryData(KEY)).toBe('private-B')
    expect(wrapper.text()).toContain('private-B')
    expect(currentClient).not.toBe(retiredClient)
  })
})
