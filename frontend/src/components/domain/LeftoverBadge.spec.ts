import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import LeftoverBadge from './LeftoverBadge.vue'

function mountBadge(leftover: string | null, unit: 'g' | 'ml' | 'piece' = 'g') {
  return mount(LeftoverBadge, { props: { leftover, unit } })
}

describe('LeftoverBadge', () => {
  it('pokazuje resztkę z jednostką (02_DOMAIN §9.3)', () => {
    const wrapper = mountBadge('150.000')

    expect(wrapper.get('[data-testid="leftover-badge"]').text()).toBe('Zostanie: 150 g')
  })

  it('duże resztki prezentuje w kilogramach, ale danych nie zmienia', () => {
    expect(mountBadge('1500.000').text()).toBe('Zostanie: 1,5 kg')
  })

  it('resztka zero to osobny, POZYTYWNY komunikat', () => {
    const wrapper = mountBadge('0.000')

    expect(wrapper.get('[data-testid="leftover-badge-exact"]').text()).toBe('Bez resztki')
    expect(wrapper.get('[data-testid="leftover-badge-exact"]').classes()).toContain(
      'text-secondary',
    )
  })

  it('brak wybranego opakowania nie renderuje plakietki (null to nie zero)', () => {
    expect(mountBadge(null).find('[data-testid="leftover-badge"]').exists()).toBe(false)
  })

  it('sztuki pokazuje w sztukach', () => {
    expect(mountBadge('3.000', 'piece').text()).toBe('Zostanie: 3 szt.')
  })
})
