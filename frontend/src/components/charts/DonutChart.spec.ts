import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import DonutChart from './DonutChart.vue'

const MACROS = [
  { label: 'Białko', value: '50', colorClass: 'stroke-secondary' },
  { label: 'Tłuszcze', value: '25', colorClass: 'stroke-warning' },
  { label: 'Węglowodany', value: '25', colorClass: 'stroke-primary' },
]

describe('DonutChart', () => {
  it('liczy udziały segmentów z podanych wartości', () => {
    const wrapper = mount(DonutChart, { props: { segments: MACROS } })

    expect(
      wrapper.get('[data-testid="donut-chart-segment-Białko"]').attributes('data-percent'),
    ).toBe('50')
    expect(
      wrapper.get('[data-testid="donut-chart-segment-Tłuszcze"]').attributes('data-percent'),
    ).toBe('25')
  })

  it('segmenty układają się jeden za drugim, bez nakładania', () => {
    const wrapper = mount(DonutChart, { props: { segments: MACROS } })

    const offsets = wrapper
      .findAll('circle[data-percent]')
      .map((circle) => Number.parseFloat(circle.attributes('stroke-dashoffset') ?? '0'))

    expect(offsets[0]).toBe(0)
    expect(offsets[1]).toBeLessThan(0)
    expect(offsets[2]).toBeLessThan(offsets[1] as number)
  })

  it('aria-label niesie wartości i udziały — wykres nie jest pusty dla czytnika', () => {
    const wrapper = mount(DonutChart, { props: { segments: MACROS } })

    expect(wrapper.get('[role="img"]').attributes('aria-label')).toBe(
      'Udział makroskładników: Białko 50 g (50%), Tłuszcze 25 g (25%), Węglowodany 25 g (25%)',
    )
  })

  it('legenda podaje nazwę i liczbę, nie tylko kolor', () => {
    const wrapper = mount(DonutChart, { props: { segments: MACROS } })

    expect(wrapper.text()).toContain('Białko')
    expect(wrapper.text()).toContain('50 g · 50%')
  })

  it('pusty dzień pokazuje stan pusty zamiast fałszywego pierścienia', () => {
    const wrapper = mount(DonutChart, {
      props: {
        segments: [
          { label: 'Białko', value: '0', colorClass: 'stroke-secondary' },
          { label: 'Tłuszcze', value: '0', colorClass: 'stroke-warning' },
        ],
      },
    })

    expect(wrapper.find('[data-testid="donut-chart-empty"]').exists()).toBe(true)
    expect(wrapper.findAll('circle[data-percent]')).toHaveLength(0)
    expect(wrapper.get('[role="img"]').attributes('aria-label')).toContain('brak danych')
  })
})
