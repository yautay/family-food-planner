import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AmountInput from './AmountInput.vue'

function mountInput(props: Record<string, unknown> = {}) {
  return mount(AmountInput, { props: { modelValue: null, ...props } })
}

describe('AmountInput', () => {
  it('wpisany przecinek wychodzi do API jako kropka', async () => {
    const wrapper = mountInput()

    await wrapper.get('[data-testid="amount"]').setValue('12,5')

    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toBe('12.5')
  })

  it('wyczyszczone pole daje null, a nie zero', async () => {
    const wrapper = mountInput({ modelValue: '12.5' })

    await wrapper.get('[data-testid="amount"]').setValue('')

    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toBeNull()
  })

  it('wartość z API pokazuje po polsku', () => {
    const wrapper = mountInput({ modelValue: '0.80' })

    expect((wrapper.get('[data-testid="amount"]').element as HTMLInputElement).value).toBe('0,80')
  })

  it('oznacza błąd, gdy wpis nie jest liczbą', async () => {
    const wrapper = mountInput()

    await wrapper.get('[data-testid="amount"]').setValue('dużo')

    expect(wrapper.get('[data-testid="amount"]').attributes('aria-invalid')).toBe('true')
  })

  it('domyślnie odrzuca zero jako ilość', async () => {
    const wrapper = mountInput()

    await wrapper.get('[data-testid="amount"]').setValue('0')

    expect(wrapper.get('[data-testid="amount"]').attributes('aria-invalid')).toBe('true')
  })

  it('dla wartości odżywczych zero jest poprawne', async () => {
    const wrapper = mountInput({ positive: false })

    await wrapper.get('[data-testid="amount"]').setValue('0')

    expect(wrapper.get('[data-testid="amount"]').attributes('aria-invalid')).toBe('false')
  })

  it('pilnuje liczby miejsc po przecinku wg skali kolumny', async () => {
    const wrapper = mountInput({ decimalPlaces: 2 })

    await wrapper.get('[data-testid="amount"]').setValue('12,345')

    expect(wrapper.get('[data-testid="amount"]').attributes('aria-invalid')).toBe('true')
  })

  it('pokazuje wybór jednostki, gdy podano listę', () => {
    const wrapper = mountInput({ units: ['g', 'kg', 'łyżka'], unit: 'g' })

    const options = wrapper.get('[data-testid="amount-unit"]').findAll('option')
    expect(options.map((option) => option.text())).toEqual(['g', 'kg', 'łyżka'])
  })

  it('zmiana jednostki wychodzi osobnym zdarzeniem', async () => {
    const wrapper = mountInput({ units: ['g', 'kg'], unit: 'g' })

    await wrapper.get('[data-testid="amount-unit"]').setValue('kg')

    expect(wrapper.emitted('update:unit')?.at(-1)?.[0]).toBe('kg')
  })

  it('sygnalizuje poprawność osobnym zdarzeniem', async () => {
    // Konsument (B05+) nie może wysłać do API tekstu wpisanego w trakcie pisania,
    // dlatego obok wartości leci informacja, czy nadaje się do zapisu.
    const wrapper = mountInput()

    await wrapper.get('[data-testid="amount"]').setValue('12,5')
    expect(wrapper.emitted('update:valid')?.at(-1)?.[0]).toBe(true)

    await wrapper.get('[data-testid="amount"]').setValue('dużo')
    expect(wrapper.emitted('update:valid')?.at(-1)?.[0]).toBe(false)
  })

  it('bez listy jednostek nie renderuje selecta', () => {
    const wrapper = mountInput()

    expect(wrapper.find('[data-testid="amount-unit"]').exists()).toBe(false)
  })
})
