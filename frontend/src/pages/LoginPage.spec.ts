import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import LoginPage from './LoginPage.vue'

describe('LoginPage', () => {
  it('renderuje formularz logowania po polsku', () => {
    const wrapper = mount(LoginPage)

    expect(wrapper.text()).toContain('Zaloguj się')
    expect(wrapper.find('[data-testid="login-card"]').exists()).toBe(true)
    expect(wrapper.find('#login-email').exists()).toBe(true)
    expect(wrapper.find('#login-password').exists()).toBe(true)
  })

  it('trzyma przycisk wysyłki wyłączony — logika logowania powstaje w BATCH_02', () => {
    const wrapper = mount(LoginPage)

    expect(wrapper.get('[data-testid="login-submit"]').attributes('disabled')).toBeDefined()
  })
})
