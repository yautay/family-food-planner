import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { queryKeys } from '@/api/queryKeys'
import type { RoundConfig } from '@/api/shopping'
import RoundConfigSection from './RoundConfigSection.vue'

const api = vi.hoisted(() => ({
  fetchRoundConfigs: vi.fn(),
  createRoundConfig: vi.fn(),
  updateRoundConfig: vi.fn(),
  deleteRoundConfig: vi.fn(),
}))
vi.mock('@/api/shopping', () => api)

function rounds(count: number): RoundConfig[] {
  return Array.from({ length: count }, (_, position) => ({
    id: position + 101,
    name: `Tura ${position + 1}`,
    shopping_weekday: null,
    covers_days: 7,
    fresh_days: 4,
    mode: 'durable_plus_fresh_window',
    position,
    scope: 'household',
    owner_user_id: 1,
    household_id: 1,
    created_at: '',
    updated_at: '',
  }))
}

const disposers: (() => void)[] = []
async function render(items: RoundConfig[]) {
  api.fetchRoundConfigs.mockResolvedValue({ items, total: items.length })
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = mount(RoundConfigSection, {
    global: { plugins: [[VueQueryPlugin, { queryClient: client }]] },
  })
  disposers.push(() => {
    wrapper.unmount()
    client.clear()
  })
  await flushPromises()
  return { wrapper, client }
}

beforeEach(() => vi.resetAllMocks())
afterEach(() => {
  disposers.splice(0).forEach((dispose) => dispose())
  vi.restoreAllMocks()
})

describe('Tury zakupów przy dużej konfiguracji', () => {
  it('ogranicza pierwszy render, zachowując wszystkie 8196 tur w cache serwera', async () => {
    const items = rounds(8196)
    const { wrapper, client } = await render(items)

    expect(wrapper.get('[data-testid="round-configs-list"]').findAll('li')).toHaveLength(20)
    expect(wrapper.get('[data-testid="round-configs-count"]').text()).toBe(
      'Pokazano 20 z 8196 tur.',
    )
    expect(client.getQueryData(queryKeys.shopping.roundConfigs)).toEqual({ items, total: 8196 })
    expect(api.fetchRoundConfigs).toHaveBeenCalledTimes(1)
    expect(api.updateRoundConfig).not.toHaveBeenCalled()
  })

  it('udostępnia każdą turę kolejnymi porcjami bez ponownego pobierania ani mutacji', async () => {
    const { wrapper } = await render(rounds(45))
    await wrapper.get('[data-testid="round-configs-more"]').trigger('click')
    expect(wrapper.get('[data-testid="round-configs-list"]').findAll('li')).toHaveLength(40)
    await wrapper.get('[data-testid="round-configs-more"]').trigger('click')

    expect(wrapper.get('[data-testid="round-configs-list"]').findAll('li')).toHaveLength(45)
    expect(wrapper.find('[data-testid="round-configs-more"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="round-up-101"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="round-down-145"]').attributes('disabled')).toBeDefined()
    expect(api.fetchRoundConfigs).toHaveBeenCalledTimes(1)
    expect(api.updateRoundConfig).not.toHaveBeenCalled()
  })

  it('przesuwa ostatnią widoczną turę względem ukrytego sąsiada w pełnej kolejności', async () => {
    const items = rounds(45)
    const { wrapper, client } = await render(items)
    expect(wrapper.find('[data-testid="round-config-121"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="round-down-120"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('[data-testid="round-down-120"]').trigger('click')
    await flushPromises()

    expect(api.updateRoundConfig.mock.calls).toEqual([
      [120, { clear_shopping_weekday: false, clear_fresh_days: false, position: 20 }],
      [121, { clear_shopping_weekday: false, clear_fresh_days: false, position: 19 }],
    ])
    expect(api.fetchRoundConfigs).toHaveBeenCalledTimes(2)
    expect(client.getQueryData(queryKeys.shopping.roundConfigs)).toEqual({ items, total: 45 })
  })

  it('zachowuje globalne pozycje po pokazaniu kolejnej porcji', async () => {
    const { wrapper } = await render(rounds(45))
    await wrapper.get('[data-testid="round-configs-more"]').trigger('click')
    await wrapper.get('[data-testid="round-up-121"]').trigger('click')
    await flushPromises()

    expect(api.updateRoundConfig.mock.calls).toEqual([
      [121, { clear_shopping_weekday: false, clear_fresh_days: false, position: 19 }],
      [120, { clear_shopping_weekday: false, clear_fresh_days: false, position: 20 }],
    ])
    expect(wrapper.get('[data-testid="round-configs-list"]').findAll('li')).toHaveLength(40)
  })

  it('po ujawnieniu dalszych tur zachowuje edycję, usuwanie i tworzenie oraz pełny odczyt', async () => {
    let items = rounds(21)
    const { wrapper, client } = await render(items)
    api.fetchRoundConfigs.mockImplementation(async () => ({ items, total: items.length }))
    api.updateRoundConfig.mockImplementation(async (id, patch) => {
      items = items.map((item) => (item.id === id ? { ...item, ...patch } : item))
      return items.find((item) => item.id === id)
    })
    api.deleteRoundConfig.mockImplementation(async (id) => {
      items = items.filter((item) => item.id !== id)
    })
    const added = { ...rounds(1)[0]!, id: 999, name: 'Nowa tura', position: 21 }
    api.createRoundConfig.mockImplementation(async () => {
      items = [...items, added]
      return added
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    await wrapper.get('[data-testid="round-configs-more"]').trigger('click')
    await wrapper.get('[data-testid="round-edit-121"]').trigger('click')
    await wrapper.get('[data-testid="round-name"]').setValue('Zmieniona tura')
    await wrapper.get('[data-testid="round-form"]').trigger('submit')
    await flushPromises()
    expect(api.updateRoundConfig).toHaveBeenCalledWith(121, {
      name: 'Zmieniona tura',
      mode: 'durable_plus_fresh_window',
      covers_days: 7,
      fresh_days: 4,
      clear_fresh_days: false,
      shopping_weekday: undefined,
      clear_shopping_weekday: true,
    })
    expect(wrapper.get('[data-testid="round-config-121"]').text()).toContain('Zmieniona tura')

    await wrapper.get('[data-testid="round-remove-121"]').trigger('click')
    await flushPromises()
    expect(api.deleteRoundConfig).toHaveBeenCalledWith(121)
    expect(wrapper.find('[data-testid="round-config-121"]').exists()).toBe(false)

    await wrapper.get('[data-testid="round-add"]').trigger('click')
    await wrapper.get('[data-testid="round-name"]').setValue('Nowa tura')
    await wrapper.get('[data-testid="round-form"]').trigger('submit')
    await flushPromises()
    expect(api.createRoundConfig).toHaveBeenCalledWith({
      name: 'Nowa tura',
      mode: 'durable_plus_fresh_window',
      covers_days: 7,
      fresh_days: 4,
      shopping_weekday: null,
    })
    expect(wrapper.get('[data-testid="round-config-999"]').text()).toContain('Nowa tura')
    expect(client.getQueryData(queryKeys.shopping.roundConfigs)).toEqual({ items, total: 21 })
    expect(api.fetchRoundConfigs).toHaveBeenCalledTimes(4)
  })
})
