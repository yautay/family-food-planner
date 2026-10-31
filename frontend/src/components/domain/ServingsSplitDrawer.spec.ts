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
  it('oferuje ponowienie błędu profili i blokuje kolejne kliknięcie podczas pobierania', async () => {
    const wrapper = factory('3.1')
    await wrapper.setProps({ profilesError: true })
    expect(wrapper.get<HTMLButtonElement>('[data-testid="split-apply"]').element.disabled).toBe(
      true,
    )
    await wrapper.get('[data-testid="split-profiles-retry"]').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
    await wrapper.setProps({ profilesPending: true })
    expect(
      wrapper.get<HTMLButtonElement>('[data-testid="split-profiles-retry"]').element.disabled,
    ).toBe(true)
    await wrapper.get('[data-testid="split-profiles-retry"]').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
    expect(wrapper.find('[data-testid="split-profiles-loading"]').exists()).toBe(true)
    await wrapper.setProps({ profilesError: false, profilesPending: false })
    expect(wrapper.get<HTMLButtonElement>('[data-testid="split-apply"]').element.disabled).toBe(
      false,
    )
  })
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

  it('zmieniona suma automatycznie staje się liczbą porcji pozycji', async () => {
    const wrapper = factory('5')

    expect(wrapper.find('[data-testid="split-mismatch"]').exists()).toBe(false)
    expect((wrapper.get('[data-testid="split-apply"]').element as HTMLButtonElement).disabled).toBe(
      false,
    )
    await wrapper.get('[data-testid="split-apply"]').trigger('click')
    expect(wrapper.emitted('apply')?.[0]?.[1]).toBe('3.10')
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
    expect(wrapper.find('[data-testid="split-mismatch"]').exists()).toBe(false)
  })

  it('zachowuje dwie osoby po 1,1 i pomija trzeci profil przy otwarciu częściowego podziału', async () => {
    const wrapper = factory('2.2', [
      { member_profile_id: 1, multiplier: '1.10' },
      { member_profile_id: 2, multiplier: '1.10' },
    ])
    expect((wrapper.get('[data-testid="split-input-3"]').element as HTMLInputElement).value).toBe(
      '0',
    )
    await wrapper.get('[data-testid="split-apply"]').trigger('click')
    expect(wrapper.emitted('apply')?.[0]).toEqual([
      [
        { member_profile_id: 1, multiplier: '1.10' },
        { member_profile_id: 2, multiplier: '1.10' },
      ],
      '2.20',
    ])
  })

  it('zero pomija osobę, a niepoprawny tekst i całkowite zero blokują zapis bez wyjątku BigInt', async () => {
    const wrapper = factory('3.1')
    await wrapper.get('[data-testid="split-input-1"]').setValue('1e3')
    expect(wrapper.get('[data-testid="split-total"]').text()).toContain('—')
    expect(wrapper.get<HTMLButtonElement>('[data-testid="split-apply"]').element.disabled).toBe(
      true,
    )
    for (const id of [1, 2, 3]) await wrapper.get(`[data-testid="split-input-${id}"]`).setValue('0')
    expect(wrapper.get<HTMLButtonElement>('[data-testid="split-apply"]').element.disabled).toBe(
      true,
    )
    await wrapper.get('[data-testid="split-input-2"]').setValue('1,1')
    await wrapper.get('[data-testid="split-apply"]').trigger('click')
    expect(wrapper.emitted('apply')?.[0]).toEqual([
      [{ member_profile_id: 2, multiplier: '1.1' }],
      '1.1',
    ])
  })

  it('historyczny profil nie znika, a refetch profili nie kasuje szkicu', async () => {
    const wrapper = factory('1.1', [{ member_profile_id: 99, multiplier: '1.1' }])
    expect(wrapper.find('[data-testid="split-input-99"]').exists()).toBe(true)
    await wrapper.get('[data-testid="split-input-99"]').setValue('2,2')
    await wrapper.setProps({ profiles: [...PROFILES] as never })
    expect(wrapper.get<HTMLInputElement>('[data-testid="split-input-99"]').element.value).toBe(
      '2,2',
    )
  })

  it('bez profili tłumaczy, czego brakuje, zamiast pokazywać pusty formularz', () => {
    const wrapper = mount(ServingsSplitDrawer, {
      props: { open: true, profiles: [], split: [], servings: '1' },
    })

    expect(wrapper.find('[data-testid="split-no-profiles"]').exists()).toBe(true)
  })
})
