import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, type LocationQueryRaw, type Router } from 'vue-router'

import { ApiError } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import { useShoppingDraftStore } from '@/stores/shoppingDraft'

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
  fetchShoppingLists,
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
  fetchShoppingLists: vi.fn(),
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
vi.mock('@/api/shoppingLists', () => ({ fetchShoppingLists }))

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

let queryClient: QueryClient
let router: Router
const wrappers: ReturnType<typeof mount>[] = []
async function mountPage(query: LocationQueryRaw = {}) {
  setActivePinia(createPinia())
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/zakupy', name: 'zakupy', component: ZakupyPage },
      { path: '/zakupy/:id', name: 'zakupy-lista', component: { template: '<div />' } },
    ],
  })
  await router.push({ name: 'zakupy', query })
  await router.isReady()
  const wrapper = mount(ZakupyPage, {
    attachTo: document.body,
    global: { plugins: [router, [VueQueryPlugin, { queryClient }]] },
  })
  wrappers.push(wrapper)
  await flushPromises()
  return wrapper
}

describe('ZakupyPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchShoppingLists.mockResolvedValue({ items: [], total: 0 })
    fetchRoundConfigs.mockResolvedValue({ items: [roundConfig()], total: 1 })
    useGeneration(generation())
  })
  afterEach(() => {
    wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
    queryClient?.clear()
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

  it.each([
    new ApiError(422, {
      code: 'invalid',
      message: 'Nie udało się przygotować nowego podglądu.',
      details: {},
    }),
    new Error('offline'),
  ])(
    'sukces A znika przy rozpoczęciu generacji B i nie wraca po jej błędzie: %s',
    async (error) => {
      const wrapper = await mountPage({ from: '2030-01-07', to: '2030-01-13' })
      await wrapper.get('[data-testid="zakupy-form"]').trigger('submit')
      await flushPromises()
      finalizeGeneration.mockResolvedValue({
        items: [{ id: 42, name: 'Zapisana lista A', round_name: 'Niedziela', items: [] }],
        total: 1,
      })
      fetchShoppingLists.mockResolvedValue({
        items: [
          {
            id: 42,
            generation_id: 7,
            name: 'Zapisana lista A',
            round_name: 'Niedziela',
            store_id: null,
            store_name: null,
            expires_at: '2030-01-14T10:00:00Z',
            items_total: 1,
            items_checked: 0,
            share: null,
            created_at: '2030-01-07T10:00:00Z',
          },
        ],
        total: 1,
      })
      await wrapper.get('[data-testid="preview-finalize"]').trigger('click')
      await flushPromises()
      expect(wrapper.find('[data-testid="zakupy-created-lists"]').exists()).toBe(true)
      expect(wrapper.get('[data-testid="shopping-list-42"]').text()).toContain('Zapisana lista A')

      await wrapper.get('[data-testid="zakupy-date-from"]').setValue('2035-02-01')
      await wrapper.get('[data-testid="zakupy-date-to"]').setValue('2035-02-07')
      await wrapper.get('[data-testid="zakupy-use-pantry"]').setValue(true)
      let fail!: (reason: unknown) => void
      generateShopping.mockReturnValueOnce(
        new Promise((_resolve, reject) => {
          fail = reject
        }),
      )
      await wrapper.get('[data-testid="zakupy-form"]').trigger('submit')
      await flushPromises()
      expect(wrapper.get('[data-testid="zakupy-generate"]').attributes('disabled')).toBeDefined()
      expect(wrapper.find('[data-testid="zakupy-created-lists"]').exists()).toBe(false)
      expect(wrapper.find('[data-testid="zakupy-preview"]').exists()).toBe(false)
      expect(wrapper.get('[data-testid="shopping-list-42"]').text()).toContain('Zapisana lista A')

      fail(error)
      await flushPromises()
      expect(wrapper.find('[data-testid="zakupy-error"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="zakupy-created-lists"]').exists()).toBe(false)
      expect(wrapper.get('[data-testid="shopping-list-42"]').text()).toContain('Zapisana lista A')
      expect([useShoppingDraftStore().dateFrom, useShoppingDraftStore().dateTo]).toEqual([
        '2035-02-01',
        '2035-02-07',
      ])
      expect(useShoppingDraftStore().usePantry).toBe(true)
      expect(finalizeGeneration).toHaveBeenCalledTimes(1)
    },
  )

  it('przejmuje zakres Planu także bez remountu; selectedDate go nie zastępuje i nic nie generuje', async () => {
    const wrapper = await mountPage({
      from: '2035-02-01',
      to: '2035-02-07',
      selectedDate: '2035-02-03',
    })
    expect(
      (wrapper.get('[data-testid="zakupy-date-from"]').element as HTMLInputElement).value,
    ).toBe('2035-02-01')
    expect((wrapper.get('[data-testid="zakupy-date-to"]').element as HTMLInputElement).value).toBe(
      '2035-02-07',
    )
    await wrapper.get('[data-testid="zakupy-use-pantry"]').setValue(true)
    await router.replace({ name: 'zakupy', query: { from: '2035-03-01', to: '2035-03-02' } })
    await flushPromises()
    expect(useShoppingDraftStore().dateFrom).toBe('2035-03-01')
    expect(useShoppingDraftStore().dateTo).toBe('2035-03-02')
    expect(useShoppingDraftStore().usePantry).toBe(false)
    expect(generateShopping).not.toHaveBeenCalled()
    await wrapper.get('[data-testid="zakupy-form"]').trigger('submit')
    await flushPromises()
    expect(generateShopping).toHaveBeenCalledWith(
      expect.objectContaining({
        date_from: '2035-03-01',
        date_to: '2035-03-02',
        use_pantry: false,
      }),
    )
  })

  it.each([
    { from: '2035-03-01' },
    { from: '2035-02-30', to: '2035-03-07' },
    { from: ['2035-03-01', '2035-03-02'], to: '2035-03-07' },
    { from: '2035-03-07', to: '2035-03-01' },
    { from: '2035-01-01', to: '2035-04-03' },
  ])('nie zastępuje szkicu błędnym query %j', async (query) => {
    await mountPage({ from: '2035-03-01', to: '2035-03-07' })
    const draft = useShoppingDraftStore()
    draft.usePantry = true
    await router.replace({ name: 'zakupy', query })
    expect(draft.dateFrom).toBe('2035-03-01')
    expect(draft.dateTo).toBe('2035-03-07')
    expect(draft.usePantry).toBe(true)
    expect(generateShopping).not.toHaveBeenCalled()
  })

  it('zgoda na spiżarnię nie przechodzi automatycznie do kolejnej generacji', async () => {
    const wrapper = await mountPage()
    await wrapper.get('[data-testid="zakupy-use-pantry"]').setValue(true)
    await wrapper.get('[data-testid="zakupy-form"]').trigger('submit')
    await flushPromises()
    expect(generateShopping).toHaveBeenLastCalledWith(expect.objectContaining({ use_pantry: true }))
    expect(useShoppingDraftStore().usePantry).toBe(false)
    await wrapper.get('[data-testid="zakupy-form"]').trigger('submit')
    await flushPromises()
    expect(generateShopping).toHaveBeenLastCalledWith(
      expect.objectContaining({ use_pantry: false }),
    )
  })

  it('błąd kolejnego podglądu zachowuje poprzedni podgląd, zakres i zgodę do ponowienia', async () => {
    const wrapper = await mountPage({ from: '2030-01-07', to: '2030-01-13' })
    await wrapper.get('[data-testid="zakupy-form"]').trigger('submit')
    await flushPromises()
    generateShopping.mockRejectedValue(
      new ApiError(422, {
        code: 'invalid',
        message: 'Nie udało się przygotować podglądu.',
        details: {},
      }),
    )
    await wrapper.get('[data-testid="zakupy-use-pantry"]').setValue(true)
    await wrapper.get('[data-testid="zakupy-form"]').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[data-testid="zakupy-error"]').text()).toContain('Nie udało')
    expect(wrapper.get('[data-testid="preview-needed-10"]').text()).toContain('1,4 kg')
    expect(useShoppingDraftStore().dateFrom).toBe('2030-01-07')
    expect(useShoppingDraftStore().usePantry).toBe(true)
  })

  it('błąd finalizacji zachowuje podgląd i nie pokazuje sukcesu ani invalidacji katalogu', async () => {
    const wrapper = await mountPage({ from: '2030-01-07', to: '2030-01-13' })
    await wrapper.get('[data-testid="zakupy-form"]').trigger('submit')
    await flushPromises()
    const invalidation = vi.spyOn(queryClient, 'invalidateQueries')
    finalizeGeneration.mockRejectedValue(
      new ApiError(409, { code: 'conflict', message: 'Najpierw rozstrzygnij braki.', details: {} }),
    )
    await wrapper.get('[data-testid="preview-finalize"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="preview-error"]').text()).toContain('rozstrzygnij')
    expect(wrapper.find('[data-testid="zakupy-created-lists"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="preview-needed-10"]').text()).toContain('1,4 kg')
    expect(useShoppingDraftStore().generationId).toBe(7)
    expect(useShoppingDraftStore().dateFrom).toBe('2030-01-07')
    expect(invalidation).not.toHaveBeenCalled()
  })

  it('pending blokuje podwójne utworzenie, a sukces pokazuje wszystkie tury i odświeża indeks', async () => {
    let finish!: (value: unknown) => void
    finalizeGeneration.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve
      }),
    )
    const wrapper = await mountPage()
    await wrapper.get('[data-testid="zakupy-form"]').trigger('submit')
    await flushPromises()
    const invalidation = vi.spyOn(queryClient, 'invalidateQueries')
    await wrapper.get('[data-testid="preview-finalize"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="preview-finalize"]').attributes('disabled')).toBeDefined()
    expect(
      wrapper.get('[data-testid="preview-toggle-have-10"]').attributes('disabled'),
    ).toBeDefined()
    expect(wrapper.find('[data-testid="zakupy-created-lists"]').exists()).toBe(false)
    finish({
      items: [42, 43].map((id) => ({
        id,
        name: `Lista ${id}`,
        round_name: `Tura ${id}`,
        items: [],
      })),
      total: 2,
    })
    await flushPromises()
    expect(wrapper.get('[data-testid="created-list-link-42"]').attributes('href')).toBe(
      '/zakupy/42',
    )
    expect(wrapper.get('[data-testid="created-list-link-43"]').attributes('href')).toBe(
      '/zakupy/43',
    )
    expect(invalidation).toHaveBeenCalledWith({ queryKey: queryKeys.shopping.listsIndex })
    expect(fetchShoppingLists).toHaveBeenCalledTimes(2)
    expect(useShoppingDraftStore().generationId).toBeNull()
    expect(useShoppingDraftStore().usePantry).toBe(false)
  })

  it('bez tur pokazuje drogę utworzenia pierwszej i nie wysyła generacji', async () => {
    fetchRoundConfigs.mockResolvedValue({ items: [], total: 0 })
    const wrapper = await mountPage()
    expect(wrapper.get('[data-testid="zakupy-no-rounds"]').text()).toContain('pierwszą turę')
    expect(wrapper.get('[data-testid="zakupy-round-settings"]').attributes('open')).toBeDefined()
    expect(wrapper.get('[data-testid="zakupy-generate"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="round-configs-empty"] button').trigger('click')
    expect(wrapper.find('[data-testid="round-form"]').exists()).toBe(true)
    await wrapper.get('[data-testid="zakupy-form"]').trigger('submit')
    expect(generateShopping).not.toHaveBeenCalled()
  })

  it('błąd pobrania tur nie jest pustą konfiguracją i można go ponowić bez utraty zakresu', async () => {
    fetchRoundConfigs.mockRejectedValue(new Error('offline'))
    const wrapper = await mountPage({ from: '2035-01-01', to: '2035-01-07' })
    expect(wrapper.find('[data-testid="round-configs-empty"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="zakupy-generate"]').attributes('disabled')).toBeDefined()
    fetchRoundConfigs.mockResolvedValue({ items: [roundConfig()], total: 1 })
    await queryClient.invalidateQueries({ queryKey: queryKeys.shopping.roundConfigs })
    await flushPromises()
    expect(wrapper.get('[data-testid="zakupy-generate"]').attributes('disabled')).toBeUndefined()
    expect(useShoppingDraftStore().dateFrom).toBe('2035-01-01')
    expect(generateShopping).not.toHaveBeenCalled()
  })

  it('tworzy pierwszą turę i odświeża wspólną konfigurację, pozostawiając generator gotowy', async () => {
    fetchRoundConfigs.mockResolvedValue({ items: [], total: 0 })
    const wrapper = await mountPage()
    await wrapper.get('[data-testid="round-configs-empty"] button').trigger('click')
    await wrapper.get('[data-testid="round-name"]').setValue('Pierwsze zakupy')
    createRoundConfig.mockResolvedValue(roundConfig({ name: 'Pierwsze zakupy' }))
    fetchRoundConfigs.mockResolvedValue({
      items: [roundConfig({ name: 'Pierwsze zakupy' })],
      total: 1,
    })
    await wrapper.get('[data-testid="round-form"]').trigger('submit')
    await flushPromises()
    expect(createRoundConfig).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Pierwsze zakupy' }),
    )
    expect(wrapper.get('[data-testid="round-config-1"]').text()).toContain('Pierwsze zakupy')
    expect(wrapper.get('[data-testid="zakupy-generate"]').attributes('disabled')).toBeUndefined()
    expect(generateShopping).not.toHaveBeenCalled()
  })

  it('pending podglądu blokuje ponowny submit i nie pokazuje przedwczesnego sukcesu', async () => {
    let finish!: (value: ReturnType<typeof generation>) => void
    generateShopping.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve
      }),
    )
    const wrapper = await mountPage()
    await wrapper.get('[data-testid="zakupy-form"]').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[data-testid="zakupy-generate"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="zakupy-use-pantry"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="zakupy-form"]').trigger('submit')
    expect(generateShopping).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-testid="zakupy-preview"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="zakupy-created-lists"]').exists()).toBe(false)
    finish(generation())
    await flushPromises()
    expect(wrapper.find('[data-testid="zakupy-preview"]').exists()).toBe(true)
  })

  it('wysyła jawny wybór tur, a domyślnie korzysta ze wszystkich', async () => {
    fetchRoundConfigs.mockResolvedValue({
      items: [roundConfig(), roundConfig({ id: 2, name: 'Świeże' })],
      total: 2,
    })
    const wrapper = await mountPage()
    expect(useShoppingDraftStore().roundConfigIds).toBeNull()
    await wrapper.get('[data-testid="round-selection-all"]').setValue(false)
    await wrapper.get('[data-testid="round-selection-1"]').setValue(false)
    await wrapper.get('[data-testid="zakupy-form"]').trigger('submit')
    await flushPromises()
    expect(generateShopping).toHaveBeenLastCalledWith(
      expect.objectContaining({ round_config_ids: [2] }),
    )
  })

  it('wybór opakowania zachowuje pozostałe jawne decyzje i pokazuje sklep wariantu', async () => {
    const baseLine = line()
    const choice = { product_id: 11, retail_product_id: 200 }
    const value = generation({
      retail_choices: [choice],
      rounds: [
        {
          ...generation().rounds[0],
          items: [
            line({
              retail_options: [
                ...baseLine.retail_options,
                {
                  ...baseLine.retail_options[0],
                  retail_product_id: 101,
                  label: 'Mąka 2 kg',
                  store_name: 'Zielony sklep',
                  package_amount: '2000.00',
                },
              ],
            }),
          ],
        },
      ],
    })
    useGeneration(value)
    resolveGeneration.mockResolvedValue(value)
    const wrapper = await mountPage()
    await wrapper.get('[data-testid="zakupy-form"]').trigger('submit')
    await flushPromises()
    const select = wrapper.get('[data-testid="preview-retail-select-10"]')
    expect(select.text()).toContain('Zielony sklep')
    await select.setValue('101')
    await flushPromises()
    expect(resolveGeneration).toHaveBeenCalledWith(7, {
      retail_choices: [choice, { product_id: 10, retail_product_id: 101 }],
    })
  })

  it('błąd rozstrzygnięcia zachowuje podgląd i pozwala ponowić decyzję', async () => {
    const wrapper = await mountPage()
    await wrapper.get('[data-testid="zakupy-form"]').trigger('submit')
    await flushPromises()
    resolveGeneration.mockRejectedValue(
      new ApiError(422, {
        code: 'invalid',
        message: 'Nie udało się zapisać decyzji.',
        details: {},
      }),
    )
    await wrapper.get('[data-testid="preview-toggle-have-10"]').trigger('change')
    await flushPromises()
    expect(wrapper.get('[data-testid="preview-error"]').text()).toContain('zapisać decyzji')
    expect(wrapper.get('[data-testid="preview-needed-10"]').text()).toContain('1,4 kg')
    expect(wrapper.get('[data-testid="preview-finalize"]').attributes('disabled')).toBeUndefined()
  })
})
