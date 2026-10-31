import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PantryItem } from '@/api/pantry'
import { ApiError } from '@/api/client'
import SpizarniaPage from './SpizarniaPage.vue'

const { fetchPantryItems, createPantryItem, updatePantryItem, deletePantryItem, fetchCategories } =
  vi.hoisted(() => ({
    fetchPantryItems: vi.fn(),
    createPantryItem: vi.fn(),
    updatePantryItem: vi.fn(),
    deletePantryItem: vi.fn(),
    fetchCategories: vi.fn(),
  }))

vi.mock('@/api/pantry', () => ({
  fetchPantryItems,
  createPantryItem,
  updatePantryItem,
  deletePantryItem,
}))

vi.mock('@/api/catalog', () => ({ fetchCategories, fetchProducts: vi.fn() }))

function item(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    product_id: 10,
    product_name: 'Mąka pszenna',
    category_id: 5,
    category_name: 'Suche',
    measure_kind: 'mass' as const,
    retail_product_id: null,
    amount: '1500.000',
    amount_unit: 'g' as const,
    expiry_date: null,
    location: 'szafka',
    note: '',
    owner_user_id: 1,
    household_id: 1,
    created_at: '2026-08-21T10:00:00Z',
    updated_at: '2026-08-21T10:00:00Z',
    ...overrides,
  }
}

const panelStub = {
  props: ['open', 'error', 'submitDisabled', 'pending'],
  emits: ['submit', 'close'],
  template: `<div v-if="open"><slot formId="test-form" /><p data-testid="pantry-error">{{ error }}</p><button data-testid="pantry-submit" :disabled="submitDisabled || pending" @click="$emit('submit')">Zapisz</button></div>`,
}
async function mountPage() {
  setActivePinia(createPinia())
  const wrapper = mount(SpizarniaPage, {
    global: { plugins: [VueQueryPlugin], stubs: { ActionPanel: panelStub } },
  })
  await flushPromises()
  return wrapper
}

describe('SpizarniaPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    fetchCategories.mockResolvedValue({ items: [{ id: 5, name: 'Suche', position: 1 }], total: 1 })
    fetchPantryItems.mockResolvedValue({ items: [item()], total: 1 })
  })

  it('pokazuje pozycje w kolejności z serwera i formatuje ilość', async () => {
    fetchPantryItems.mockResolvedValue({
      items: [
        item({ id: 1, product_name: 'Jogurt', amount: '400.000', expiry_date: '2026-08-23' }),
        item({ id: 2, product_name: 'Mąka pszenna', amount: '1500.000', expiry_date: null }),
      ],
      total: 2,
    })

    const wrapper = await mountPage()

    // Sortowanie liczy baza (pozycje bez daty na końcu) — strona nie przestawia
    // kolejności po swojemu, bo rozjechałaby się z paginacją.
    const names = wrapper.findAll('[data-testid^="pantry-name-"]').map((element) => element.text())
    expect(names).toEqual(['Jogurt', 'Mąka pszenna'])
    expect(wrapper.get('[data-testid="pantry-amount-2"]').text()).toBe('1,5 kg')
  })

  it('wyróżnia pozycję bliską przeterminowania (AC 4)', async () => {
    // „Dziś" bierze się z zegara maszyny, więc datę liczymy względem niego —
    // inaczej test przestałby znaczyć cokolwiek po kilku dniach.
    const inThreeDays = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
    fetchPantryItems.mockResolvedValue({
      items: [item({ expiry_date: inThreeDays })],
      total: 1,
    })

    const wrapper = await mountPage()

    expect(
      wrapper.get('[data-testid="pantry-list"]').find('[data-testid="expiry-badge-soon"]').exists(),
    ).toBe(true)
  })

  it('domyślnie pyta o sortowanie po dacie ważności', async () => {
    await mountPage()

    expect(fetchPantryItems).toHaveBeenCalledWith(expect.objectContaining({ sort: 'expiry' }))
  })

  it('filtr „tylko kończące się" dokłada próg dni do zapytania', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="pantry-expiring-only"]').setValue(true)
    await flushPromises()

    expect(fetchPantryItems).toHaveBeenLastCalledWith(
      expect.objectContaining({ expires_within_days: 7 }),
    )
  })

  it('pusta spiżarnia uczy, co zrobić dalej', async () => {
    fetchPantryItems.mockResolvedValue({ items: [], total: 0 })

    const wrapper = await mountPage()

    expect(wrapper.get('[data-testid="pantry-empty"]').text()).toContain(
      'Twoja spiżarnia jest pusta.',
    )
    expect(wrapper.get('[data-testid="pantry-add-first"]').text()).toBe('Dodaj pierwszy produkt')
  })

  it('formularz nie pozwala zapisać bez produktu i ilości', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="pantry-add"]').trigger('click')

    const submit = wrapper.get('[data-testid="pantry-submit"]')
    expect(submit.attributes('disabled')).toBeDefined()

    await wrapper.get('[data-testid="pantry-amount"]').setValue('12,5')
    expect(wrapper.get('[data-testid="pantry-submit"]').attributes('disabled')).toBeDefined()
  })

  it('ujemna ilość jest odrzucana już w polu', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="pantry-add"]').trigger('click')
    await wrapper.get('[data-testid="pantry-amount"]').setValue('-5')

    expect(wrapper.get('[data-testid="pantry-amount"]').attributes('aria-invalid')).toBe('true')
    expect(wrapper.get('[data-testid="pantry-submit"]').attributes('disabled')).toBeDefined()
  })

  it('zero jest poprawną ilością (wyzerowanie zostawia pozycję)', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="pantry-add"]').trigger('click')
    await wrapper.get('[data-testid="pantry-amount"]').setValue('0')

    expect(wrapper.get('[data-testid="pantry-amount"]').attributes('aria-invalid')).toBe('false')
  })

  it('edycja pokazuje produkt tylko do odczytu i zapisuje PATCH-em', async () => {
    updatePantryItem.mockResolvedValue(item({ amount: '250.000' }))

    const wrapper = await mountPage()
    await wrapper.get('[data-testid="pantry-edit-1"]').trigger('click')

    // Zmiana produktu znaczyłaby inną pozycję, więc pickera w edycji nie ma.
    expect(wrapper.get('[data-testid="pantry-edited-product"]').text()).toContain('Mąka pszenna')
    expect(wrapper.find('[data-testid="picker-input"]').exists()).toBe(false)

    await wrapper.get('[data-testid="pantry-amount"]').setValue('250')
    await wrapper.get('[data-testid="pantry-submit"]').trigger('click')
    await flushPromises()

    expect(updatePantryItem).toHaveBeenCalledWith(1, {
      amount: '250',
      expiry_date: null,
      location: 'szafka',
      note: '',
    })
    expect(createPantryItem).not.toHaveBeenCalled()
  })

  it('„Wyzeruj" wysyła PATCH z zerem, a nie DELETE', async () => {
    updatePantryItem.mockResolvedValue(item({ amount: '0.000' }))

    const wrapper = await mountPage()
    await wrapper.get('[data-testid="pantry-zero-1"]').trigger('click')
    await flushPromises()

    expect(updatePantryItem).toHaveBeenCalledWith(1, { amount: '0' })
    expect(deletePantryItem).not.toHaveBeenCalled()
  })

  it('usunięcie pyta o potwierdzenie (destrukcja bezpieczna)', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)

    const wrapper = await mountPage()
    await wrapper.get('[data-testid="pantry-remove-1"]').trigger('click')
    await flushPromises()

    expect(confirm).toHaveBeenCalled()
    expect(deletePantryItem).not.toHaveBeenCalled()
    confirm.mockRestore()
  })

  it('przełącznik widoku podmienia listę na wiersze', async () => {
    const wrapper = await mountPage()

    expect(wrapper.find('[data-testid="pantry-card-1"]').exists()).toBe(true)

    await wrapper.get('[data-testid="pantry-view-list"]').trigger('click')

    expect(wrapper.find('[data-testid="pantry-row-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="pantry-card-1"]').exists()).toBe(false)
  })
})

/**
 * Paginacja spiżarni (BATCH_19). Strona jest tu WIĘKSZA niż domyślne 50
 * (`PAGE_SIZE` = 100): spiżarnia to inwentarz przeglądany „ile mam czego",
 * a nie przeszukiwany katalog — zmniejszenie strony dołożyłoby kliknięć
 * tam, gdzie ich dziś nie ma (06_UIUX §2).
 */
describe('SpizarniaPage — paginacja', () => {
  const PAGE_SIZE = 100
  const TOTAL = 130
  const ALL = Array.from({ length: TOTAL }, (_unused, index) =>
    item({ id: index + 1, product_id: index + 1 }),
  )

  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    fetchCategories.mockResolvedValue({ items: [{ id: 5, name: 'Suche', position: 1 }], total: 1 })
    fetchPantryItems.mockImplementation(({ offset = 0, limit = PAGE_SIZE }) =>
      Promise.resolve({ items: ALL.slice(offset, offset + limit), total: TOTAL }),
    )
  })

  it('pierwsza strona pokazuje sto pozycji i relację do całości', async () => {
    const wrapper = await mountPage()

    expect(wrapper.findAll('[data-testid^="pantry-card-"]')).toHaveLength(PAGE_SIZE)
    expect(wrapper.get('[data-testid="pantry-total"]').text()).toContain('100 z 130')
  })

  it('„pokaż więcej" dowozi resztę spiżarni', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="pantry-load-more"]').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('[data-testid^="pantry-card-"]')).toHaveLength(TOTAL)
    expect(fetchPantryItems).toHaveBeenCalledWith(
      expect.objectContaining({ limit: PAGE_SIZE, offset: PAGE_SIZE }),
    )
    expect(wrapper.find('[data-testid="pantry-load-more"]').exists()).toBe(false)
  })

  it('zbiór mieszczący się na stronie nie dostaje przycisku', async () => {
    fetchPantryItems.mockResolvedValue({ items: [item()], total: 1 })

    const wrapper = await mountPage()

    expect(wrapper.find('[data-testid="pantry-load-more"]').exists()).toBe(false)
  })
})

const api = { fetchPantryItems, createPantryItem, updatePantryItem, deletePantryItem }
const all: PantryItem[] = Array.from({ length: 105 }, (_, i) => ({
  id: i + 1,
  product_id: 1,
  product_name: `Długa nazwa produktu ${i + 1}`,
  category_name: 'Warzywa',
  category_id: 1,
  measure_kind: 'mass',
  amount: '1500.000',
  amount_unit: 'g',
  expiry_date: null,
  location: 'szafka',
  note: '',
  retail_product_id: null,
  owner_user_id: 1,
  household_id: null,
  created_at: '2026-10-31T10:00:00Z',
  updated_at: '2026-10-31T10:00:00Z',
}))
async function render() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = mount(SpizarniaPage, {
    global: {
      plugins: [createPinia(), [VueQueryPlugin, { queryClient: client }]],
      stubs: {
        ProductPicker: true,
        ActionPanel: panelStub,
      },
    },
  })
  await flushPromises()
  return { wrapper, client }
}
describe('Spiżarnia — rzeczywisty filtr i zachowanie miejsca', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    fetchCategories.mockResolvedValue({ items: [{ id: 1, name: 'Warzywa' }], total: 1 })
    api.fetchPantryItems.mockImplementation(({ limit, offset = 0 }) =>
      Promise.resolve({
        items:
          limit === 3
            ? [{ ...all[0], expiry_date: '2026-10-31' }]
            : all.slice(offset, offset + limit),
        total: limit === 3 ? 200 : 105,
      }),
    )
    api.updatePantryItem.mockResolvedValue(all[104])
  })
  it('podgląd korzysta z serwerowego filtra i nie udaje globalnego licznika', async () => {
    const { wrapper } = await render()
    expect(api.fetchPantryItems).toHaveBeenCalledWith(
      expect.objectContaining({ limit: 3, offset: 0, sort: 'expiry', expires_within_days: 7 }),
    )
    const urgent = wrapper.get('[data-testid="pantry-use-first"]')
    expect(urgent.text()).toContain('Wycinek partii')
    expect(urgent.text()).not.toContain('200')
    await wrapper.get('[data-testid="pantry-show-expiring"]').trigger('click')
    await flushPromises()
    expect(api.fetchPantryItems).toHaveBeenCalledWith(
      expect.objectContaining({ limit: 100, expires_within_days: 7 }),
    )
  })
  it('edycja ilości 0,25 pozostawia filtr, widok i wszystkie wczytane strony', async () => {
    const { wrapper } = await render()
    await wrapper.get('[data-testid="pantry-category-filter"]').setValue('1')
    await wrapper.get('[data-testid="pantry-view-list"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="pantry-load-more"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="pantry-edit-105"]').trigger('click')
    await wrapper.get('[data-testid="pantry-amount"]').setValue('0,25')
    await wrapper.get('[data-testid="pantry-submit"]').trigger('click')
    await flushPromises()
    expect(api.updatePantryItem).toHaveBeenCalledWith(
      105,
      expect.objectContaining({ amount: '0.25' }),
    )
    expect(wrapper.findAll('[data-testid^="pantry-row-"]')).toHaveLength(105)
    expect(wrapper.get('[data-testid="pantry-category-filter"]').element).toHaveProperty(
      'value',
      '1',
    )
    expect(wrapper.get('[data-testid="pantry-view-list"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.find('[data-testid="pantry-form"]').exists()).toBe(false)
    expect(api.fetchPantryItems).toHaveBeenCalledWith(
      expect.objectContaining({ offset: 100, category_id: 1 }),
    )
    expect(wrapper.get('[data-testid="pantry-saved"]').text()).toBe('Zapas zapisany.')
  })
  it('odmowa zapisu zachowuje szkic i zapasy', async () => {
    api.updatePantryItem.mockRejectedValue(
      new ApiError(422, { code: 'validation_error', message: 'Popraw ilość.', details: {} }),
    )
    const { wrapper } = await render()
    await wrapper.get('[data-testid="pantry-edit-1"]').trigger('click')
    await wrapper.get('[data-testid="pantry-amount"]').setValue('0,25')
    await wrapper.get('[data-testid="pantry-submit"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="pantry-error"]').text()).toContain('Popraw ilość.')
    expect(wrapper.get('[data-testid="pantry-amount"]').element).toHaveProperty('value', '0,25')
    expect(wrapper.findAll('[data-testid^="pantry-card-"]')).toHaveLength(100)
    expect(wrapper.find('[data-testid="pantry-saved"]').exists()).toBe(false)
  })
  it('błąd odświeżenia pokazuje zapisane dane i ponowienie', async () => {
    const { wrapper, client } = await render()
    api.fetchPantryItems.mockRejectedValue(new Error('brak sieci'))
    await client.invalidateQueries()
    await flushPromises()
    expect(wrapper.findAll('[data-testid^="pantry-card-"]')).toHaveLength(100)
    expect(wrapper.text()).toContain('Pokazujemy ostatnio pobrane dane.')
    expect(wrapper.find('[data-testid="pantry-empty"]').exists()).toBe(false)
  })
  it('zerowa ilość w wycinku nie jest rekomendowana ani uznana za brak zapasów całego domu', async () => {
    api.fetchPantryItems.mockImplementation(({ limit, offset = 0 }) =>
      Promise.resolve({
        items:
          limit === 3
            ? [{ ...all[0], amount: '0.000', expiry_date: '2026-10-31' }]
            : all.slice(offset, offset + limit),
        total: limit === 3 ? 200 : 105,
      }),
    )
    const { wrapper } = await render()
    const preview = wrapper.get('[data-testid="pantry-use-first"]')
    expect(preview.find('[data-testid="pantry-urgent-1"]').exists()).toBe(false)
    expect(preview.text()).toContain('W pobranym wycinku')
    expect(preview.find('[data-testid="pantry-show-expiring"]').exists()).toBe(true)
  })
})
