import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { StagedIngredientRead } from '@/api/pdfImport'

import StagedIngredientRow from './StagedIngredientRow.vue'

/**
 * Wiersz składnika w review importu — Acceptance Criterion 2 karty B16:
 * potwierdź sugestię / wybierz pickerem / utwórz nowy inline.
 *
 * `ProductPicker` jest zastubowany: jego własny kontrakt ma osobny spec
 * (`ProductPicker.spec.ts`), a tu chodzi o to, że wiersz REUŻYWA go zamiast
 * rysować swój select (05_FRONTEND §4).
 */
const PICKER_STUB = {
  name: 'ProductPicker',
  props: ['modelValue', 'label', 'disabled'],
  emits: ['update:modelValue', 'selected'],
  template: '<div data-testid="picker-stub" />',
}

function ingredient(overrides: Partial<StagedIngredientRead> = {}): StagedIngredientRead {
  return {
    id: 7,
    raw_name: 'Cebula',
    raw_qty: '2.000',
    raw_unit: 'Sztuka',
    grams: '210.000',
    from_extras_section: false,
    match_kind: 'none',
    confidence: null,
    suggested_product_id: null,
    suggested_product_name: null,
    confirmed_product_id: null,
    confirmed_product_name: null,
    create_new_product: false,
    ...overrides,
  }
}

function mountRow(overrides: Partial<StagedIngredientRead> = {}) {
  return mount(StagedIngredientRow, {
    props: { ingredient: ingredient(overrides) },
    global: { stubs: { ProductPicker: PICKER_STUB } },
  })
}

describe('StagedIngredientRow', () => {
  it('pokazuje ilość dokładnie tak, jak stała w dokumencie', () => {
    const wrapper = mountRow()

    expect(wrapper.get('[data-testid="staged-ingredient-amount"]').text()).toBe(
      '2.000 x Sztuka (210 g)',
    )
  })

  it('wiersz bez pary ilość + jednostka pokazuje samą gramaturę (wariant D20)', () => {
    const wrapper = mountRow({ raw_qty: null, raw_unit: null, grams: '200.000' })

    expect(wrapper.get('[data-testid="staged-ingredient-amount"]').text()).toBe('200 g')
  })

  it('ścieżka 1: propozycję potwierdza się JEDNYM kliknięciem', async () => {
    const wrapper = mountRow({
      suggested_product_id: 42,
      suggested_product_name: 'Cebula',
      match_kind: 'exact',
    })

    await wrapper.get('[data-testid="staged-ingredient-confirm-7"]').trigger('click')

    expect(wrapper.emitted('confirm')).toEqual([[{ ingredientId: 7, productId: 42 }]])
  })

  it('propozycja AI niesie swoją pewność — człowiek ma wiedzieć, czemu ufa', () => {
    const wrapper = mountRow({
      suggested_product_id: 42,
      suggested_product_name: 'Skyr naturalny',
      match_kind: 'ai',
      confidence: '0.82',
    })
    const text = wrapper.get('[data-testid="staged-ingredient-suggestion"]').text()

    expect(text).toContain('propozycja AI')
    expect(text).toContain('0.82')
  })

  it('potwierdzone mapowanie chowa propozycję — nie ma czego już potwierdzać', () => {
    const wrapper = mountRow({
      suggested_product_id: 42,
      suggested_product_name: 'Cebula',
      confirmed_product_id: 42,
      confirmed_product_name: 'Cebula',
      match_kind: 'exact',
    })

    expect(wrapper.find('[data-testid="staged-ingredient-suggestion"]').exists()).toBe(false)
  })

  it('ścieżka 2: wybór z pickera emituje mapowanie', async () => {
    const wrapper = mountRow()

    await wrapper
      .findComponent(PICKER_STUB)
      .vm.$emit('update:modelValue', { id: 11, name: 'Cebula' })

    expect(wrapper.emitted('confirm')).toEqual([[{ ingredientId: 7, productId: 11 }]])
  })

  it('wyczyszczenie pickera emituje `clear`, a nie mapowanie na null', async () => {
    const wrapper = mountRow({ confirmed_product_id: 11, confirmed_product_name: 'Cebula' })

    await wrapper.findComponent(PICKER_STUB).vm.$emit('update:modelValue', null)

    expect(wrapper.emitted('clear')).toEqual([[7]])
    expect(wrapper.emitted('confirm')).toBeUndefined()
  })

  it('ścieżka 3: „Utwórz nowy" emituje decyzję o założeniu produktu', async () => {
    const wrapper = mountRow()

    await wrapper.get('[data-testid="staged-ingredient-create-new-7"]').trigger('click')

    expect(wrapper.emitted('create-new')).toEqual([[7]])
  })

  it('składnik z sekcji `Produkty` jest oznaczony — nie dzieli się przez porcje', () => {
    const wrapper = mountRow({ from_extras_section: true })

    expect(wrapper.text()).toContain('dodatek do posiłku')
  })

  it('wiersz zablokowany (trwa zapis) nie da się kliknąć', () => {
    const wrapper = mount(StagedIngredientRow, {
      props: { ingredient: ingredient(), disabled: true },
      global: { stubs: { ProductPicker: PICKER_STUB } },
    })

    expect(
      wrapper.get('[data-testid="staged-ingredient-create-new-7"]').attributes('disabled'),
    ).toBeDefined()
  })
})
