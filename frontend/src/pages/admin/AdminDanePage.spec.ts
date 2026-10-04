import { VueQueryPlugin } from '@tanstack/vue-query'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AdminDanePage from './AdminDanePage.vue'

/**
 * Podpowiedź w zakładce „Instancja” (D33): wyjaśnia, że tylko kopia instancji może nadać
 * przepisom zakres „Wszyscy”. Rozwijana przyciskiem (≥44 px), bo na telefonie nie ma hovera.
 */
function mountPage() {
  return mount(AdminDanePage, {
    global: { plugins: [VueQueryPlugin] },
    attachTo: document.body,
  })
}

describe('AdminDanePage — podpowiedź o kopii instancji', () => {
  it('domyślnie zwinięta, a przycisk ma aria-expanded=false i cel dotykowy ≥44 px', () => {
    const wrapper = mountPage()

    const toggle = wrapper.get('[data-testid="admin-dane-help-toggle"]')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(toggle.classes()).toContain('min-h-11')
    expect(wrapper.find('[data-testid="admin-dane-help"]').exists()).toBe(false)
  })

  it('po kliknięciu pokazuje wyjaśnienie zakresu „Wszyscy” i chowa je po drugim kliknięciu', async () => {
    const wrapper = mountPage()
    const toggle = wrapper.get('[data-testid="admin-dane-help-toggle"]')

    await toggle.trigger('click')

    const help = wrapper.get('[data-testid="admin-dane-help"]')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(help.text()).toContain('Wszyscy')
    expect(help.text()).toContain('administrator')
    expect(help.attributes('role')).toBe('note')

    await toggle.trigger('click')
    expect(wrapper.find('[data-testid="admin-dane-help"]').exists()).toBe(false)
  })
})
