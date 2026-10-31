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

  it('rysuje linię celu SCHODKOWO, gdy cel zmienia się w środku zakresu', () => {
    // Cele są historyczne (02_DOMAIN §6): zmiana celu ma być widoczna jako
    // zmiana poziomu linii, nie jako wygładzone przejście.
    const wrapper = mount(BarChart, {
      props: {
        data: [
          { ...day('pon', '1000'), target: '2000' },
          { ...day('wt', '1000'), target: '2000' },
          { ...day('sr', '1000'), target: '1000' },
        ],
      },
    })

    const levels = wrapper.get('[data-testid="bar-chart-target-step-0"]').attributes('data-levels')
    // Skala to 2000 (najwyższy cel): cel 2000 → y=0, cel 1000 → y=50.
    expect(levels).toBe('0,0,50')
    // Wspólnej, poziomej linii celu wtedy nie ma — byłaby drugą, sprzeczną informacją.
    expect(wrapper.find('[data-testid="bar-chart-target-line"]').exists()).toBe(false)
  })

  it('przerywa linię celu na dniu bez celu, zamiast ciągnąć ostatni poziom', () => {
    const wrapper = mount(BarChart, {
      props: {
        data: [
          { ...day('pon', '1000'), target: '2000' },
          { ...day('wt', '1000'), target: null },
          { ...day('sr', '1000'), target: '2000' },
        ],
      },
    })

    expect(wrapper.findAll('[data-testid^="bar-chart-target-step-"]')).toHaveLength(2)
  })

  it('dzień bez planu jest luką: obrys zamiast słupka, nie zerowa wartość', () => {
    const wrapper = mount(BarChart, {
      props: {
        data: [day('pon', '2000'), { ...day('wt', '0'), empty: true }],
      },
    })

    expect(wrapper.find('[data-testid="bar-chart-gap-wt"]').exists()).toBe(true)
    // Segmentu wartości dla luki nie ma w ogóle — zero i „brak planu" to nie to samo.
    expect(wrapper.find('[data-testid="bar-chart-bar-wt-kcal"]').exists()).toBe(false)
    expect(wrapper.get('[role="img"]').attributes('aria-label')).toContain('wt brak planu')
  })

  it('luka nie wchodzi do skali i nie zmienia wysokości pozostałych słupków', () => {
    const wrapper = mount(BarChart, {
      props: { data: [day('pon', '2000'), { ...day('wt', '9999'), empty: true }] },
    })

    expect(wrapper.get('[data-testid="bar-chart-bar-pon-kcal"]').attributes('data-height')).toBe(
      '100',
    )
  })

  it('udostępnia slot nakładki w układzie współrzędnych słupków', () => {
    // Na tym stoi wspólna skala trendu i słupków (B13) — bez geometrii ze slotu
    // nakładka miałaby własną skalę i porównanie byłoby złudzeniem.
    const wrapper = mount(BarChart, {
      props: { data: [day('pon', '1000')], target: '2000' },
      slots: {
        overlay: `<template #overlay="{ width, height, scaleMax }">
          <text data-testid="overlay-probe" :data-geometry="[width, height, scaleMax].join('/')" />
        </template>`,
      },
    })

    expect(wrapper.get('[data-testid="overlay-probe"]').attributes('data-geometry')).toBe(
      '14/100/2000',
    )
  })

  it('id słupka rozdziela dni o tej samej etykiecie (zakres dłuższy niż miesiąc)', () => {
    // W zakresie 92-dniowym „05" wraca trzy razy; bez `id` powstałyby
    // zduplikowane `data-testid` i strict mode Playwrighta by na nich padł.
    const wrapper = mount(BarChart, {
      props: {
        data: [
          { ...day('05', '1000'), id: '2026-05-05' },
          { ...day('05', '2000'), id: '2026-06-05' },
        ],
      },
    })

    expect(
      wrapper.get('[data-testid="bar-chart-bar-2026-05-05-kcal"]').attributes('data-height'),
    ).toBe('50')
    expect(
      wrapper.get('[data-testid="bar-chart-bar-2026-06-05-kcal"]').attributes('data-height'),
    ).toBe('100')
  })

  it('w trybie schodkowym aria-label podaje cel PRZY KAŻDYM dniu', () => {
    // Wspólnej linii celu nie ma, więc bez tego czytnik ekranu nie usłyszałby
    // celu w ogóle — a cel jest tu różny dla różnych dni.
    const wrapper = mount(BarChart, {
      props: {
        data: [
          { ...day('pon', '1800'), target: '2000', title: 'poniedziałek 17.08' },
          { ...day('wt', '1900'), target: '2400' },
        ],
        unit: 'kcal',
      },
    })

    const label = wrapper.get('[role="img"]').attributes('aria-label') ?? ''
    expect(label).toContain('poniedziałek 17.08 1800 kcal (cel 2000 kcal)')
    expect(label).toContain('wt 1900 kcal (cel 2400 kcal)')
  })

  it('komunikat pustego wykresu da się podmienić na tekst strony', () => {
    const wrapper = mount(BarChart, {
      props: { data: [day('pon', '0')], emptyText: 'Brak zaplanowanych dni w tym zakresie.' },
    })

    expect(wrapper.get('[data-testid="bar-chart-empty"]').text()).toBe(
      'Brak zaplanowanych dni w tym zakresie.',
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
  it('opisuje jawny zakres linii celu bez zmiany domyślnego celu posiłku', () => {
    const wrapper = mount(BarChart, {
      props: {
        data: [{ ...day('pon', '1800'), target: '2000' }],
        targetLabel: 'historyczny cel konta',
      },
    })
    expect(wrapper.get('svg').attributes('aria-label')).toContain('historyczny cel konta 2000 kcal')
    expect(wrapper.find('[data-testid="bar-chart-target-step-0"]').exists()).toBe(true)
  })

  it('długi zakres ma region dostępny z klawiatury i zachowuje wszystkie dni', () => {
    const wrapper = mount(BarChart, {
      props: { data: Array.from({ length: 92 }, (_, i) => day(String(i), '1000')) },
    })
    expect(wrapper.get('[role="region"]').attributes('tabindex')).toBe('0')
    expect(wrapper.get('figure').attributes('style')).toContain('2208px')
    expect(wrapper.findAll('[data-testid^="bar-chart-label-"]')).toHaveLength(92)
  })
})
