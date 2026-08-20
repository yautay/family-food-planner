import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import NutritionBar from './NutritionBar.vue'

/**
 * Wykresy są własnym SVG (ADR-013), więc testujemy to, co użytkownik dostaje:
 * geometrię wypełnienia, kolor z tokens i opis dla czytnika ekranu.
 */
describe('NutritionBar', () => {
  it('wypełnia pasek proporcjonalnie do celu', () => {
    const wrapper = mount(NutritionBar, {
      props: { label: 'Kalorie', value: '900', target: '1800', status: 'below' },
    })

    expect(wrapper.get('[data-testid="nutrition-bar-fill"]').attributes('data-percent')).toBe('50')
  })

  it('nie przekracza 100% przy wartości ponad cel', () => {
    const wrapper = mount(NutritionBar, {
      props: { label: 'Kalorie', value: '4000', target: '2000', status: 'above' },
    })

    expect(wrapper.get('[data-testid="nutrition-bar-fill"]').attributes('data-percent')).toBe('100')
  })

  it('bez celu pasek zostaje pusty i neutralny', () => {
    const wrapper = mount(NutritionBar, {
      props: { label: 'Białko', value: '80', target: null, status: null },
    })

    const fill = wrapper.get('[data-testid="nutrition-bar-fill"]')
    expect(fill.attributes('data-percent')).toBe('0')
    expect(fill.classes()).toContain('fill-primary')
  })

  it('kolor niesie status, ale nigdy sam — aria-label podaje słowa', () => {
    const below = mount(NutritionBar, {
      props: { label: 'Kalorie', value: '900', target: '1800', status: 'below', unit: 'kcal' },
    })
    const ok = mount(NutritionBar, {
      props: { label: 'Kalorie', value: '1800', target: '1800', status: 'ok', unit: 'kcal' },
    })
    const above = mount(NutritionBar, {
      props: { label: 'Kalorie', value: '2500', target: '1800', status: 'above', unit: 'kcal' },
    })

    expect(below.get('[data-testid="nutrition-bar-fill"]').classes()).toContain('fill-warning')
    expect(ok.get('[data-testid="nutrition-bar-fill"]').classes()).toContain('fill-secondary')
    expect(above.get('[data-testid="nutrition-bar-fill"]').classes()).toContain('fill-destructive')

    expect(below.get('[role="img"]').attributes('aria-label')).toBe(
      'Kalorie: 900 kcal, cel 1800 kcal, za mało',
    )
    expect(above.get('[role="img"]').attributes('aria-label')).toContain('za dużo')
  })

  it('formatuje liczby po polsku i obcina nieznaczące zera', () => {
    const wrapper = mount(NutritionBar, {
      props: { label: 'Białko', value: '12.50', target: '80.00', status: 'below', unit: 'g' },
    })

    expect(wrapper.get('[role="img"]').attributes('aria-label')).toBe(
      'Białko: 12,5 g, cel 80 g, za mało',
    )
  })

  it('wariant pionowy rysuje słupek od dołu', () => {
    const wrapper = mount(NutritionBar, {
      props: {
        label: 'poniedziałek',
        value: '500',
        target: '2000',
        status: 'below',
        orientation: 'vertical',
      },
    })

    const fill = wrapper.get('[data-testid="nutrition-bar-fill"]')
    expect(fill.attributes('data-percent')).toBe('25')
    expect(fill.attributes('y')).toBe('75')
    expect(fill.attributes('height')).toBe('25')
  })
})
