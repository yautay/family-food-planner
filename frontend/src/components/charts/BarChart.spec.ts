import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import BarChart from './BarChart.vue'
import type { BarDatum } from './BarChart.vue'

/**
 * Wykresy są własnym SVG (ADR-013), więc testujemy to, co użytkownik dostaje:
 * geometrię słupków (wspólna skala!), stackowanie segmentów, linię celu
 * i opis dla czytnika ekranu.
 */
function day(label: string, kcal: string): BarDatum {
  return { label, segments: [{ label: 'kcal', value: kcal, colorClass: 'fill-primary' }] }
}

describe('BarChart', () => {
  it('skaluje słupki wspólną skalą, nie każdy osobno', () => {
    // Bez wspólnej skali dzień 1200 i dzień 2400 kcal wyglądałyby identycznie.
    const wrapper = mount(BarChart, {
      props: { data: [day('pon', '1200'), day('wt', '2400')] },
    })

    const first = wrapper.get('[data-testid="bar-chart-bar-pon-kcal"]').attributes('data-height')
    const second = wrapper.get('[data-testid="bar-chart-bar-wt-kcal"]').attributes('data-height')

    expect(second).toBe('100')
    expect(first).toBe('50')
  })

  it('układa segmenty jeden na drugim (stack), a nie jeden na drugim w tym samym miejscu', () => {
    const wrapper = mount(BarChart, {
      props: {
        data: [
          {
            label: 'pon',
            segments: [
              { label: 'bialko', value: '100', colorClass: 'fill-primary' },
              { label: 'tluszcz', value: '100', colorClass: 'fill-secondary' },
            ],
          },
        ],
      },
    })

    const first = wrapper.get('[data-testid="bar-chart-bar-pon-bialko"]')
    const second = wrapper.get('[data-testid="bar-chart-bar-pon-tluszcz"]')

    // Każdy segment to połowa wysokości; drugi leży DOKŁADNIE nad pierwszym.
    expect(first.attributes('data-height')).toBe('50')
    expect(second.attributes('data-height')).toBe('50')
    expect(Number(first.attributes('y'))).toBeCloseTo(50)
    expect(Number(second.attributes('y'))).toBeCloseTo(0)
  })

  it('rysuje linię celu i wciąga cel do skali, gdy jest wyżej niż słupki', () => {
    const wrapper = mount(BarChart, {
      props: { data: [day('pon', '1000')], target: '2000' },
    })

    const line = wrapper.get('[data-testid="bar-chart-target-line"]')
    // Cel wyznacza skalę (2000), więc leży na samej górze, a słupek na połowie.
    expect(line.attributes('data-y')).toBe('0')
    expect(wrapper.get('[data-testid="bar-chart-bar-pon-kcal"]').attributes('data-height')).toBe(
      '50',
    )
  })

  it('bez celu nie rysuje linii celu', () => {
    const wrapper = mount(BarChart, { props: { data: [day('pon', '1000')], target: null } })

    expect(wrapper.find('[data-testid="bar-chart-target-line"]').exists()).toBe(false)
  })

  it('linia celu zostaje w kadrze także przy przekroczeniu celu', () => {
    const wrapper = mount(BarChart, {
      props: { data: [day('pon', '3000')], target: '2000' },
    })

    const y = Number(wrapper.get('[data-testid="bar-chart-target-line"]').attributes('data-y'))
    expect(y).toBeGreaterThan(0)
    expect(y).toBeLessThan(100)
  })

  it('aria-label podaje wartości wszystkich dni i cel', () => {
    const wrapper = mount(BarChart, {
      props: {
        data: [{ ...day('pon', '1800'), title: 'poniedziałek 17.08' }, day('wt', '2000')],
        target: '2100',
        title: 'Kalorie w tygodniu',
      },
    })

    const label = wrapper.get('[role="img"]').attributes('aria-label') ?? ''
    expect(label).toContain('poniedziałek 17.08 1800 kcal')
    expect(label).toContain('wt 2000 kcal')
    expect(label).toContain('cel 2100 kcal')
  })

  it('pusty tydzień mówi wprost, czego brakuje, zamiast pokazywać zero słupków', () => {
    const wrapper = mount(BarChart, {
      props: { data: [day('pon', '0'), day('wt', '0')] },
    })

    expect(wrapper.find('[data-testid="bar-chart-empty"]').exists()).toBe(true)
    expect(wrapper.get('[role="img"]').attributes('aria-label')).toContain('brak danych')
  })

  it('nie wysadza się na wartościach spoza kontraktu', () => {
    // API zawsze przysyła stringi dziesiętne, ale wykres nie ma prawa paść na „—".
    const wrapper = mount(BarChart, {
      props: { data: [day('pon', '—'), day('wt', '1000')] },
    })

    expect(wrapper.get('[data-testid="bar-chart-bar-pon-kcal"]').attributes('data-height')).toBe(
      '0',
    )
    expect(wrapper.get('[data-testid="bar-chart-bar-wt-kcal"]').attributes('data-height')).toBe(
      '100',
    )
  })

  it('wyróżnia wskazany dzień w etykietach', () => {
    const wrapper = mount(BarChart, {
      props: { data: [{ ...day('pon', '1000'), highlighted: true }, day('wt', '1000')] },
    })

    expect(wrapper.get('[data-testid="bar-chart-label-pon"]').classes()).toContain('font-semibold')
    expect(wrapper.get('[data-testid="bar-chart-label-wt"]').classes()).not.toContain(
      'font-semibold',
    )
  })
})
