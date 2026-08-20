import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ServingsSplitDrawer from './ServingsSplitDrawer.vue'

/**
 * Rozkład rodzinny: suma mnożników musi równać się liczbie porcji pozycji
 * (02_DOMAIN §7). Liczymy ją na stringach dziesiętnych, bo na floatach
 * 1,1 + 1,1 + 1,1 nie równa się 3,3 (ADR-008).
 */
const PROFILES = [
  { id: 1, name: 'Ania', default_multiplier: '1.00', kcal_goal: null, is_active: true },
  { id: 2, name: 'Olek', default_multiplier: '0.80', kcal_goal: null, is_active: true },
  { id: 3, name: 'Tata', default_multiplier: '1.30', kcal_goal: null, is_active: true },
]

function factory(
  servings: string,
  split: { member_profile_id: number; multiplier: string }[] = [],
) {
  return mount(ServingsSplitDrawer, {
    props: {
      open: true,
      // Profile z API mają więcej pól; test podaje tylko te, których używa drawer.
      profiles: PROFILES as never,
      split: split.map((row) => ({ ...row, member_name: 'x' })) as never,
      servings,
    },
  })
}

describe('ServingsSplitDrawer', () => {
  it('startuje od domyślnych mnożników profili (B03)', () => {
    const wrapper = factory('3.1')

    expect((wrapper.get('[data-testid="split-input-1"]').element as HTMLInputElement).value).toBe(
      '1,00',
    )
    expect((wrapper.get('[data-testid="split-input-2"]').element as HTMLInputElement).value).toBe(
      '0,80',
    )
  })

  it('sumuje mnożniki dokładnie i pozwala zapisać przy zgodzie z porcjami', async () => {
    const wrapper = factory('3.1')

    expect(wrapper.get('[data-testid="split-total"]').text()).toContain('3,1')
    expect(wrapper.find('[data-testid="split-mismatch"]').exists()).toBe(false)
    expect((wrapper.get('[data-testid="split-apply"]').element as HTMLButtonElement).disabled).toBe(
      false,
    )

    await wrapper.get('[data-testid="split-apply"]').trigger('click')
    expect(wrapper.emitted('apply')?.[0]).toEqual([
      [
        { member_profile_id: 1, multiplier: '1.00' },
        { member_profile_id: 2, multiplier: '0.80' },
        { member_profile_id: 3, multiplier: '1.30' },
      ],
      '3.10',
    ])
  })

  it('niezgodna suma blokuje zapis i mówi o tym wprost', async () => {
    const wrapper = factory('5')

    expect(wrapper.find('[data-testid="split-mismatch"]').exists()).toBe(true)
    expect((wrapper.get('[data-testid="split-apply"]').element as HTMLButtonElement).disabled).toBe(
      true,
    )
  })

  it('suma liczona jest bez floatów (1,1 + 1,1 + 1,1 = 3,3)', async () => {
    const wrapper = factory('3.3')
    for (const id of [1, 2, 3]) {
      await wrapper.get(`[data-testid="split-input-${id}"]`).setValue('1,1')
    }

    expect(wrapper.get('[data-testid="split-total"]').text()).toContain('3,3')
    expect(wrapper.find('[data-testid="split-mismatch"]').exists()).toBe(false)
  })

  it('puste pole oznacza „ta osoba nie je tej pozycji"', async () => {
    const wrapper = factory('2.3')
    await wrapper.get('[data-testid="split-input-1"]').setValue('')

    expect(wrapper.get('[data-testid="split-total"]').text()).toContain('2,1')
    expect(wrapper.find('[data-testid="split-mismatch"]').exists()).toBe(true)
  })

  it('bez profili tłumaczy, czego brakuje, zamiast pokazywać pusty formularz', () => {
    const wrapper = mount(ServingsSplitDrawer, {
      props: { open: true, profiles: [], split: [], servings: '1' },
    })

    expect(wrapper.find('[data-testid="split-no-profiles"]').exists()).toBe(true)
  })
})
