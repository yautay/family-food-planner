import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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

async function mountPage() {
  setActivePinia(createPinia())
  const wrapper = mount(SpizarniaPage, { global: { plugins: [VueQueryPlugin] } })
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

    expect(wrapper.find('[data-testid="expiry-badge-soon"]').exists()).toBe(true)
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
