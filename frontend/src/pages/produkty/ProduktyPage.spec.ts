import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProduktyPage from './ProduktyPage.vue'

/**
 * Paginacja katalogu (BATCH_19, ustalenie R4 P1).
 *
 * Dług, który to zamyka: strona wysyłała `offset: 0` ze stałym limitem i pisała
 * obok „Produktów: 185", renderując 50 — liczba i widok kłamały razem. Test
 * pilnuje więc DWÓCH rzeczy naraz: że licznik podaje relację widocznych do
 * wszystkich i że da się dojść do ostatniej pozycji.
 */

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {} }),
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
})
