import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type * as ShoppingListsApi from '@/api/shoppingLists'

import { useOfflineQueueStore } from '@/stores/offlineQueue'

import ListaZakupowPage from './ListaZakupowPage.vue'

/**
 * Strona listy zakupowej — to, czego nie sprawdzi żaden test backendu:
 *
 * - **optimistic toggle**: checkbox reaguje NATYCHMIAST, a błąd serwera
 *   wycofuje zmianę i pokazuje komunikat (karta B11 §Tests),
 * - **kolejność sekcji przychodzi z serwera** — strona jej nie liczy,
 * - **pozycje „mam już w domu"** są wyszarzone na dole swojej sekcji (AC 2),
 * - zmiana sklepu wysyła PATCH i podmienia CAŁĄ listę (AC 1).
 */
const {
  fetchShoppingList,
  updateShoppingList,
  updateShoppingListItem,
  deleteShoppingList,
  acceptListToPantry,
  fetchStores,
} = vi.hoisted(() => ({
  fetchShoppingList: vi.fn(),
  updateShoppingList: vi.fn(),
  updateShoppingListItem: vi.fn(),
  deleteShoppingList: vi.fn(),
  acceptListToPantry: vi.fn(),
  fetchStores: vi.fn(),
}))

vi.mock('@/api/shoppingLists', async () => {
  const actual = await vi.importActual<typeof ShoppingListsApi>('@/api/shoppingLists')
  return {
    ...actual,
    fetchShoppingList,
    updateShoppingList,
    updateShoppingListItem,
    deleteShoppingList,
    acceptListToPantry,
  }
})
vi.mock('@/api/stores', () => ({ fetchStores, createStore: vi.fn() }))
/** Parametry trasy są MUTOWALNE, żeby jeden test mógł podać śmieciowe id. */
const routeParams: { id: string } = { id: '5' }

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: routeParams }),
  useRouter: () => ({ push: vi.fn() }),
}))

function item(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    category_id: 10,
    product_id: 100,
    retail_product_id: null,
    label: 'Mąka pszenna 1 kg',
    needed_amount: '1400.000',
    amount_unit: 'g' as const,
    packages_count: 2,
    package_size: '1000.00',
    leftover_amount: '600.000',
    already_have: false,
    from_pantry_amount: null,
    checked: false,
    checked_at: null,
    received_at: null,
    position: 0,
    ...overrides,
  }
}

function detail(overrides: Record<string, unknown> = {}) {
  return {
    id: 5,
    generation_id: 3,
    name: 'Zakupy 07.01-13.01.2030',
    round_name: 'Niedziela',
    store_id: null,
    store_name: null,
    expires_at: '2030-01-14T12:00:00Z',
    share: null,
    sections: [
      {
        category_id: 10,
        category_name: 'Sypkie',
        items: [item(), item({ id: 2, label: 'Ryż', already_have: true, position: 1 })],
      },
      {
        category_id: 20,
        category_name: 'Warzywa',
        items: [
          item({
            id: 3,
            category_id: 20,
            label: 'Pomidor',
            needed_amount: '700.000',
            packages_count: null,
            package_size: null,
            leftover_amount: null,
          }),
        ],
      },
    ],
    created_at: '2030-01-06T12:00:00Z',
    updated_at: '2030-01-06T12:00:00Z',
    ...overrides,
  }
}

async function mountPage(
  prepare?: (store: ReturnType<typeof useOfflineQueueStore>) => void,
): Promise<VueWrapper> {
  // Pinia jest potrzebna od B12: strona czyta kolejkę offline (ADR-009).
  // jsdom nie ma IndexedDB, więc `db.ts` degraduje się do „brak snapshotu,
  // pusta kolejka" — czyli dokładnie zachowanie online, o które chodzi tu.
  const pinia = createPinia()
  setActivePinia(pinia)
  prepare?.(useOfflineQueueStore())
  const wrapper = mount(ListaZakupowPage, {
    global: {
      plugins: [VueQueryPlugin, pinia],
      stubs: { RouterLink: { template: '<a><slot /></a>' } },
    },
  })
  await flushPromises()
  return wrapper
}

describe('ListaZakupowPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchShoppingList.mockResolvedValue(detail())
    fetchStores.mockResolvedValue({ items: [], total: 0 })
  })

  it('renderuje sekcje W KOLEJNOŚCI Z SERWERA, nie po nazwie kategorii', async () => {
    const wrapper = await mountPage()

    const naglowki = wrapper.findAll('h2').map((element) => element.text())
    expect(naglowki).toEqual(['Sypkie', 'Warzywa'])
    expect(wrapper.get('[data-testid="lista-nazwa"]').text()).toBe('Zakupy 07.01-13.01.2030')
    expect(wrapper.get('[data-testid="lista-progress"]').text()).toBe('Odhaczone 0 z 3')
  })

  it('pozycja „mam już w domu" jest wyszarzona i stoi tam, gdzie ją dał serwer (AC 2)', async () => {
    const wrapper = await mountPage()

    const sekcja = wrapper.get('[data-testid="lista-sekcja-10"]')
    const pozycje = sekcja.findAll('[data-testid^="shopping-item-"]')
    expect(pozycje.map((row) => row.attributes('data-testid'))).toEqual([
      'shopping-item-1',
      'shopping-item-2',
    ])
    expect(pozycje[1]?.classes()).toContain('opacity-60')
  })

  it('odhaczenie działa OPTIMISTIC: stan zmienia się przed odpowiedzią serwera', async () => {
    let resolvePatch: ((value: unknown) => void) | undefined
    updateShoppingListItem.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePatch = resolve
        }),
    )
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="shopping-check-1"]').trigger('change')
    await flushPromises()

    // Serwer JESZCZE nie odpowiedział, a licznik już się przesunął.
    expect(wrapper.get('[data-testid="lista-progress"]').text()).toBe('Odhaczone 1 z 3')
    expect(updateShoppingListItem).toHaveBeenCalledWith(5, 1, { checked: true })

    resolvePatch?.(item({ checked: true, checked_at: '2030-01-06T12:05:00Z' }))
    await flushPromises()
    expect(wrapper.get('[data-testid="lista-progress"]').text()).toBe('Odhaczone 1 z 3')
  })

  it('błąd PATCH-a WYCOFUJE optimistic update i pokazuje komunikat', async () => {
    const { ApiError } = await import('@/api/client')
    updateShoppingListItem.mockRejectedValue(
      new ApiError(409, { code: 'conflict', message: 'Nie udało się odhaczyć.', details: {} }),
    )
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="shopping-check-1"]').trigger('change')
    await flushPromises()

    expect(wrapper.get('[data-testid="lista-progress"]').text()).toBe('Odhaczone 0 z 3')
    expect(wrapper.get('[data-testid="lista-error"]').text()).toBe('Nie udało się odhaczyć.')
  })

  it('zmiana sklepu wysyła PATCH i podmienia listę na wersję z serwera (AC 1)', async () => {
    fetchStores.mockResolvedValue({
      items: [{ id: 9, name: 'Biedronka', color: null, is_archived: false }],
      total: 1,
    })
    const przesortowana = detail({
      store_id: 9,
      store_name: 'Biedronka',
      sections: [detail().sections[1], detail().sections[0]],
    })
    updateShoppingList.mockResolvedValue(przesortowana)
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="store-picker-input"]').setValue('Biedronka')
    await wrapper.get('[data-testid="store-picker-option-9"]').trigger('click')
    await flushPromises()

    expect(updateShoppingList).toHaveBeenCalledWith(5, { store_id: 9, clear_store: false })
    // Drugi `flushPromises`: pierwszy rozwiązuje mutację, a `setQueryData`
    // w `onSuccess` odświeża widok dopiero w następnym cyklu.
    await flushPromises()
    expect(wrapper.findAll('h2').map((element) => element.text())).toEqual(['Warzywa', 'Sypkie'])
  })

  it('„Przyjmij zakupy do spiżarni" jest zablokowane bez odhaczonych pozycji (AC 7)', async () => {
    const wrapper = await mountPage()

    expect(wrapper.get('[data-testid="lista-accept-open"]').attributes('disabled')).toBeDefined()
  })

  it('przyjęcie do spiżarni wymaga potwierdzenia w dialogu, nie dzieje się od razu', async () => {
    fetchShoppingList.mockResolvedValue(
      detail({
        sections: [{ category_id: 10, category_name: 'Sypkie', items: [item({ checked: true })] }],
      }),
    )
    acceptListToPantry.mockResolvedValue({ created: 1, increased: 0, skipped: 0 })
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="lista-accept-open"]').trigger('click')
    expect(acceptListToPantry).not.toHaveBeenCalled()

    await wrapper.get('[data-testid="accept-confirm"]').trigger('click')
    await flushPromises()

    expect(acceptListToPantry).toHaveBeenCalledWith(5)
    expect(wrapper.get('[data-testid="lista-info"]').text()).toContain('1 nowych pozycji')
  })

  it('usunięcie listy wymaga dialogu z konsekwencjami (06_UIUX §3.3)', async () => {
    deleteShoppingList.mockResolvedValue(undefined)
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="lista-delete-open"]').trigger('click')
    const dialog = wrapper.get('[data-testid="delete-dialog"]')
    expect(dialog.text()).toContain('bezpowrotnie')
    expect(deleteShoppingList).not.toHaveBeenCalled()

    await wrapper.get('[data-testid="delete-confirm"]').trigger('click')
    await flushPromises()

    expect(deleteShoppingList).toHaveBeenCalledWith(5)
  })

  it('śmieciowe id w URL-u daje komunikat „nie znaleziono", a nie wieczny spinner', async () => {
    // Regresja z `/code-review` B11: wyłączone zapytanie ma w TanStack Query 5
    // status `pending`, więc strona wisiała na „Wczytywanie…".
    routeParams.id = 'abc'
    const wrapper = await mountPage()

    expect(wrapper.find('[data-testid="lista-zakupowa-brak"]').exists()).toBe(true)
    expect(fetchShoppingList).not.toHaveBeenCalled()
    routeParams.id = '5'
  })

  it('wygasła lista mówi o tym wprost (publiczny link już nie działa)', async () => {
    fetchShoppingList.mockResolvedValue(detail({ expires_at: '2020-01-01T00:00:00Z' }))
    const wrapper = await mountPage()

    expect(wrapper.find('[data-testid="lista-wygasla"]').exists()).toBe(true)
  })

  // --- znacznik przyjęcia (D19) i tryb offline (ADR-009) -------------------------

  it('pozycja już przyjęta ma TEKSTOWY znacznik, a przycisk liczy tylko nowe (D19)', async () => {
    fetchShoppingList.mockResolvedValue(
      detail({
        sections: [
          {
            category_id: 10,
            category_name: 'Sypkie',
            items: [
              item({ id: 1, checked: true, received_at: '2030-01-06T12:00:00Z' }),
              item({ id: 2, label: 'Ryż', checked: true, position: 1 }),
            ],
          },
        ],
      }),
    )
    const wrapper = await mountPage()

    expect(wrapper.get('[data-testid="shopping-received-1"]').text()).toBe('W spiżarni')
    expect(wrapper.find('[data-testid="shopping-received-2"]').exists()).toBe(false)
    // Do przyjęcia zostaje JEDNA pozycja, choć odhaczone są dwie.
    expect(wrapper.get('[data-testid="lista-accept-hint"]').text()).toBe('Do przyjęcia: 1')
  })

  it('gdy wszystko jest już w spiżarni, przycisk przyjęcia jest nieaktywny (D19)', async () => {
    fetchShoppingList.mockResolvedValue(
      detail({
        sections: [
          {
            category_id: 10,
            category_name: 'Sypkie',
            items: [item({ id: 1, checked: true, received_at: '2030-01-06T12:00:00Z' })],
          },
        ],
      }),
    )
    const wrapper = await mountPage()

    const przycisk = wrapper.get('[data-testid="lista-accept-open"]')
    expect(przycisk.attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="lista-accept-hint"]').text()).toBe(
      'Wszystko z tej listy jest już w spiżarni.',
    )
  })

  it('offline: odhaczenie NIE idzie na serwer, ale UI reaguje i pokazuje banner', async () => {
    const wrapper = await mountPage(({ markOffline }) => markOffline())

    expect(wrapper.get('[data-testid="offline-banner"]').text()).toContain('Tryb offline')

    await wrapper.get('[data-testid="shopping-check-1"]').trigger('change')
    await flushPromises()

    // Zero ruchu na sieci — zmiana czeka w kolejce…
    expect(updateShoppingListItem).not.toHaveBeenCalled()
    // …a checkbox jest odhaczony NATYCHMIAST (optimistic, AC 3).
    expect(wrapper.get('[data-testid="lista-progress"]').text()).toBe('Odhaczone 1 z 3')
    // Zmiana sklepu offline jest zablokowana: kolejność sekcji układa serwer
    // z profilu sklepu, więc przeglądarka nie umiałaby pokazać skutku (R3).
    expect(wrapper.get('[data-testid="lista-sklep"]').text()).toContain(
      'Zmiana sklepu wymaga połączenia',
    )
  })
})
