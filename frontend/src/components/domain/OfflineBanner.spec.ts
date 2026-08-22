/**
 * `OfflineBanner` — wskaźnik trybu offline i licznik oczekujących zmian (AC 5).
 *
 * Testujemy trzy rzeczy, bo trzy da się tu zepsuć niezauważalnie: że pasek
 * NIE POKAZUJE SIĘ, gdy nie ma o czym mówić (inaczej byłby stałym szumem na
 * widoku krytycznym mobilnym), że licznik jest tekstem, a nie samą kropką
 * (06_UIUX §1), i że komunikat offline mówi o LOSIE ZMIAN, a nie o stanie sieci.
 */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import OfflineBanner from '@/components/domain/OfflineBanner.vue'
import { offline as texts } from '@/lib/texts'

describe('OfflineBanner', () => {
  it('nie renderuje niczego, gdy jest połączenie i pusta kolejka', () => {
    const wrapper = mount(OfflineBanner, { props: { offline: false, pending: 0 } })

    expect(wrapper.find('[data-testid="offline-banner"]').exists()).toBe(false)
  })

  it('offline: mówi, że zmiany zapiszą się po odzyskaniu zasięgu', () => {
    const wrapper = mount(OfflineBanner, { props: { offline: true, pending: 0 } })

    expect(wrapper.get('[data-testid="offline-banner-message"]').text()).toBe(texts.banner)
    expect(wrapper.find('[data-testid="offline-pending"]').exists()).toBe(false)
  })

  it('pokazuje liczbę oczekujących zmian TEKSTEM', () => {
    const wrapper = mount(OfflineBanner, { props: { offline: true, pending: 3 } })

    expect(wrapper.get('[data-testid="offline-pending"]').text()).toBe(texts.pending(3))
  })

  it('jedna zmiana ma poprawną formę gramatyczną', () => {
    const wrapper = mount(OfflineBanner, { props: { offline: true, pending: 1 } })

    expect(wrapper.get('[data-testid="offline-pending"]').text()).toBe('Oczekuje 1 zmiana')
  })

  it('online z zaległościami: komunikat o zapisywaniu, nie o offline', () => {
    const wrapper = mount(OfflineBanner, {
      props: { offline: false, pending: 2, syncing: true },
    })

    expect(wrapper.get('[data-testid="offline-banner-message"]').text()).toBe(texts.syncing)
  })

  it('nie trafia na wydruk — to stan aplikacji, nie treść listy (06_UIUX §6)', () => {
    const wrapper = mount(OfflineBanner, { props: { offline: true, pending: 0 } })

    expect(wrapper.get('[data-testid="offline-banner"]').classes()).toContain('print:hidden')
  })
})
