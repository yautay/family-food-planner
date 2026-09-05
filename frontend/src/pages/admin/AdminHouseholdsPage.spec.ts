import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AdminHouseholdsPage from './AdminHouseholdsPage.vue'

const {
  fetchHouseholds,
  fetchHousehold,
  createHousehold,
  renameHousehold,
  deleteHousehold,
  setHouseholdMembers,
  fetchUsers,
} = vi.hoisted(() => ({
  fetchHouseholds: vi.fn(),
  fetchHousehold: vi.fn(),
  createHousehold: vi.fn(),
  renameHousehold: vi.fn(),
  deleteHousehold: vi.fn(),
  setHouseholdMembers: vi.fn(),
  fetchUsers: vi.fn(),
}))

vi.mock('@/api/adminHouseholds', () => ({
  fetchHouseholds,
  fetchHousehold,
  createHousehold,
  renameHousehold,
  deleteHousehold,
  setHouseholdMembers,
}))
vi.mock('@/api/adminUsers', () => ({ fetchUsers }))

const HOUSEHOLD = {
  id: 1,
  name: 'Kowalscy',
  created_at: '2026-08-16T10:00:00Z',
  updated_at: '2026-08-16T10:00:00Z',
  members_count: 2,
  profiles_count: 0,
}
const ANNA = {
  id: 10,
  email: 'anna@example.com',
  display_name: 'Anna',
  role: 'user' as const,
  is_active: true,
}
const PIOTR = { ...ANNA, id: 11, email: 'piotr@example.com', display_name: 'Piotr' }
const NOWY = { ...ANNA, id: 12, email: 'nowy@example.com', display_name: 'Nowy' }

const DETAIL = { ...HOUSEHOLD, members: [ANNA, PIOTR], profiles: [] }

async function mountPage() {
  setActivePinia(createPinia())
  const wrapper = mount(AdminHouseholdsPage, { global: { plugins: [VueQueryPlugin] } })
  await flushPromises()
  return wrapper
}

describe('AdminHouseholdsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchHouseholds.mockResolvedValue({ items: [HOUSEHOLD], total: 1 })
    fetchHousehold.mockResolvedValue(DETAIL)
    fetchUsers.mockResolvedValue({ items: [ANNA, PIOTR, NOWY], total: 3 })
    setHouseholdMembers.mockResolvedValue(DETAIL)
  })

  it('pokazuje listę rodzin z licznikami', async () => {
    const wrapper = await mountPage()

    const row = wrapper.get('[data-testid="household-row-1"]')
    expect(row.text()).toContain('Kowalscy')
    expect(row.text()).toContain('Konta: 2')
  })

  it('pusta lista uczy, co zrobić dalej', async () => {
    fetchHouseholds.mockResolvedValue({ items: [], total: 0 })

    const wrapper = await mountPage()

    expect(wrapper.get('[data-testid="households-empty"]').text()).toContain('Utwórz pierwszą')
  })

  it('po rozwinięciu składu pokazuje członków rodziny', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="household-select-1"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="household-member-10"]').text()).toContain('anna@example.com')
    expect(wrapper.find('[data-testid="household-assign-select"]').exists()).toBe(true)
  })

  it('nie pokazuje narzędzi składu, dopóki nie zna aktualnych członków', async () => {
    // `PUT .../members` podmienia CAŁY skład — działanie na niezaładowanej
    // liście odpięłoby pozostałe konta.
    fetchHousehold.mockReturnValue(new Promise(() => {}))
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="household-select-1"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="household-assign-select"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="household-detach-10"]').exists()).toBe(false)
    expect(setHouseholdMembers).not.toHaveBeenCalled()
  })

  it('przypisanie wysyła pełny skład razem z dotychczasowymi członkami', async () => {
    const wrapper = await mountPage()
    await wrapper.get('[data-testid="household-select-1"]').trigger('click')
    await flushPromises()

    await wrapper.get('[data-testid="household-assign-select"]').setValue(NOWY.id)
    await wrapper.get('[data-testid="household-assign-submit"]').trigger('submit')
    await flushPromises()

    expect(setHouseholdMembers).toHaveBeenCalledWith(1, [ANNA.id, PIOTR.id, NOWY.id])
  })

  it('select przypisania pomija konta już należące do tej rodziny', async () => {
    const wrapper = await mountPage()
    await wrapper.get('[data-testid="household-select-1"]').trigger('click')
    await flushPromises()

    const opcje = wrapper.get('[data-testid="household-assign-select"]').text()
    expect(opcje).toContain('nowy@example.com')
    expect(opcje).not.toContain('anna@example.com')
  })

  it('odpięcie wysyła skład bez wskazanego konta', async () => {
    const wrapper = await mountPage()
    await wrapper.get('[data-testid="household-select-1"]').trigger('click')
    await flushPromises()

    await wrapper.get('[data-testid="household-detach-10"]').trigger('click')
    await flushPromises()

    expect(setHouseholdMembers).toHaveBeenCalledWith(1, [PIOTR.id])
  })

  it('blokada usunięcia pokazuje listę użyć z odpowiedzi serwera', async () => {
    const { ApiError } = await import('@/api/client')
    deleteHousehold.mockRejectedValue(
      new ApiError(409, {
        code: 'conflict',
        message: 'Rodzina ma przypisane konta.',
        details: { used_in: [{ type: 'user', id: 10, name: 'Anna' }] },
      }),
    )
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="household-delete-1"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="households-error"]').text()).toContain(
      'Rodzina ma przypisane konta.',
    )
    expect(wrapper.get('[data-testid="households-used-in"]').text()).toContain('Anna')
    confirm.mockRestore()
  })

  it('usunięcie bez potwierdzenia nie woła API', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="household-delete-1"]').trigger('click')
    await flushPromises()

    expect(deleteHousehold).not.toHaveBeenCalled()
    confirm.mockRestore()
  })

  it('tworzenie rodziny wysyła przyciętą nazwę', async () => {
    createHousehold.mockResolvedValue(DETAIL)
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="new-household-name"]').setValue('  Nowakowie  ')
    await wrapper.get('[data-testid="new-household-submit"]').trigger('submit')
    await flushPromises()

    expect(createHousehold).toHaveBeenCalledWith('Nowakowie')
  })
})

/** Paginacja listy rodzin (BATCH_19) — jeden z sześciu ekranów z ustalenia R4 P1. */
describe('AdminHouseholdsPage — paginacja', () => {
  const PAGE_SIZE = 50
  const TOTAL = 60
  const ALL = Array.from({ length: TOTAL }, (_unused, index) => ({
    ...HOUSEHOLD,
    id: index + 1,
    name: `Rodzina ${index + 1}`,
  }))

  beforeEach(() => {
    vi.clearAllMocks()
    fetchHousehold.mockResolvedValue(DETAIL)
    fetchUsers.mockResolvedValue({ items: [ANNA], total: 1 })
    fetchHouseholds.mockImplementation(({ offset = 0, limit = PAGE_SIZE }) =>
      Promise.resolve({ items: ALL.slice(offset, offset + limit), total: TOTAL }),
    )
  })

  it('pierwsza strona pokazuje limit rodzin i relację do całości', async () => {
    const wrapper = await mountPage()

    expect(wrapper.findAll('[data-testid^="household-row-"]')).toHaveLength(PAGE_SIZE)
    expect(wrapper.get('[data-testid="households-total"]').text()).toContain('50 z 60')
  })

  it('„pokaż więcej" dowozi ostatnią rodzinę', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="households-load-more"]').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('[data-testid^="household-row-"]')).toHaveLength(TOTAL)
    expect(wrapper.get(`[data-testid="household-row-${TOTAL}"]`).text()).toContain('Rodzina 60')
    expect(wrapper.find('[data-testid="households-load-more"]').exists()).toBe(false)
  })
})
