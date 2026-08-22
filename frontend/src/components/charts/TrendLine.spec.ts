import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import TrendLine from './TrendLine.vue'
import type { TrendPoint } from './TrendLine.vue'

/**
 * Wykresy są własnym SVG (ADR-013), więc testujemy to, co dostaje użytkownik:
 * geometrię polilinii, przerwy na brakach danych, wspólną skalę w trybie
 * nakładki i opis dla czytnika ekranu.
 */
function point(label: string, value: string | null): TrendPoint {
  return { label, value }
}

describe('TrendLine', () => {
  it('zamienia punkty w polilinię o tyle wierzchołkach, ile jest wartości', () => {
    const wrapper = mount(TrendLine, {
      props: { points: [point('1', '1000'), point('2', '2000'), point('3', '1500')] },
    })

    const run = wrapper.get('[data-testid="trend-line-run-0"]').attributes('points') ?? ''
    expect(run.split(' ')).toHaveLength(3)
    expect(wrapper.findAll('[data-testid^="trend-line-marker-"]')).toHaveLength(3)
  })

  it('skaluje wysokość wspólnym maksimum — najwyższy punkt jest na górze', () => {
    const wrapper = mount(TrendLine, {
      props: { points: [point('1', '1000'), point('2', '2000')] },
    })

    // Tryb samodzielny ma wysokość 40: 2000 → y=0, 1000 → y=20.
    expect(wrapper.get('[data-testid="trend-line-marker-2"]').attributes('data-y')).toBe('0')
    expect(wrapper.get('[data-testid="trend-line-marker-1"]').attributes('data-y')).toBe('20')
  })

  it('przerywa linię na braku danych, a nie przeciąga jej przez lukę', () => {
    const wrapper = mount(TrendLine, {
      props: {
        points: [point('1', '1000'), point('2', null), point('3', '1000'), point('4', '1200')],
      },
    })

    // Pierwszy odcinek ma jeden punkt (sam marker), więc powstaje TYLKO drugi.
    expect(wrapper.findAll('[data-testid^="trend-line-run-"]')).toHaveLength(1)
    expect(wrapper.find('[data-testid="trend-line-marker-2"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid^="trend-line-marker-"]')).toHaveLength(3)
  })

  it('samotny punkt zostaje markerem, bo odcinek z jednej pary jest niewidoczny', () => {
    const wrapper = mount(TrendLine, {
      props: { points: [point('1', '1000'), point('2', null)] },
    })

    expect(wrapper.findAll('[data-testid^="trend-line-run-"]')).toHaveLength(0)
    expect(wrapper.find('[data-testid="trend-line-marker-1"]').exists()).toBe(true)
  })

  it('aria-label podaje wartości punktów i nazywa braki wprost', () => {
    const wrapper = mount(TrendLine, {
      props: {
        points: [point('17.08', '1800'), point('18.08', null)],
        title: 'Średnia krocząca',
        unit: 'kcal',
      },
    })

    const label = wrapper.get('[role="img"]').attributes('aria-label') ?? ''
    expect(label).toContain('17.08 1800 kcal')
    expect(label).toContain('18.08 brak danych')
  })

  it('bez ani jednej wartości mówi „brak danych" zamiast rysować pustą linię', () => {
    const wrapper = mount(TrendLine, { props: { points: [point('1', null)] } })

    expect(wrapper.get('[role="img"]').attributes('aria-label')).toContain('brak danych')
    expect(wrapper.findAll('[data-testid^="trend-line-run-"]')).toHaveLength(0)
  })

  it('w trybie samodzielnym renderuje własny svg, w nakładce grupę bez svg', () => {
    const standalone = mount(TrendLine, { props: { points: [point('1', '100')] } })
    const overlay = mount(TrendLine, {
      props: { points: [point('1', '100')], frame: { width: 100, height: 100, scaleMax: 200 } },
    })

    // Nakładka NIE MOŻE mieć własnego `<svg>`: drugi układ współrzędnych wewnątrz
    // wykresu rodzica przesunąłby linię względem słupków.
    expect(standalone.find('svg').exists()).toBe(true)
    expect(overlay.find('svg').exists()).toBe(false)
    expect(overlay.find('g[role="img"]').exists()).toBe(true)
  })

  it('w nakładce liczy geometrię skalą RODZICA, nie własną', () => {
    const wrapper = mount(TrendLine, {
      props: {
        points: [point('1', '1000')],
        // Skala rodzica (BarChart) to 2000 na wysokości 100 → 1000 kcal leży w połowie.
        frame: { width: 100, height: 100, scaleMax: 2000 },
      },
    })

    expect(wrapper.get('[data-testid="trend-line-marker-1"]').attributes('data-y')).toBe('50')
  })

  it('nie wysadza się na wartościach spoza kontraktu', () => {
    // API zawsze przysyła stringi dziesiętne, ale wykres nie ma prawa paść na „—".
    const wrapper = mount(TrendLine, {
      props: { points: [point('1', '—'), point('2', '1000')] },
    })

    expect(wrapper.find('[data-testid="trend-line-marker-1"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="trend-line-marker-2"]').exists()).toBe(true)
  })

  it('kolor bierze z tokens podanych w props (06_UIUX §1 — żadnych hexów)', () => {
    const wrapper = mount(TrendLine, {
      props: {
        points: [point('1', '100'), point('2', '200')],
        colorClass: 'stroke-primary',
        markerClass: 'fill-primary',
      },
    })

    expect(wrapper.get('[data-testid="trend-line-run-0"]').classes()).toContain('stroke-primary')
    expect(wrapper.get('[data-testid="trend-line-marker-1"]').classes()).toContain('fill-primary')
  })
})
