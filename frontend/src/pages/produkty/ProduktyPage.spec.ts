import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type * as RouterModule from 'vue-router'

import { queryKeys } from '@/api/queryKeys'
import ProduktyPage from './ProduktyPage.vue'

/**
 * Paginacja katalogu (BATCH_19, ustalenie R4 P1).
 *
 * Dług, który to zamyka: strona wysyłała `offset: 0` ze stałym limitem i pisała
 * obok „Produktów: 185", renderując 50 — liczba i widok kłamały razem. Test
 * pilnuje więc DWÓCH rzeczy naraz: że licznik podaje relację widocznych do
 * wszystkich i że da się dojść do ostatniej pozycji.
 */

const navigation = vi.hoisted(() => ({ query: {} as Record<string, string> }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {}, query: navigation.query }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

const { fetchProducts, fetchCategories } = vi.hoisted(() => ({
  fetchProducts: vi.fn(),
  fetchCategories: vi.fn(),
}))
vi.mock('@/api/catalog', () => ({ fetchProducts, fetchCategories }))

function product(id: number) {
  return {
    id,
    name: `Produkt ${id}`,
    normalized_name: `produkt ${id}`,
    category_id: 1,
    category_name: 'Warzywa',
    measure_kind: 'mass' as const,
    piece_weight_g: null,
    verification_status: 'verified' as const,
    verified_at: '2026-08-21T10:00:00Z',
    perishability: 'fresh' as const,
    perishability_override: null,
    is_archived: false,
    nutrition: {
      kcal_100: '40.00',
      protein_100: '1.10',
      fat_100: '0.10',
      carbs_100: '9.30',
      fiber_100: '1.70',
      sugars_100: '4.20',
      glycemic_index: '15.0',
      nutrition_source: 'usda:11282',
    },
    completeness: {
      complete: true,
      has_core_macros: true,
      has_glycemic_index: true,
      missing: [],
    },
    created_at: '2026-08-21T10:00:00Z',
    updated_at: '2026-08-21T10:00:00Z',
  }
}

/** Zbiór większy niż strona — 60 pozycji przy `PAGE_SIZE` 50. */
const TOTAL = 60
const PAGE_SIZE = 50
const ALL = Array.from({ length: TOTAL }, (_unused, index) => product(index + 1))

async function mountPage() {
  setActivePinia(createPinia())
  const wrapper = mount(ProduktyPage, {
    global: { plugins: [VueQueryPlugin], stubs: { RouterLink: true } },
  })
  await flushPromises()
  return wrapper
}

/** Mount bez ponawiania — testy ścieżek błędu nie mają czekać na retry. */
async function mountPageWithoutRetry() {
  setActivePinia(createPinia())
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = mount(ProduktyPage, {
    global: { plugins: [[VueQueryPlugin, { queryClient }]], stubs: { RouterLink: true } },
  })
  await flushPromises()
  return wrapper
}

describe('ProduktyPage — paginacja', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    navigation.query = {}
    fetchCategories.mockResolvedValue({
      items: [{ id: 1, name: 'Warzywa', position: 1 }],
      total: 1,
    })
    fetchProducts.mockImplementation(({ offset = 0, limit = PAGE_SIZE }) =>
      Promise.resolve({ items: ALL.slice(offset, offset + limit), total: TOTAL }),
    )
  })

  it('pierwsza strona pokazuje limit pozycji i licznik „widoczne z wszystkich"', async () => {
    const wrapper = await mountPage()

    expect(wrapper.findAll('[data-testid^="product-card-"]')).toHaveLength(PAGE_SIZE)
    expect(wrapper.get('[data-testid="products-total"]').text()).toContain('50 z 60')
  })

  it('„pokaż więcej" dowozi resztę zbioru i znika po wczytaniu całości', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="products-load-more"]').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('[data-testid^="product-card-"]')).toHaveLength(TOTAL)
    expect(wrapper.get('[data-testid="products-total"]').text()).toContain('60 z 60')
    expect(wrapper.find('[data-testid="products-load-more"]').exists()).toBe(false)
  })

  it('doładowanie zwiększa `offset`, a nie `limit` (sufit serwera to 200, 04_API §1)', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="products-load-more"]').trigger('click')
    await flushPromises()

    expect(fetchProducts).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({ limit: 50, offset: 0 }),
    )
    expect(fetchProducts).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ limit: 50, offset: 50 }),
    )
  })

  it('zbiór mieszczący się na stronie nie dostaje przycisku', async () => {
    fetchProducts.mockResolvedValue({ items: ALL.slice(0, 3), total: 3 })

    const wrapper = await mountPage()

    expect(wrapper.get('[data-testid="products-total"]').text()).toContain('3 z 3')
    expect(wrapper.find('[data-testid="products-load-more"]').exists()).toBe(false)
  })

  it('nieudane doładowanie NIE kasuje wierszy, które już widać', async () => {
    // Regresja znaleziona przez `/code-review` na diffie B19: `isError` całego
    // zapytania zapalał się także po nieudanym `fetchNextPage`, więc ekran
    // pokazywał komunikat błędu ZAMIAST 50 poprawnych wierszy z cache'u —
    // a licznik dalej mówił „50 z 60". Dokładnie ten rozjazd liczby z widokiem
    // ten batch likwiduje, więc nie wolno go wprowadzić z powrotem.
    fetchProducts
      .mockResolvedValueOnce({ items: ALL.slice(0, PAGE_SIZE), total: TOTAL })
      .mockRejectedValue(new Error('sieć padła'))

    const wrapper = await mountPageWithoutRetry()
    expect(wrapper.findAll('[data-testid^="product-card-"]')).toHaveLength(PAGE_SIZE)

    await wrapper.get('[data-testid="products-load-more"]').trigger('click')
    await flushPromises()
    await flushPromises()

    expect(wrapper.findAll('[data-testid^="product-card-"]')).toHaveLength(PAGE_SIZE)
    expect(wrapper.get('[data-testid="products-total"]').text()).toContain('50 z 60')
    // Komunikat siada PRZY przycisku, bo to on jest ponowieniem.
    expect(wrapper.get('[data-testid="products-load-more-error"]').text()).toContain(
      'Nie udało się wczytać',
    )
    expect(wrapper.find('[data-testid="products-load-more"]').exists()).toBe(true)
  })

  it('padnięcie PIERWSZEJ strony pokazuje błąd, bo nie ma czego pokazać', async () => {
    fetchProducts.mockRejectedValue(new Error('sieć padła'))

    const wrapper = await mountPageWithoutRetry()
    await flushPromises()

    expect(wrapper.find('[data-testid="products-list"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Coś poszło nie tak')
  })

  it('pozycja powtórzona na dwóch stronach renderuje się raz', async () => {
    // Wstawienie wiersza między pobraniem stron przesuwa ich granice, więc
    // serwer może oddać tę samą pozycję dwa razy. Bez odsiewu Vue dostaje dwa
    // węzły z tym samym `:key` i psuje patchowanie listy.
    fetchProducts
      .mockResolvedValueOnce({ items: ALL.slice(0, PAGE_SIZE), total: TOTAL })
      .mockResolvedValueOnce({ items: ALL.slice(PAGE_SIZE - 2), total: TOTAL })

    const wrapper = await mountPage()
    await wrapper.get('[data-testid="products-load-more"]').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('[data-testid^="product-card-"]')).toHaveLength(TOTAL)
    expect(wrapper.findAll('[data-testid="product-card-49"]')).toHaveLength(1)
    expect(wrapper.get('[data-testid="products-total"]').text()).toContain('60 z 60')
  })

  it('zmiana filtra wraca do pierwszej strony', async () => {
    const wrapper = await mountPage()
    await wrapper.get('[data-testid="products-load-more"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-testid^="product-card-"]')).toHaveLength(TOTAL)

    // Nowy filtr = nowy klucz zapytań, więc doładowane strony nie mogą zostać
    // na ekranie: pokazywałyby wynik POPRZEDNIEGO zapytania.
    await wrapper.get('[data-testid="products-include-archived"]').setValue(true)
    await flushPromises()

    expect(wrapper.findAll('[data-testid^="product-card-"]')).toHaveLength(PAGE_SIZE)
  })
  it('powrót z edycji odtwarza filtr i stronę z pozycji 60', async () => {
    navigation.query = { category: '1', pages: '2', focus: '60', archived: '1' }
    const wrapper = await mountPage()
    await flushPromises()
    await flushPromises()
    expect(wrapper.findAll('[data-testid^="product-card-"]')).toHaveLength(60)
    expect(fetchProducts).toHaveBeenCalledWith(
      expect.objectContaining({ category_id: 1, include_archived: true, offset: 50 }),
    )
    expect(wrapper.get('[data-testid="products-category-filter"]').element).toHaveProperty(
      'value',
      '1',
    )
    expect(wrapper.get('[data-testid="products-include-archived"]').element).toHaveProperty(
      'checked',
      true,
    )
    await wrapper.get('[data-testid="products-include-archived"]').setValue(false)
    await flushPromises()
    expect(wrapper.findAll('[data-testid^="product-card-"]')).toHaveLength(50)
  })
  it('ogromne pages ma ograniczony budżet żądań, a dalsze wyniki wymagają Pokaż więcej', async () => {
    navigation.query = { pages: '9007199254740991', focus: '9999999' }
    fetchProducts.mockImplementation(({ offset, limit }) =>
      Promise.resolve({
        items: Array.from({ length: limit }, (_, i) => product(offset + i + 1)),
        total: 1_000_000,
      }),
    )
    const wrapper = await mountPage()
    await vi.waitFor(() => expect(fetchProducts).toHaveBeenCalledTimes(3))
    for (let i = 0; i < 5; i += 1) await flushPromises()
    expect(fetchProducts).toHaveBeenCalledTimes(3)
    expect(wrapper.findAll('[data-testid^="product-card-"]')).toHaveLength(150)
    expect(wrapper.get('[data-testid="products-restore-limited"]').text()).toContain(
      'Przywrócono część',
    )
    expect(wrapper.find('[data-testid="product-card-9999999"]').exists()).toBe(false)
    await wrapper.get('[data-testid="products-load-more"]').trigger('click')
    await flushPromises()
    await flushPromises()
    expect(fetchProducts).toHaveBeenCalledTimes(4)
    expect(fetchProducts).toHaveBeenLastCalledWith(
      expect.objectContaining({ limit: 50, offset: 150 }),
    )
    expect(wrapper.findAll('[data-testid^="product-card-"]')).toHaveLength(200)
    expect(wrapper.find('[data-testid="products-load-more"]').exists()).toBe(true)
  })

  it('nakładające się strony nie odnawiają automatycznego budżetu', async () => {
    navigation.query = { pages: '9007199254740991' }
    fetchProducts.mockResolvedValue({ items: ALL.slice(0, 50), total: 1_000_000 })
    const wrapper = await mountPage()
    await vi.waitFor(() => expect(fetchProducts).toHaveBeenCalledTimes(3))
    for (let i = 0; i < 5; i += 1) await flushPromises()
    expect(fetchProducts).toHaveBeenCalledTimes(3)
    expect(wrapper.findAll('[data-testid^="product-card-"]')).toHaveLength(50)
    expect(wrapper.find('[data-testid="products-restore-limited"]').exists()).toBe(true)
  })

  it('budżet nie usuwa pięciu stron z cache ani fokusu powracającej pozycji', async () => {
    navigation.query = { pages: '5', focus: '230' }
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    })
    queryClient.setQueryData(
      queryKeys.products.list({
        limit: 50,
        q: undefined,
        category_id: undefined,
        include_archived: false,
      }),
      {
        pages: Array.from({ length: 5 }, (_, page) => ({
          items: Array.from({ length: 50 }, (_, i) => product(page * 50 + i + 1)),
          total: 500,
        })),
        pageParams: [0, 50, 100, 150, 200],
      },
    )
    setActivePinia(createPinia())
    const wrapper = mount(ProduktyPage, {
      attachTo: document.body,
      global: { plugins: [[VueQueryPlugin, { queryClient }]], stubs: { RouterLink: true } },
    })
    try {
      await flushPromises()
      await vi.waitFor(() => expect(document.activeElement?.id).toBe('product-230'))
      expect(wrapper.findAll('[data-testid^="product-card-"]')).toHaveLength(250)
      expect(fetchProducts).not.toHaveBeenCalled()
      expect(wrapper.find('[data-testid="products-restore-limited"]').exists()).toBe(false)
    } finally {
      wrapper.unmount()
      queryClient.clear()
    }
  })
  it('zimny powrót na drugą stronę nadal pobiera dwie strony i przywraca fokus', async () => {
    navigation.query = { category: '1', pages: '2', focus: '60' }
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    setActivePinia(createPinia())
    const wrapper = mount(ProduktyPage, {
      attachTo: document.body,
      global: { plugins: [[VueQueryPlugin, { queryClient }]], stubs: { RouterLink: true } },
    })
    try {
      await flushPromises()
      await vi.waitFor(() => expect(document.activeElement?.id).toBe('product-60'))
      expect(fetchProducts).toHaveBeenCalledTimes(2)
      expect(fetchProducts).toHaveBeenLastCalledWith(
        expect.objectContaining({ category_id: 1, offset: 50, limit: 50 }),
      )
      expect(wrapper.findAll('[data-testid^="product-card-"]')).toHaveLength(60)
      expect(wrapper.find('[data-testid="products-restore-limited"]').exists()).toBe(false)
    } finally {
      wrapper.unmount()
      queryClient.clear()
    }
  })
  it('niepełne dane biblioteki mają krótki opis i wszystkie surowe komunikaty w rozwinięciu', async () => {
    const name = 'Płatki owsiane pełnoziarniste z otrębami, pestkami dyni i suszonymi owocami'
    const missing = [
      `${name}: brak kalorii`,
      `${name}: brak białka`,
      `${name}: brak indeksu glikemicznego`,
    ]
    fetchProducts.mockResolvedValue({
      items: [
        {
          ...product(1),
          name,
          completeness: {
            complete: false,
            has_core_macros: false,
            has_glycemic_index: false,
            missing,
          },
        },
      ],
      total: 1,
    })
    const wrapper = await mountPage()
    expect(wrapper.get('[data-testid="product-incomplete-1-toggle"]').text()).toBe(
      'Niepełne dane — szczegóły',
    )
    expect(wrapper.get('[data-testid="product-incomplete-1"]').attributes('open')).toBeUndefined()
    expect(
      wrapper.findAll('[data-testid="product-incomplete-1-messages"] li').map((row) => row.text()),
    ).toEqual(missing)
  })
  it('link widocznego produktu zachowuje wpisaną nazwę przed debounce serwera', async () => {
    const { createRouter, createMemoryHistory } =
      await vi.importActual<typeof RouterModule>('vue-router')
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/produkty', name: 'produkty', component: { template: '<div />' } },
        { path: '/produkty/nowy', name: 'produkt-nowy', component: { template: '<div />' } },
        {
          path: '/produkty/:id/edytuj',
          name: 'produkt-edycja',
          component: { template: '<div />' },
        },
      ],
    })
    navigation.query = { q: 'stare wyszukanie', category: '1', archived: '1' }
    await router.push({ name: 'produkty', query: navigation.query })
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    })
    setActivePinia(createPinia())
    const wrapper = mount(ProduktyPage, {
      global: { plugins: [router, [VueQueryPlugin, { queryClient }]] },
    })
    await flushPromises()
    const initialRequests = fetchProducts.mock.calls.length
    vi.useFakeTimers()
    try {
      await wrapper.get('[data-testid="products-search"]').setValue('  Produkt 1  ')
      const edit = wrapper.get('[data-testid="product-edit-1"]')
      const href = new URL(edit.attributes('href')!, 'https://example.invalid')
      expect(href.pathname).toBe('/produkty/1/edytuj')
      expect(Object.fromEntries(href.searchParams)).toEqual({
        q: 'Produkt 1',
        category: '1',
        archived: '1',
        pages: '1',
        focus: '1',
      })
      expect(fetchProducts).toHaveBeenCalledTimes(initialRequests)
      expect(fetchProducts).toHaveBeenLastCalledWith(
        expect.objectContaining({ q: 'stare wyszukanie' }),
      )
      await edit.trigger('click')
      await flushPromises()
      expect(router.currentRoute.value.query.q).toBe('Produkt 1')
      expect(fetchProducts).toHaveBeenCalledTimes(initialRequests)
    } finally {
      wrapper.unmount()
      queryClient.clear()
      vi.useRealTimers()
    }
  })
})
