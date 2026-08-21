import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import StorePicker from './StorePicker.vue'

/**
 * `StorePicker` — create-in-context dla sklepów (06_UIUX §3.1, wymóg 05 §4).
 *
 * Trzy rzeczy, które muszą działać, żeby wzorzec miał sens: wybór istniejącego
 * sklepu, opcja „+ Dodaj sklep" dla frazy bez trafienia oraz jawna pozycja
 * „Bez sklepu" (wariant retail bez sklepu jest dozwolony).
 */

const { fetchStores, createStore } = vi.hoisted(() => ({
  fetchStores: vi.fn(),
  createStore: vi.fn(),
}))

vi.mock('@/api/stores', () => ({ fetchStores, createStore }))

function store(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    name: 'Lidl',
    color: null,
    is_archived: false,
    created_at: '2026-08-21T10:00:00Z',
    updated_at: '2026-08-21T10:00:00Z',
    ...overrides,
  }
}

async function mountPicker() {
  const wrapper = mount(StorePicker, { global: { plugins: [VueQueryPlugin] } })
  await flushPromises()
  return wrapper
}

describe('StorePicker', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchStores.mockResolvedValue({ items: [store()], total: 1 })
  })

  it('wybór sklepu z listy emituje modelValue i selected', async () => {
    const wrapper = await mountPicker()

    await wrapper.get('[data-testid="store-picker-option-1"]').trigger('click')

    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([store()])
    expect(wrapper.emitted('selected')?.[0]).toEqual([store()])
  })

  it('„Bez sklepu" emituje null — wariant bez sklepu jest dozwolony', async () => {
    const wrapper = await mountPicker()

    await wrapper.get('[data-testid="store-picker-none"]').trigger('click')

    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([null])
    expect(wrapper.emitted('selected')).toBeUndefined()
  })

  it('fraza bez trafienia pokazuje „+ Dodaj sklep" i tworzy sklep w miejscu', async () => {
    const created = store({ id: 7, name: 'Aldi' })
    createStore.mockResolvedValue(created)
    const wrapper = await mountPicker()

    await wrapper.get('[data-testid="store-picker-input"]').setValue('Aldi')
    await flushPromises()

    const createButton = wrapper.get('[data-testid="store-picker-create"]')
    expect(createButton.text()).toContain('Aldi')

    await createButton.trigger('click')
    await flushPromises()

    expect(createStore).toHaveBeenCalledWith({ name: 'Aldi' })
    // Auto-wybór: użytkownik wraca do przerwanego formularza z gotowym sklepem.
    expect(wrapper.emitted('selected')?.[0]).toEqual([created])
  })

  it('istniejący sklep nie generuje opcji „+ Dodaj"', async () => {
    const wrapper = await mountPicker()

    await wrapper.get('[data-testid="store-picker-input"]').setValue('lidl')
    await flushPromises()

    expect(wrapper.find('[data-testid="store-picker-create"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="store-picker-option-1"]').exists()).toBe(true)
  })
})
