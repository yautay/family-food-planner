import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ShoppingItemRow from './ShoppingItemRow.vue'

/**
 * Wiersz listy zakupowej — Acceptance Criteria 1–3 karty B11:
 *
 * - checkbox jest DUŻY (~48 px) i to on jest celem dotykowym w sklepie,
 * - pozycja „mam już w domu" jest wyszarzona i opisana TEKSTEM (nie tylko kolorem),
 * - w trybie druku pojawia się znak `☐`, a checkbox przeglądarki znika.
 */
function mountRow(overrides: Record<string, unknown> = {}) {
  return mount(ShoppingItemRow, {
    props: {
      itemId: 7,
      label: 'Mąka pszenna 1 kg',
      amount: '1400.000',
      unit: 'g' as const,
      checked: false,
      alreadyHave: false,
      leftover: '600.000',
      packagesCount: 2,
      packageSize: '1000.00',
      ...overrides,
    },
  })
}

describe('ShoppingItemRow', () => {
  it('checkbox ma ~48 px celu dotykowego (06_UIUX §5)', () => {
    const wrapper = mountRow()

    expect(wrapper.get('[data-testid="shopping-check-7"]').classes()).toContain('size-12')
  })

  it('emituje `toggle` z ODWRÓCONYM stanem, nie z bieżącym', async () => {
    const wrapper = mountRow({ checked: false })

    await wrapper.get('[data-testid="shopping-check-7"]').trigger('change')

    expect(wrapper.emitted('toggle')).toEqual([[{ itemId: 7, checked: true }]])
  })

  it('odhaczona pozycja emituje odznaczenie (odhaczanie działa w obie strony)', async () => {
    const wrapper = mountRow({ checked: true })

    await wrapper.get('[data-testid="shopping-check-7"]').trigger('change')

    expect(wrapper.emitted('toggle')).toEqual([[{ itemId: 7, checked: false }]])
  })

  it('pokazuje ilość i opakowania przez `formatAmount` (g → kg powyżej 1000)', () => {
    const wrapper = mountRow()

    expect(wrapper.get('[data-testid="shopping-amount-7"]').text()).toBe('1,4 kg')
    expect(wrapper.get('[data-testid="shopping-packages-7"]').text()).toBe('2 x 1 kg')
  })

  it('plakietka resztki jest widoczna, gdy znamy opakowanie (02_DOMAIN §9.3)', () => {
    const wrapper = mountRow()

    expect(wrapper.get('[data-testid="leftover-badge"]').text()).toBe('Zostanie: 600 g')
  })

  it('bez opakowania nie ma plakietki resztki (null to nie zero)', () => {
    const wrapper = mountRow({ packagesCount: null, packageSize: null, leftover: null })

    expect(wrapper.find('[data-testid="leftover-badge"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="shopping-packages-7"]').exists()).toBe(false)
  })

  it('„mam już w domu" wyszarza wiersz I dopisuje tekst (AC 2)', () => {
    const wrapper = mountRow({ alreadyHave: true })

    expect(wrapper.get('[data-testid="shopping-item-7"]').classes()).toContain('opacity-60')
    expect(wrapper.get('[data-testid="shopping-have-7"]').text()).toBe('Mam już w domu')
  })

  it('w druku checkbox ustępuje znakowi ☐, a plakietki znikają (AC 3, 06_UIUX §6)', () => {
    const wrapper = mountRow()

    // Znak jest w DOM-ie i pokazuje się dopiero w `@media print`; checkbox
    // przeglądarki idzie wtedy w `print:hidden`. Snapshot klas jest tu jedyną
    // sensowną asercją, bo vitest nie renderuje mediów wydruku.
    expect(wrapper.html()).toContain('☐')
    expect(wrapper.get('[data-testid="shopping-check-7"]').classes()).toContain('print:hidden')
    expect(wrapper.get('[data-testid="leftover-badge"]').classes()).toContain('print:hidden')
  })

  it('odhaczona pozycja jest przekreślona na ekranie, ale nie na wydruku', () => {
    const wrapper = mountRow({ checked: true })

    const label = wrapper.get('[data-testid="shopping-label-7"]')
    expect(label.classes()).toContain('line-through')
    expect(label.classes()).toContain('print:no-underline')
  })
})
