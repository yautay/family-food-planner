import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AdminWeryfikacjaPage from './AdminWeryfikacjaPage.vue'

/**
 * Kolejka weryfikacji — najgorszy przypadek długu z R4 (P1).
 *
 * Ekran deklarował „najstarsze na górze", ale sortował po stronie KLIENTA:
 * układał po `created_at` pięćdziesiątkę, którą serwer wybrał alfabetycznie po
 * `name`. Produkt spoza pierwszych 50 nazw był stąd NIEOSIĄGALNY — a to jest
 * ekran, na którym właściciel uzupełnia wartości po imporcie jadłospisów.
 *
 * Test pilnuje więc rzeczy, której nie widać w DOM: że porządek zamawia SERWER
 * (`sort=created_at`), a strona kolejności już nie tyka.
 */

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {} }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

const { fetchProducts, verifyProduct } = vi.hoisted(() => ({
  fetchProducts: vi.fn(),
  verifyProduct: vi.fn(),
}))
vi.mock('@/api/catalog', () => ({ fetchProducts, verifyProduct }))

function product(id: number, name: string) {
  return {
    id,
    name,
    normalized_name: name.toLowerCase(),
    category_id: 1,
    category_name: 'Warzywa',
    measure_kind: 'mass' as const,
    piece_weight_g: null,
    verification_status: 'unverified' as const,
    verified_at: null,
    perishability: 'fresh' as const,
    perishability_override: null,
    is_archived: false,
    nutrition: {
      kcal_100: null,
      protein_100: null,
      fat_100: null,
      carbs_100: null,
      fiber_100: null,
      sugars_100: null,
      glycemic_index: null,
      nutrition_source: null,
    },
    completeness: {
      complete: false,
      has_core_macros: false,
      has_glycemic_index: false,
      missing: ['kcal_100'],
    },
    created_at: '2026-08-21T10:00:00Z',
    updated_at: '2026-08-21T10:00:00Z',
  }
}

const TOTAL = 60
const PAGE_SIZE = 50
/** Kolejność SERWERA (wg wieku) — nazwy celowo nie są alfabetyczne. */
const ALL = Array.from({ length: TOTAL }, (_unused, index) =>
  product(index + 1, `Produkt ${String(TOTAL - index).padStart(3, '0')}`),
)

async function mountPage() {
  setActivePinia(createPinia())
  const wrapper = mount(AdminWeryfikacjaPage, {
    global: { plugins: [VueQueryPlugin], stubs: { RouterLink: true } },
  })
  await flushPromises()
  return wrapper
}

describe('AdminWeryfikacjaPage — kolejka', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchProducts.mockImplementation(({ offset = 0, limit = PAGE_SIZE }) =>
      Promise.resolve({ items: ALL.slice(offset, offset + limit), total: TOTAL }),
    )
  })

  it('porządek zamawia serwer, nie przeglądarka', async () => {
    await mountPage()

    expect(fetchProducts).toHaveBeenCalledWith(
      expect.objectContaining({ sort: 'created_at', verification_status: 'unverified' }),
    )
  })

  it('nie przestawia kolejności zwróconej przez serwer', async () => {
    const wrapper = await mountPage()

    const names = wrapper
      .findAll('[data-testid^="verification-row-"]')
      .map((row) => row.get('p.font-medium').text())

    expect(names.slice(0, 3)).toEqual(['Produkt 060', 'Produkt 059', 'Produkt 058'])
  })

  it('licznik mówi, ile z kolejki widać, a „pokaż więcej" dowozi resztę', async () => {
    const wrapper = await mountPage()

    expect(wrapper.findAll('[data-testid^="verification-row-"]')).toHaveLength(PAGE_SIZE)
    expect(wrapper.get('[data-testid="admin-weryfikacja-page"]').text()).toContain('50 z 60')

    await wrapper.get('[data-testid="verification-load-more"]').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('[data-testid^="verification-row-"]')).toHaveLength(TOTAL)
    expect(wrapper.find('[data-testid="verification-load-more"]').exists()).toBe(false)
  })

  it('pusta kolejka nie pokazuje przycisku doładowania', async () => {
    fetchProducts.mockResolvedValue({ items: [], total: 0 })

    const wrapper = await mountPage()

    expect(wrapper.find('[data-testid="verification-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="verification-load-more"]').exists()).toBe(false)
  })
})
