import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type * as PublicListApi from '@/api/publicList'

import PublicznaListaPage from './PublicznaListaPage.vue'

/**
 * Publiczna strona `/l/:token` — AC 5 karty B11.
 *
 * Najważniejsza asercja to KOMUNIKAT wygaśnięcia: ADR-010 podaje jego treść
 * dosłownie i ten sam ekran obsługuje 410 ORAZ 404 (nie zdradzamy, czy token
 * kiedykolwiek istniał). Reszta to odhaczanie bez logowania i grupowanie
 * pozycji w sekcje w kolejności, którą ustalił serwer.
 */
const { fetchPublicList, checkPublicListItem } = vi.hoisted(() => ({
  fetchPublicList: vi.fn(),
  checkPublicListItem: vi.fn(),
}))

vi.mock('@/api/publicList', async () => {
  const actual = await vi.importActual<typeof PublicListApi>('@/api/publicList')
  return { ...actual, fetchPublicList, checkPublicListItem }
})
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { token: 'tokentokentokentokentokentokentokentoken123' } }),
}))

function item(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    label: 'Mąka pszenna 1 kg',
    amount: '1400.000',
    unit: 'g' as const,
    category_name: 'Sypkie',
    checked: false,
    leftover_amount: '600.000',
    already_have: false,
    packages_count: 2,
    package_size: '1000.00',
    ...overrides,
  }
}

function list(overrides: Record<string, unknown> = {}) {
  return {
    name: 'Zakupy 07.01-13.01.2030',
    expires_at: '2030-01-14T12:00:00Z',
    items: [
      item(),
      item({ id: 2, label: 'Ryż', category_name: 'Sypkie' }),
      item({ id: 3, label: 'Pomidor', category_name: 'Warzywa' }),
    ],
    ...overrides,
  }
}

async function mountPage() {
  const wrapper = mount(PublicznaListaPage, { global: { plugins: [VueQueryPlugin] } })
  await flushPromises()
  return wrapper
}

describe('PublicznaListaPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchPublicList.mockResolvedValue(list())
  })

  it('pokazuje nazwę listy, ważność i sekcje w kolejności z serwera', async () => {
    const wrapper = await mountPage()

    expect(wrapper.get('[data-testid="public-list-title"]').text()).toBe('Zakupy 07.01-13.01.2030')
    expect(wrapper.get('[data-testid="public-list-meta"]').text()).toContain(
      'Link ważny do 14.01.2030',
    )
    expect(wrapper.findAll('h2').map((element) => element.text())).toEqual(['Sypkie', 'Warzywa'])
  })

  it('odhaczanie działa bez logowania i jest optimistic', async () => {
    let resolvePatch: ((value: unknown) => void) | undefined
    checkPublicListItem.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePatch = resolve
        }),
    )
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="shopping-check-1"]').trigger('change')
    await flushPromises()

    // Serwer JESZCZE nie odpowiedział, a licznik już się przesunął.
    expect(wrapper.get('[data-testid="public-list-meta"]').text()).toContain('Odhaczone 1 z 3')
    expect(checkPublicListItem).toHaveBeenCalledWith(
      'tokentokentokentokentokentokentokentoken123',
      1,
      true,
    )

    resolvePatch?.(item({ checked: true }))
    await flushPromises()
    expect(wrapper.get('[data-testid="public-list-meta"]').text()).toContain('Odhaczone 1 z 3')
  })

  it('błąd PATCH-a wycofuje odhaczenie (stan na serwerze się nie zmienił)', async () => {
    const { PublicListRequestError } = await import('@/api/publicList')
    checkPublicListItem.mockRejectedValue(new PublicListRequestError(500))
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="shopping-check-1"]').trigger('change')
    await flushPromises()

    expect(wrapper.get('[data-testid="public-list-meta"]').text()).toContain('Odhaczone 0 z 3')
  })

  it('410 pokazuje ekran wygaśnięcia z komunikatem DOSŁOWNIE z ADR-010', async () => {
    const { PublicListUnavailableError } = await import('@/api/publicList')
    fetchPublicList.mockRejectedValue(new PublicListUnavailableError())

    const wrapper = await mountPage()

    expect(wrapper.get('[data-testid="public-list-unavailable"]').text()).toContain(
      'Ta lista zakupowa już wygasła lub została usunięta.',
    )
    // Zero danych rodziny na ekranie błędu — także żadnej nazwy listy.
    expect(wrapper.text()).not.toContain('Zakupy 07.01')
  })

  it('404 daje TEN SAM ekran co 410 (nie zdradzamy, czy token istniał)', async () => {
    const { PublicListUnavailableError } = await import('@/api/publicList')
    fetchPublicList.mockRejectedValue(new PublicListUnavailableError())

    const wrapper = await mountPage()

    expect(wrapper.find('[data-testid="public-list-unavailable"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="public-list-error"]').exists()).toBe(false)
  })

  it('błąd inny niż wygaśnięcie proponuje ponowienie, a nie ekran wygaśnięcia', async () => {
    const { PublicListRequestError } = await import('@/api/publicList')
    fetchPublicList.mockRejectedValue(new PublicListRequestError(500))

    const wrapper = await mountPage()

    // Błąd sieci ponawiamy RAZ (opóźnienie TanStack Query), więc na ekran
    // „spróbuj ponownie" trzeba poczekać — inaczej test sprawdzałby spinner.
    await vi.waitFor(
      () => expect(wrapper.find('[data-testid="public-list-retry"]').exists()).toBe(true),
      { timeout: 5000 },
    )
    expect(wrapper.find('[data-testid="public-list-unavailable"]').exists()).toBe(false)
  })
})
