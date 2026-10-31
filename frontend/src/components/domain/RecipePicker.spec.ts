import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import type * as Recipes from '@/api/recipes'
import { queryKeys } from '@/api/queryKeys'
import RecipePicker from './RecipePicker.vue'

const api = vi.hoisted(() => ({ fetchRecipes: vi.fn(), createRecipe: vi.fn() }))
vi.mock('@/api/recipes', async (original) => ({ ...(await original<typeof Recipes>()), ...api }))
const recipe = { id: 1, name: 'Zupa', nutrition: { kcal: '100' } }
let wrapper: VueWrapper
let client: QueryClient
function open(debounceMs = 0): void {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  wrapper = mount(RecipePicker, {
    props: { debounceMs },
    global: { plugins: [[VueQueryPlugin, { queryClient: client }]] },
  })
}
async function search(value: string): Promise<void> {
  await wrapper.get('[data-testid="recipe-picker-input"]').trigger('focus')
  await wrapper.get('[data-testid="recipe-picker-input"]').setValue(value)
  await flushPromises()
}
beforeEach(() => {
  vi.clearAllMocks()
  api.fetchRecipes.mockResolvedValue({ items: [], total: 0 })
  api.createRecipe.mockResolvedValue(recipe)
})
afterEach(() => {
  wrapper?.unmount()
  client?.clear()
})

describe('RecipePicker — odczyt, cache i bieżąca fraza', () => {
  it('oddziela pierwsze ładowanie, błąd bez cache i udany brak wyników', async () => {
    let reject!: (error: Error) => void
    api.fetchRecipes.mockImplementationOnce(
      () =>
        new Promise((_resolve, failure) => {
          reject = failure
        }),
    )
    open()
    await search('Zupa')
    expect(wrapper.find('[data-testid="recipe-picker-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="recipe-picker-empty"]').exists()).toBe(false)
    reject(new Error('Brak odczytu'))
    await flushPromises()
    expect(wrapper.find('[data-testid="recipe-picker-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="recipe-picker-create"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="recipe-picker-empty"]').exists()).toBe(false)
    await wrapper.get('[data-testid="recipe-picker-input"]').trigger('keydown', { key: 'Enter' })
    expect(wrapper.find('[data-testid="recipe-create-drawer"]').exists()).toBe(false)
    await wrapper.get('[data-testid="recipe-picker-retry"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="recipe-picker-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="recipe-picker-create"]').exists()).toBe(true)
  })

  it('refetch failure zachowuje nowszy cache i pokazuje odrębny komunikat z retry', async () => {
    api.fetchRecipes.mockResolvedValue({ items: [recipe], total: 1 })
    open()
    await search('Zupa')
    api.fetchRecipes.mockRejectedValue(new Error('Brak odświeżenia'))
    const key = queryKeys.recipes.list({ limit: 8, offset: 0, q: 'Zupa' })
    client.setQueryData(key, { items: [{ ...recipe, name: 'Nowszy przepis w cache' }], total: 1 })
    await client.invalidateQueries({ queryKey: queryKeys.recipes.all })
    await flushPromises()
    expect(wrapper.get('[data-testid="recipe-picker-refetch-error"]').text()).toContain(
      'ostatnio pobrane',
    )
    expect(wrapper.get('[data-testid="recipe-picker-option-1"]').text()).toContain(
      'Nowszy przepis w cache',
    )
    expect(wrapper.find('[data-testid="recipe-picker-empty"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="recipe-picker-create"]').exists()).toBe(false)
  })

  it('Enter podczas debounce nie wybiera poprzedniego wyniku jako wyniku nowej frazy', async () => {
    api.fetchRecipes.mockResolvedValue({ items: [recipe], total: 1 })
    open(60)
    await search('Zupa')
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="recipe-picker-option-1"]').exists()).toBe(true),
    )
    await search('Zapiekanka')
    expect(wrapper.find('[data-testid="recipe-picker-option-1"]').exists()).toBe(false)
    await wrapper.get('[data-testid="recipe-picker-input"]').trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('selected')).toBeUndefined()
    expect(wrapper.find('[data-testid="recipe-create-drawer"]').exists()).toBe(false)
    await vi.waitFor(() =>
      expect(api.fetchRecipes).toHaveBeenLastCalledWith({ limit: 8, offset: 0, q: 'Zapiekanka' }),
    )
  })

  it('stary brak wyników nie otwiera create dla nowej frazy przed debounce', async () => {
    open(60)
    await search('Zupa')
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="recipe-picker-create"]').exists()).toBe(true),
    )
    await wrapper.get('[data-testid="recipe-picker-create"]').trigger('click')
    expect(wrapper.get('[data-testid="recipe-create-drawer"]').text()).toContain('Zupa')
    await search('Zapiekanka')
    expect(wrapper.find('[data-testid="recipe-create-drawer"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="recipe-picker-create"]').exists()).toBe(false)
    await wrapper.get('[data-testid="recipe-picker-input"]').trigger('keydown', { key: 'Enter' })
    expect(wrapper.find('[data-testid="recipe-create-drawer"]').exists()).toBe(false)
    expect(api.createRecipe).not.toHaveBeenCalled()
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="recipe-picker-create"]').exists()).toBe(true),
    )
    await wrapper.get('[data-testid="recipe-picker-create"]').trigger('click')
    expect(wrapper.get('[data-testid="recipe-create-drawer"]').text()).toContain('Zapiekanka')
    await wrapper.get('[data-testid="recipe-create-drawer"]').trigger('submit')
    await flushPromises()
    expect(api.createRecipe.mock.calls[0]?.[0].name).toBe('Zapiekanka')
  })

  it('błąd tworzenia zostawia formularz, a wybór udanego przepisu zachowuje dotychczasowe zdarzenia', async () => {
    api.createRecipe.mockRejectedValueOnce(
      new ApiError(422, { code: 'validation_error', message: 'Popraw przepis', details: {} }),
    )
    open()
    await search('Zupa')
    await wrapper.get('[data-testid="recipe-picker-create"]').trigger('click')
    await wrapper.get('[data-testid="recipe-create-drawer"]').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[data-testid="recipe-create-drawer"]').text()).toContain('Popraw przepis')
    expect(wrapper.get('[data-testid="recipe-create-drawer"]').text()).toContain('Zupa')
    await wrapper.get('[data-testid="recipe-create-drawer"]').trigger('submit')
    await flushPromises()
    expect(wrapper.emitted('selected')?.[0]).toEqual([recipe])
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([recipe])
  })
})
