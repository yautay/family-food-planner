import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ProductCompleteness from './ProductCompleteness.vue'

const productName = 'Płatki owsiane pełnoziarniste z otrębami, pestkami dyni i suszonymi owocami'
const missing = ['kalorii', 'białka', 'tłuszczu', 'węglowodanów', 'indeksu glikemicznego'].map(
  (field) => `${productName}: brak ${field}`,
)

describe('kompletność produktu — surowe komunikaty serwera', () => {
  it('domyślnie pokazuje zwięzły status, a natywne rozwinięcie zachowuje wszystkie komunikaty', async () => {
    const wrapper = mount(ProductCompleteness, { props: { missing, testid: 'incomplete' } })
    const details = wrapper.get('details')
    const summary = wrapper.get('summary')
    expect(summary.text()).toBe('Niepełne dane — szczegóły')
    expect(summary.text()).not.toContain(productName)
    expect(details.attributes('open')).toBeUndefined()
    ;(summary.element as HTMLElement).click()
    await wrapper.vm.$nextTick()
    expect(details.attributes('open')).toBeDefined()
    expect(wrapper.findAll('li').map((row) => row.text())).toEqual(missing)
    ;(summary.element as HTMLElement).click()
    await wrapper.vm.$nextTick()
    expect(details.attributes('open')).toBeUndefined()
  })
})
