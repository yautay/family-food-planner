import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { routes } from '@/router'
import { useAuthStore } from '@/stores/auth'
import { captureSessionGeneration, StaleSessionResponseError } from '@/lib/sessionGeneration'
import AppShell from './AppShell.vue'
import App from '@/App.vue'

const { logoutRequest } = vi.hoisted(() => ({ logoutRequest: vi.fn() }))
vi.mock('@/api/auth', () => ({ fetchCurrentUser: vi.fn(), loginRequest: vi.fn(), logoutRequest }))
const USER = {
  id: 1,
  email: 'anna@example.com',
  display_name: 'Anna',
  role: 'user' as const,
  ui_settings: {},
  household: null,
}
const wrappers: ReturnType<typeof mount>[] = []
async function mountShell(
  path = '/plan-dnia/2031-03-05',
  role: 'user' | 'admin' = 'user',
  withBoundary = false,
) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().user = { ...USER, role }
  const children = routes
    .find((record) => record.path === '/')!
    .children!.filter((record) => record.name)
    .map((record) => ({
      name: record.name,
      meta: record.meta,
      path: `/${record.path}`,
      component: { template: '<div><input data-testid="view-filter" /><h1>Treść</h1></div>' },
    }))
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      ...(withBoundary
        ? [
            {
              path: '/',
              component: AppShell,
              children: children.map((child) => ({ ...child, path: child.path.slice(1) })),
            },
          ]
        : children),
      {
        path: '/login',
        name: 'login',
        meta: { public: true },
        component: { template: '<div>Logowanie</div>' },
      },
    ],
  })
  await router.push(path)
  await router.isReady()
  const queryClient = new QueryClient()
  const wrapper = mount(withBoundary ? App : AppShell, {
    attachTo: document.body,
    global: { plugins: [pinia, [VueQueryPlugin, { queryClient }], router] },
  })
  wrappers.push(wrapper)
  return { wrapper, router, queryClient }
}
describe('AppShell UX02', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })
  afterEach(() => {
    wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
    document.body.innerHTML = ''
  })

  it('pokazuje te same cztery sekcje w tej samej kolejności na obu urządzeniach', async () => {
    const { wrapper } = await mountShell()
    const desktop = wrapper.get('[data-testid="nav-sidebar"] nav').findAll('a')
    const mobile = wrapper.get('[data-testid="nav-bottom"]').findAll('a')
    expect(desktop.map((a) => a.text())).toEqual(['Plan', 'Przepisy', 'Zakupy', 'Spiżarnia'])
    expect(mobile.map((a) => a.text())).toEqual(desktop.map((a) => a.text()))
    expect(wrapper.find('[data-testid="nav-more-toggle"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="nav-item-produkty"]').text()).toBe('Biblioteka produktów')
    expect(wrapper.get('[data-testid="account-toggle-mobile"]').attributes('aria-label')).toBe(
      'Konto i ustawienia',
    )
  })
  it.each([
    '/tydzien/2031-03-03',
    '/statystyki',
    '/przepisy/17',
    '/przepisy/17/edytuj',
    '/przepisy/nowy',
    '/zakupy/listy/7',
  ])('aktywuje sekcję także dla %s', async (path) => {
    const { wrapper } = await mountShell(path)
    const active = wrapper.get('[data-testid="nav-bottom"] [aria-current="page"]')
    expect(active.text()).toBe(
      path.startsWith('/przepisy') ? 'Przepisy' : path.startsWith('/zakupy') ? 'Zakupy' : 'Plan',
    )
  })
  it('zakładki zachowują środę i przekazują zakres zakupom', async () => {
    const { wrapper, router } = await mountShell()
    await wrapper.get('[data-testid="plan-view-tydzien"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/tydzien/2031-03-03')
    expect(router.currentRoute.value.query.selectedDate).toBe('2031-03-05')
    await wrapper.get('[data-testid="plan-view-plan-dnia"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/plan-dnia/2031-03-05')
    const shopping = router.resolve(
      wrapper.get('[data-testid="plan-shopping-link"]').attributes('href')!,
    )
    expect(shopping.query).toEqual({
      selectedDate: '2031-03-05',
      from: '2031-03-03',
      to: '2031-03-09',
    })
  })
  it('przechowuje kontekst podczas wizyty w przepisach', async () => {
    const { wrapper, router } = await mountShell()
    await router.push('/przepisy')
    await flushPromises()
    expect(wrapper.get('[data-testid="nav-item-plan-dnia"]').attributes('href')).toContain(
      '/plan-dnia/2031-03-05',
    )
  })
  it('przenosi fokus do treści po zmianie ścieżki, ale nie przy filtrach query', async () => {
    const { wrapper, router } = await mountShell()
    const input = wrapper.get<HTMLInputElement>('[data-testid="view-filter"]').element
    input.focus()
    await router.replace({ query: { filter: 'owsianka' } })
    await flushPromises()
    expect(document.activeElement).toBe(input)
    await router.push('/przepisy')
    await flushPromises()
    expect(document.activeElement).toBe(wrapper.get('main').element)
    expect(wrapper.get('[data-testid="skip-link"]').attributes('href')).toBe('#main-content')
  })
  it('konto na telefonie udostępnia ustawienia i bibliotekę bez administracji USER-owi', async () => {
    const { wrapper } = await mountShell()
    await wrapper.get('[data-testid="account-toggle-mobile"]').trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(
      document.querySelector('[data-testid="account-item-ustawienia-mobile"]')?.textContent,
    ).toContain('Dom i ustawienia')
    expect(document.querySelector('[data-testid="account-item-produkty-mobile"]')).not.toBeNull()
    expect(document.querySelector('[data-testid="account-item-admin-users-mobile"]')).toBeNull()
    expect(
      document
        .querySelector('[data-testid="account-menu-mobile"]')
        ?.classList.contains('print:hidden'),
    ).toBe(true)
    document
      .querySelector('[data-testid="account-menu-mobile"]')!
      .dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    // Reka przywraca fokus przez setTimeout(0); flushPromises nie czeka na ten timer.
    await vi.waitFor(() => {
      expect(document.querySelector('[data-testid="account-menu-mobile"]')).toBeNull()
      expect(document.activeElement).toBe(
        wrapper.get('[data-testid="account-toggle-mobile"]').element,
      )
    })
  })
  it('ADMIN ma osobną grupę i wszystkie cztery ekrany administracji', async () => {
    const { wrapper } = await mountShell('/plan-dnia', 'admin')
    await wrapper.get('[data-testid="account-toggle"]').trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(document.querySelector('[data-testid="nav-group-Administracja"]')).not.toBeNull()
    expect(
      document.querySelector('[data-testid="account-menu"]')?.classList.contains('print:hidden'),
    ).toBe(true)
    for (const name of ['users', 'households', 'verification', 'transfer'])
      expect(document.querySelector(`[data-testid="account-item-admin-${name}"]`)).not.toBeNull()
  })
  it('wybranie ustawień w menu konta zamyka menu i oddaje fokus nowej treści', async () => {
    const { wrapper, router } = await mountShell()
    await wrapper.get('[data-testid="account-toggle-mobile"]').trigger('keydown', { key: 'Enter' })
    await flushPromises()
    ;(
      document.querySelector('[data-testid="account-item-ustawienia-mobile"]') as HTMLAnchorElement
    ).click()
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('ustawienia')
    expect(document.querySelector('[data-testid="account-menu-mobile"]')).toBeNull()
    expect(document.activeElement).toBe(wrapper.get('main').element)
  })
  it('wylogowanie w menu konta usuwa sesję i cache', async () => {
    logoutRequest.mockResolvedValue(undefined)
    const { wrapper, queryClient, router } = await mountShell()
    queryClient.setQueryData(['prywatne'], { content: 'plan' })
    await wrapper.get('[data-testid="account-toggle"]').trigger('keydown', { key: 'Enter' })
    await flushPromises()
    ;(document.querySelector('[data-testid="logout-button"]') as HTMLButtonElement).click()
    await flushPromises()
    expect(logoutRequest).toHaveBeenCalledOnce()
    expect(useAuthStore().isAuthenticated).toBe(false)
    expect(queryClient.getQueryData(['prywatne'])).toBeUndefined()
    expect(router.currentRoute.value.name).toBe('login')
  })

  it.each(['success', 'stale-error', 'network-error'] as const)(
    'stare wylogowanie (%s) nie usuwa cache i trasy nowego konta',
    async (outcome) => {
      let finish!: () => void
      let fail!: (error: Error) => void
      logoutRequest.mockReturnValueOnce(
        new Promise<void>((resolve, reject) => {
          finish = resolve
          fail = reject
        }),
      )
      const { wrapper, queryClient, router } = await mountShell()
      await wrapper.get('[data-testid="account-toggle"]').trigger('keydown', { key: 'Enter' })
      await flushPromises()
      ;(document.querySelector('[data-testid="logout-button"]') as HTMLButtonElement).click()
      await flushPromises()
      expect(logoutRequest).toHaveBeenCalledOnce()
      useAuthStore().setUser({ ...USER, id: 2 }, captureSessionGeneration())
      queryClient.setQueryData(['nowa-sesja'], 'plan B')
      if (outcome === 'success') finish()
      else fail(outcome === 'stale-error' ? new StaleSessionResponseError() : new Error('offline'))
      await flushPromises()
      expect(useAuthStore().user?.id).toBe(2)
      expect(queryClient.getQueryData(['nowa-sesja'])).toBe('plan B')
      expect(router.currentRoute.value.name).toBe('plan-dnia')
    },
  )

  it('błąd sieci wylogowania w tej samej sesji nadal czyści cache i otwiera login', async () => {
    logoutRequest.mockRejectedValueOnce(new Error('offline'))
    const { wrapper, queryClient, router } = await mountShell()
    queryClient.setQueryData(['prywatne'], 'plan A')
    await wrapper.get('[data-testid="account-toggle"]').trigger('keydown', { key: 'Enter' })
    await flushPromises()
    ;(document.querySelector('[data-testid="logout-button"]') as HTMLButtonElement).click()
    await flushPromises()
    expect(useAuthStore().isAuthenticated).toBe(false)
    expect(queryClient.getQueryData(['prywatne'])).toBeUndefined()
    expect(router.currentRoute.value.name).toBe('login')
  })

  it.each(['success', 'network-error'] as const)(
    'własne odmontowanie granicy sesji po logout (%s) nadal otwiera login',
    async (outcome) => {
      let finish!: () => void
      let fail!: (error: Error) => void
      logoutRequest.mockReturnValueOnce(
        new Promise<void>((resolve, reject) => {
          finish = resolve
          fail = reject
        }),
      )
      const { wrapper, router } = await mountShell('/plan-dnia/2031-03-05', 'user', true)
      await wrapper.get('[data-testid="account-toggle"]').trigger('keydown', { key: 'Enter' })
      await flushPromises()
      ;(document.querySelector('[data-testid="logout-button"]') as HTMLButtonElement).click()
      await flushPromises()
      expect(wrapper.find('[data-testid="app-shell"]').exists()).toBe(false)
      if (outcome === 'success') finish()
      else fail(new Error('offline'))
      await flushPromises()
      expect(router.currentRoute.value.name).toBe('login')
    },
  )

  it('wylogowanie nie nadpisuje trasy wybranej po zamknięciu starego widoku', async () => {
    let finish!: () => void
    logoutRequest.mockReturnValueOnce(
      new Promise<void>((resolve) => {
        finish = resolve
      }),
    )
    const { wrapper, router } = await mountShell('/plan-dnia/2031-03-05', 'user', true)
    await wrapper.get('[data-testid="account-toggle"]').trigger('keydown', { key: 'Enter' })
    await flushPromises()
    ;(document.querySelector('[data-testid="logout-button"]') as HTMLButtonElement).click()
    await flushPromises()
    await router.push('/login?next=/przepisy')
    finish()
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/login?next=/przepisy')
  })
})
