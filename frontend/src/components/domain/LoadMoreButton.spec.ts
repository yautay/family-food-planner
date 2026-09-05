import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import LoadMoreButton from './LoadMoreButton.vue'

/**
 * Kontrakt wspólnej kontrolki paginacji (BATCH_19).
 *
 * Sześć ekranów opiera na niej dosięgalność swoich danych, więc trzy rzeczy są
 * tu sprawdzane wprost: przycisk ZNIKA po wczytaniu całości (inaczej użytkownik
 * klikałby w martwy element), etykieta mówi ile ZOSTAŁO, a doładowanie blokuje
 * przycisk zamiast migotać listą (06_UIUX §3.4).
 */
function mountButton(props: Partial<InstanceType<typeof LoadMoreButton>['$props']> = {}) {
  return mount(LoadMoreButton, {
    props: {
      loaded: 50,
      total: 185,
      hasMore: true,
      loading: false,
      testid: 'products-load-more',
      ...props,
    },
  })
}

describe('LoadMoreButton', () => {
  it('pokazuje, ile pozycji zostało do wczytania', () => {
    const wrapper = mountButton()

    const button = wrapper.get('[data-testid="products-load-more"]')
    expect(button.text()).toContain('Pokaż więcej')
    expect(button.text()).toContain('135')
    expect(button.attributes('aria-label')).toContain('pozostało 135')
  })

  it('nie renderuje się, gdy serwer nie ma już czego dać', () => {
    const wrapper = mountButton({ loaded: 185, total: 185, hasMore: false })

    expect(wrapper.find('[data-testid="products-load-more"]').exists()).toBe(false)
  })

  it('emituje `more` po kliknięciu', async () => {
    const wrapper = mountButton()

    await wrapper.get('[data-testid="products-load-more"]').trigger('click')

    expect(wrapper.emitted('more')).toHaveLength(1)
  })

  it('w trakcie doładowania jest zablokowany i mówi o wczytywaniu', () => {
    const wrapper = mountButton({ loading: true })

    const button = wrapper.get('[data-testid="products-load-more"]')
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.text()).toContain('Wczytywanie')
  })

  it('nieudane doładowanie mówi o sobie przy przycisku, a przycisk zostaje', () => {
    const wrapper = mountButton({ failed: true })

    expect(wrapper.get('[data-testid="products-load-more-error"]').text()).toContain(
      'Nie udało się wczytać',
    )
    expect(wrapper.get('[data-testid="products-load-more"]').attributes('disabled')).toBeUndefined()
  })

  it('w trakcie ponowienia komunikat ustępuje spinnerowi', () => {
    const wrapper = mountButton({ failed: true, loading: true })

    expect(wrapper.find('[data-testid="products-load-more-error"]').exists()).toBe(false)
  })

  it('cel dotykowy ma wymagane minimum 44 px (06_UIUX §5)', () => {
    const wrapper = mountButton()

    expect(wrapper.get('[data-testid="products-load-more"]').classes()).toContain('min-h-11')
  })
})
