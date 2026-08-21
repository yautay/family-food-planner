import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ZakupyPage from './ZakupyPage.vue'

/**
 * Trzy rzeczy z Acceptance Criteria karty B10, których nie da się sprawdzić
 * inaczej niż na zmontowanym komponencie:
 *
 * - checkbox „Uwzględnić stan domowy?" jest DOMYŚLNIE ODZNACZONY (AC 3),
 * - `POST /generate` dostaje `use_pantry` dokładnie takie, jakie zaznaczył
 *   użytkownik — nigdy „na wszelki wypadek" prawdziwe,
 * - nierozstrzygnięty bloker DEZAKTYWUJE przycisk „Utwórz listy" (AC 6).
 */
const {
  fetchRoundConfigs,
  createRoundConfig,
  updateRoundConfig,
  deleteRoundConfig,
  generateShopping,
  fetchGeneration,
  resolveGeneration,
  finalizeGeneration,
  discardGeneration,
} = vi.hoisted(() => ({
  fetchRoundConfigs: vi.fn(),
  createRoundConfig: vi.fn(),
  updateRoundConfig: vi.fn(),
  deleteRoundConfig: vi.fn(),
  generateShopping: vi.fn(),
  fetchGeneration: vi.fn(),
  resolveGeneration: vi.fn(),
  finalizeGeneration: vi.fn(),
  discardGeneration: vi.fn(),
}))

vi.mock('@/api/shopping', () => ({
  fetchRoundConfigs,
  createRoundConfig,
  updateRoundConfig,
  deleteRoundConfig,
  generateShopping,
  fetchGeneration,
  resolveGeneration,
  finalizeGeneration,
  discardGeneration,
}))

vi.mock('@/api/retail', () => ({ createRetailProduct: vi.fn(), fetchRetailProducts: vi.fn() }))
vi.mock('@/api/catalog', () => ({ fetchProduct: vi.fn(), fetchCategories: vi.fn() }))
vi.mock('@/api/stores', () => ({ fetchStores: vi.fn() }))

function roundConfig(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    name: 'Niedziela',
    shopping_weekday: 6,
    covers_days: 7,
    fresh_days: 4,
    mode: 'durable_plus_fresh_window' as const,
    position: 0,
    scope: 'private' as const,
    owner_user_id: 1,
    household_id: null,
    created_at: '2026-08-21T10:00:00Z',
    updated_at: '2026-08-21T10:00:00Z',
    ...overrides,
  }
}

function line(overrides: Record<string, unknown> = {}) {
  return {
    round_key: 'cfg-1',
    product_id: 10,
    label: 'Mąka 1 kg',
    amount_unit: 'g' as const,
    needed_amount: '1400.000',
    raw_amount: '1400.000',
    category_id: 5,
    category_name: 'Sypkie',
    perishability: 'durable' as const,
    days: ['2030-01-07'],
    from_pantry_amount: null,
    already_have: false,
    retail_product_id: 100,
    retail_label: 'Mąka 1 kg',
    package_amount: '1000.00',
    packages_count: 2,
    leftover_amount: '600.000',
    retail_options: [
      {
        retail_product_id: 100,
        label: 'Mąka 1 kg',
        package_amount: '1000.00',
        package_unit: 'g' as const,
        store_id: null,
        store_name: null,
      },
    ],
    ...overrides,
  }
}

function generation(overrides: Record<string, unknown> = {}) {
  return {
    id: 7,
    date_from: '2030-01-07',
    date_to: '2030-01-13',
    use_pantry: false,
    status: 'preview' as const,
    scope: 'private' as const,
    owner_user_id: 1,
    household_id: null,
    rounds: [
      {
        key: 'cfg-1',
        name: 'Niedziela',
        mode: 'durable_plus_fresh_window' as const,
        shopping_weekday: 6,
        shopping_date: '2030-01-06',
        date_from: '2030-01-07',
        date_to: '2030-01-13',
        items: [line()],
      },
    ],
    issues: [],
    retail_choices: [],
    has_blockers: false,
    created_at: '2026-08-21T10:00:00Z',
    updated_at: '2026-08-21T10:00:00Z',
    ...overrides,
  }
}

/**
 * Podgląd jest stanem SERWERA: strona wkłada odpowiedź `generate` do cache,
 * a `useQuery` i tak pyta `GET /generations/{id}`. Oba mocki muszą więc zwracać
 * to samo — inaczej test mierzyłby rozjazd mocków, nie zachowanie komponentu.
 */
function useGeneration(value: ReturnType<typeof generation>): void {
  generateShopping.mockResolvedValue(value)
  fetchGeneration.mockResolvedValue(value)
}

async function mountPage() {
  setActivePinia(createPinia())
  const wrapper = mount(ZakupyPage, { global: { plugins: [VueQueryPlugin] } })
  await flushPromises()
  return wrapper
}

describe('ZakupyPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchRoundConfigs.mockResolvedValue({ items: [roundConfig()], total: 1 })
    useGeneration(generation())
  })

  it('checkbox spiżarni jest domyślnie ODZNACZONY (AC 3, 02_DOMAIN §8)', async () => {
    const wrapper = await mountPage()

    const checkbox = wrapper.get('[data-testid="zakupy-use-pantry"]').element as HTMLInputElement
    expect(checkbox.checked).toBe(false)
  })

  it('generacja wysyła use_pantry dokładnie takie, jakie zaznaczył użytkownik', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="zakupy-generate"]').trigger('click')
    await flushPromises()
    expect(generateShopping).toHaveBeenLastCalledWith(
      expect.objectContaining({ use_pantry: false }),
    )

    await wrapper.get('[data-testid="zakupy-use-pantry"]').setValue(true)
    await wrapper.get('[data-testid="zakupy-generate"]').trigger('click')
    await flushPromises()
    expect(generateShopping).toHaveBeenLastCalledWith(expect.objectContaining({ use_pantry: true }))
  })

  it('podgląd pokazuje potrzebę, opakowania i resztkę', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="zakupy-generate"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="preview-needed-10"]').text()).toContain('1,4 kg')
    expect(wrapper.get('[data-testid="preview-packages-10"]').text()).toContain('2 ×')
    expect(wrapper.get('[data-testid="leftover-badge"]').text()).toBe('Zostanie: 600 g')
  })

  it('bloker dezaktywuje „Utwórz listy" i mówi dlaczego (AC 6)', async () => {
    useGeneration(
      generation({
        has_blockers: true,
        issues: [
          {
            key: 'product_without_category:product:10',
            kind: 'product_without_category' as const,
            severity: 'blocker' as const,
            message: 'Produkt „Mąka" nie ma kategorii.',
            dismissed: false,
            product_id: 10,
            plan_item_id: null,
            pantry_item_id: null,
          },
        ],
      }),
    )
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="zakupy-generate"]').trigger('click')
    await flushPromises()

    const button = wrapper.get('[data-testid="preview-finalize"]').element as HTMLButtonElement
    expect(button.disabled).toBe(true)
    expect(wrapper.get('[data-testid="preview-blocked"]').text()).toContain('rozstrzygnij')
    expect(wrapper.get('[data-testid="preview-issue-product_without_category"]').text()).toContain(
      'Bloker',
    )
  })

  it('ostrzeżenie NIE blokuje finalizacji (brak retail to podpowiedź, nie bloker)', async () => {
    useGeneration(
      generation({
        issues: [
          {
            key: 'missing_retail:product:10',
            kind: 'missing_retail' as const,
            severity: 'warning' as const,
            message: '„Mąka" nie ma produktu sklepowego.',
            dismissed: false,
            product_id: 10,
            plan_item_id: null,
            pantry_item_id: null,
          },
        ],
      }),
    )
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="zakupy-generate"]').trigger('click')
    await flushPromises()

    const button = wrapper.get('[data-testid="preview-finalize"]').element as HTMLButtonElement
    expect(button.disabled).toBe(false)
    expect(wrapper.find('[data-testid="preview-blocked"]').exists()).toBe(false)
  })

  it('toggle „mam już w domu" wysyła PEŁNY zbiór zaznaczeń', async () => {
    resolveGeneration.mockResolvedValue(
      generation({
        rounds: [{ ...generation().rounds[0], items: [line({ already_have: true })] }],
      }),
    )
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="zakupy-generate"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="preview-toggle-have-10"]').trigger('change')
    await flushPromises()

    expect(resolveGeneration).toHaveBeenCalledWith(7, { already_have: [10] })
    expect(wrapper.get('[data-testid="preview-already-have-10"]').text()).toContain('Mam w domu')
  })

  it('panel odjęć ze spiżarni pojawia się TYLKO przy use_pantry', async () => {
    const wrapper = await mountPage()
    await wrapper.get('[data-testid="zakupy-generate"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="preview-pantry-panel"]').exists()).toBe(false)

    useGeneration(
      generation({
        id: 8,
        use_pantry: true,
        rounds: [
          {
            ...generation().rounds[0],
            items: [line({ from_pantry_amount: '400.000', needed_amount: '1000.000' })],
          },
        ],
      }),
    )
    await wrapper.get('[data-testid="zakupy-use-pantry"]').setValue(true)
    await wrapper.get('[data-testid="zakupy-generate"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="preview-pantry-panel"]').text()).toContain('400 g')
    expect(wrapper.get('[data-testid="preview-from-pantry-10"]').text()).toContain('400 g')
  })

  it('finalizacja pokazuje utworzone listy z linkiem do strony listy', async () => {
    finalizeGeneration.mockResolvedValue({
      items: [
        {
          id: 42,
          generation_id: 7,
          name: 'Zakupy 07.01-13.01.2030',
          round_name: 'Niedziela',
          store_id: null,
          expires_at: '2030-01-14T10:00:00Z',
          items: [{ id: 1 }],
        },
      ],
      total: 1,
    })
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="zakupy-generate"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="preview-finalize"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="created-list-42"]').text()).toContain('Niedziela')
    expect(wrapper.get('[data-testid="created-list-42"]').text()).toContain('1 poz.')
  })

  it('sekcja tur pokazuje konfigurację z backendu', async () => {
    const wrapper = await mountPage()

    const row = wrapper.get('[data-testid="round-config-1"]')
    expect(row.text()).toContain('Niedziela')
    expect(row.text()).toContain('niedziela')
    expect(row.text()).toContain('Trwałe + okno świeżych')
  })
})
