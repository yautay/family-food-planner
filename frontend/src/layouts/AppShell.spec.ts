import { VueQueryPlugin } from '@tanstack/vue-query'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import { routes } from '@/router'
import { useAuthStore } from '@/stores/auth'

import AppShell from './AppShell.vue'

const { fetchCurrentUser, logoutRequest } = vi.hoisted(() => ({
  fetchCurrentUser: vi.fn(),
  logoutRequest: vi.fn(),
}))

vi.mock('@/api/auth', () => ({
  fetchCurrentUser,
  loginRequest: vi.fn(),
  logoutRequest,
}))

const USER = {
  id: 1,
  email: 'anna@example.com',
  display_name: 'Anna',
  role: 'user' as const,
  ui_settings: {},
  household: null,
}

async function mountShell(role: 'user' | 'admin' = 'user') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.user = { ...USER, role }

  const router: Router = createRouter({ history: createMemoryHistory(), routes })
  await router.push('/plan-dnia')
  await router.isReady()

  return mount(AppShell, { global: { plugins: [pinia, VueQueryPlugin, router] } })
}

describe('AppShell', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchCurrentUser.mockResolvedValue(USER)
  })

  it('pokazuje pełną nawigację po polsku', async () => {
    const wrapper = await mountShell()

    for (const name of [
      'plan-dnia',
      'tydzien',
      'przepisy',
      'produkty',
      'spizarnia',
      'zakupy',
      'statystyki',
      'ustawienia',
    ]) {
      expect(wrapper.find(`[data-testid="nav-item-${name}"]`).exists()).toBe(true)
    }
    expect(wrapper.text()).toContain('Plan dnia')
    expect(wrapper.text()).toContain('Spiżarnia')
    // Import jadłospisów PDF wycofany w BATCH_20 (D25) — pozycji menu nie ma,
    // a kopia danych rodziny jest sekcją Ustawień, nie własnym działem.
    expect(wrapper.find('[data-testid="nav-item-import"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Import PDF')
  })

  it('ukrywa wpis Admin przed zwykłym użytkownikiem', async () => {
    const wrapper = await mountShell('user')

    expect(wrapper.find('[data-testid="nav-item-admin-users"]').exists()).toBe(false)
  })

  it('pokazuje wpis Admin administratorowi', async () => {
    const wrapper = await mountShell('admin')

    expect(wrapper.find('[data-testid="nav-item-admin-users"]').exists()).toBe(true)
  })

  it('administracja ma podsekcje pod wspólnym nagłówkiem', async () => {
    const wrapper = await mountShell('admin')

    expect(wrapper.find('[data-testid="nav-group-Administracja"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="nav-item-admin-households"]').exists()).toBe(true)
  })

  it('nagłówek administracji nie pokazuje się zwykłemu użytkownikowi', async () => {
    const wrapper = await mountShell('user')

    expect(wrapper.find('[data-testid="nav-group-Administracja"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="nav-item-admin-households"]').exists()).toBe(false)
  })

  it('bottom-nav ma trzy sekcje główne i przycisk Więcej', async () => {
    const wrapper = await mountShell()

    const bottom = wrapper.get('[data-testid="nav-bottom"]')
    expect(bottom.find('[data-testid="nav-bottom-plan-dnia"]').exists()).toBe(true)
    expect(bottom.find('[data-testid="nav-bottom-przepisy"]').exists()).toBe(true)
    expect(bottom.find('[data-testid="nav-bottom-zakupy"]').exists()).toBe(true)
    expect(bottom.find('[data-testid="nav-more-toggle"]').exists()).toBe(true)
  })

  it('Więcej rozwija pozostałe sekcje', async () => {
    const wrapper = await mountShell()
    expect(wrapper.find('[data-testid="nav-more-panel"]').exists()).toBe(false)

    await wrapper.get('[data-testid="nav-more-toggle"]').trigger('click')

    expect(wrapper.find('[data-testid="nav-more-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="nav-more-item-spizarnia"]').exists()).toBe(true)
  })

  it('wylogowanie woła API i czyści sesję', async () => {
    logoutRequest.mockResolvedValue(undefined)
    const wrapper = await mountShell()

    await wrapper.get('[data-testid="logout-button"]').trigger('click')
    await vi.waitFor(() => expect(logoutRequest).toHaveBeenCalledOnce())

    expect(useAuthStore().isAuthenticated).toBe(false)
  })
})
