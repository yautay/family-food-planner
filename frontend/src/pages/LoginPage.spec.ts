import { VueQueryPlugin } from '@tanstack/vue-query'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { ApiError } from '@/api/client'
import { routes } from '@/router'

import LoginPage from './LoginPage.vue'

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

async function mountLogin() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push('/login')
  await router.isReady()

  return mount(LoginPage, { global: { plugins: [pinia, VueQueryPlugin, router] } })
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

    expect(wrapper.text()).toContain('Zaloguj się')
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
})
