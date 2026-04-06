import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import AppHeader from '../../../src/components/layout/AppHeader.vue'
import { useAuthStore } from '../../../src/stores/authStore'
import { useUiStore } from '../../../src/stores/uiStore'

function createTestRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/meals', component: { template: '<div />' } },
      { path: '/settings', component: { template: '<div />' } },
      { path: '/catalog', component: { template: '<div />' } },
      { path: '/ingredients', component: { template: '<div />' } },
      { path: '/units', component: { template: '<div />' } },
      { path: '/packages', component: { template: '<div />' } },
      { path: '/tags', component: { template: '<div />' } },
      { path: '/recipes', component: { template: '<div />' } },
      { path: '/account', component: { template: '<div />' } },
      { path: '/access-control', component: { template: '<div />' } },
      { path: '/login', component: { template: '<div />' } },
      { path: '/register', component: { template: '<div />' } },
    ],
  })
}

describe('AppHeader', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    window.matchMedia = () => ({
      matches: false,
      media: '',
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })
  })

  it('opens navigation and user menus from icons', async () => {
    const router = createTestRouter()
    await router.push('/')
    await router.isReady()

    const authStore = useAuthStore()
    authStore.$patch({
      token: 'session-token',
      user: {
        username: 'tester',
        email: 'tester@example.test',
      },
      permissions: ['permissions.manage'],
    })

    const uiStore = useUiStore()
    uiStore.setLocale('pl')

    const wrapper = mount(AppHeader, {
      global: {
        plugins: [router],
      },
    })

    const navButton = wrapper.find('button[aria-label="Przelacz nawigacje"]')
    await navButton.trigger('click')

    expect(wrapper.text()).toContain('Planowanie')
    expect(wrapper.text()).toContain('Ustawienia')

    const userButton = wrapper.find('button[aria-label="Przelacz menu uzytkownika"]')
    await userButton.trigger('click')

    expect(wrapper.text()).toContain('Konto')
    expect(wrapper.text()).toContain('Kontrola dostepu')
  })
})
