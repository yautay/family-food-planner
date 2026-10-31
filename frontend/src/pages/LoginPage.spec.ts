import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import { ApiError } from '@/api/client'
import { routes } from '@/router'
import { advanceSessionGeneration } from '@/lib/sessionGeneration'

import LoginPage from './LoginPage.vue'
import App from '@/App.vue'

const { fetchCurrentUser, loginRequest } = vi.hoisted(() => ({
  fetchCurrentUser: vi.fn(),
  loginRequest: vi.fn(),
}))

vi.mock('@/api/auth', () => ({
  fetchCurrentUser,
  loginRequest,
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

let client: QueryClient
let router: Router
async function mountLogin(path = '/login', withApp = false) {
  const pinia = createPinia()
  setActivePinia(pinia)
  router = createRouter({
    history: createMemoryHistory(),
    routes: withApp
      ? [
          { path: '/login', name: 'login', meta: { public: true }, component: LoginPage },
          { path: '/przepisy', name: 'przepisy', component: { template: '<p>Katalog</p>' } },
        ]
      : routes,
  })
  await router.push(path)
  await router.isReady()

  client = new QueryClient()
  return mount(withApp ? App : LoginPage, {
    global: { plugins: [pinia, [VueQueryPlugin, { queryClient: client }], router] },
  })
}

async function submit(wrapper: Awaited<ReturnType<typeof mountLogin>>): Promise<void> {
  await wrapper.get('form').trigger('submit')
  await vi.waitFor(() => expect(wrapper.vm).toBeTruthy())
  await wrapper.vm.$nextTick()
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchCurrentUser.mockResolvedValue(null)
  })

  it('renderuje formularz logowania po polsku', async () => {
    const wrapper = await mountLogin()

    expect(wrapper.get('h1').text()).toBe('Zaloguj się')
    expect(wrapper.text()).toContain('Paśnik')
    expect(wrapper.find('[data-testid="login-card"]').exists()).toBe(true)
    expect(wrapper.find('#login-email').exists()).toBe(true)
    expect(wrapper.find('#login-password').exists()).toBe(true)
    expect(wrapper.get('[data-testid="login-submit"]').attributes('disabled')).toBeUndefined()
  })

  it('waliduje pusty formularz komunikatami po polsku', async () => {
    const wrapper = await mountLogin()

    await submit(wrapper)
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="login-email-error"]').exists()).toBe(true),
    )

    expect(wrapper.get('[data-testid="login-email-error"]').text()).toBe('Podaj adres e-mail.')
    expect(wrapper.get('[data-testid="login-password-error"]').text()).toBe('Podaj hasło.')
    expect(wrapper.get('#login-email').attributes('aria-describedby')).toBe('login-email-error')
    expect(loginRequest).not.toHaveBeenCalled()
  })

  it('odrzuca niepoprawny adres e-mail', async () => {
    const wrapper = await mountLogin()
    await wrapper.get('#login-email').setValue('to-nie-email')
    await wrapper.get('#login-password').setValue('haslo-testowe-2026')

    await submit(wrapper)
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="login-email-error"]').exists()).toBe(true),
    )

    expect(wrapper.get('[data-testid="login-email-error"]').text()).toContain('poprawny adres')
    expect(loginRequest).not.toHaveBeenCalled()
  })

  it('wysyła poprawne dane do API', async () => {
    loginRequest.mockResolvedValue(USER)
    const wrapper = await mountLogin()
    await wrapper.get('#login-email').setValue('anna@example.com')
    await wrapper.get('#login-password').setValue('haslo-testowe-2026')

    await submit(wrapper)

    await vi.waitFor(() =>
      expect(loginRequest).toHaveBeenCalledWith({
        email: 'anna@example.com',
        password: 'haslo-testowe-2026',
      }),
    )
  })

  it('pokazuje neutralny komunikat przy 401', async () => {
    loginRequest.mockRejectedValue(
      new ApiError(401, {
        code: 'unauthorized',
        message: 'Nieprawidłowy email lub hasło.',
        details: {},
      }),
    )
    const wrapper = await mountLogin()
    await wrapper.get('#login-email').setValue('anna@example.com')
    await wrapper.get('#login-password').setValue('zle-haslo-2026')

    await submit(wrapper)
    await vi.waitFor(() => expect(wrapper.find('[data-testid="login-error"]').exists()).toBe(true))

    expect(wrapper.get('[data-testid="login-error"]').text()).toBe('Nieprawidłowy email lub hasło.')
  })

  it('pokazuje komunikat o zbyt wielu próbach przy 429', async () => {
    loginRequest.mockRejectedValue(
      new ApiError(429, { code: 'rate_limited', message: 'Zbyt wiele żądań.', details: {} }),
    )
    const wrapper = await mountLogin()
    await wrapper.get('#login-email').setValue('anna@example.com')
    await wrapper.get('#login-password').setValue('haslo-testowe-2026')

    await submit(wrapper)
    await vi.waitFor(() => expect(wrapper.find('[data-testid="login-error"]').exists()).toBe(true))

    expect(wrapper.get('[data-testid="login-error"]').text()).toContain('Zbyt wiele prób')
  })

  it.each(['session', 'unmount'] as const)(
    'login po %s podczas invalidacji nie przejmuje nawigacji',
    async (change) => {
      loginRequest.mockResolvedValue(USER)
      const wrapper = await mountLogin('/login?next=/przepisy?q=zupa')
      let finish!: () => void
      const invalidate = vi.spyOn(client, 'invalidateQueries').mockReturnValueOnce(
        new Promise<void>((resolve) => {
          finish = resolve
        }),
      )
      const push = vi.spyOn(router, 'push')
      try {
        await wrapper.get('#login-email').setValue(USER.email)
        await wrapper.get('#login-password').setValue('haslo-testowe-2026')
        await submit(wrapper)
        await vi.waitFor(() => expect(invalidate).toHaveBeenCalledOnce())
        if (change === 'session') advanceSessionGeneration()
        else wrapper.unmount()
        finish()
        await flushPromises()
        expect(push).not.toHaveBeenCalled()
      } finally {
        wrapper.unmount()
        push.mockRestore()
      }
    },
  )

  it('poprawny login po własnej zmianie generacji nadal zachowuje lokalne next', async () => {
    loginRequest.mockResolvedValue(USER)
    const wrapper = await mountLogin('/login?next=/przepisy?q=zupa', true)
    try {
      await wrapper.get('#login-email').setValue(USER.email)
      await wrapper.get('#login-password').setValue('haslo-testowe-2026')
      await submit(wrapper)
      await vi.waitFor(() => expect(router.currentRoute.value.fullPath).toBe('/przepisy?q=zupa'))
    } finally {
      wrapper.unmount()
    }
  })
})
