import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { queryKeys } from '@/api/queryKeys'
import TemplateSourcePreview from './TemplateSourcePreview.vue'
const api = vi.hoisted(() => ({
  fetchDayTemplate: vi.fn(),
  fetchWeekTemplate: vi.fn(),
  fetchRecipe: vi.fn(),
  fetchProduct: vi.fn(),
}))
vi.mock('@/api/templates', () => api)
vi.mock('@/api/recipes', () => api)
vi.mock('@/api/catalog', () => api)
let wrapper: VueWrapper
let client: QueryClient
const template = {
  id: 3,
  name: 'Dzień zimowy',
  payload: { meals: [{ name: 'Obiad', items: [{ recipe_id: 7 }, { product_id: 2 }] }] },
}
beforeEach(() => {
  vi.resetAllMocks()
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  api.fetchDayTemplate.mockResolvedValue(template)
  api.fetchRecipe.mockResolvedValue({ id: 7, name: 'Zupa archiwalna', is_archived: true })
  api.fetchProduct.mockResolvedValue({ id: 2, name: 'Produkt aktywny', is_archived: false })
})
afterEach(() => {
  wrapper?.unmount()
  client.clear()
})
async function render() {
  wrapper = mount(TemplateSourcePreview, {
    props: { references: [{ kind: 'day', id: 3 }] },
    global: { plugins: [[VueQueryPlugin, { queryClient: client }]] },
  })
  await flushPromises()
}
it('pokazuje prawdziwe ostrzeżenia archiwalne przed zapisem i nie zmienia kształtu wspólnego cache szablonu', async () => {
  await render()
  expect(wrapper.get('[data-testid="template-archive-warnings"]').text()).toContain(
    'Zupa archiwalna',
  )
  expect(wrapper.get('[data-testid="template-archive-warnings"]').text()).not.toContain(
    'Produkt aktywny',
  )
  expect(wrapper.emitted('ready')?.at(-1)).toEqual([true])
  expect(client.getQueryData(queryKeys.templates.day(3))).toEqual(template)
})
it('niedostępny przepis jest błędem, nie pustym szablonem', async () => {
  api.fetchRecipe.mockRejectedValue(new Error('404'))
  await render()
  expect(wrapper.get('[role="alert"]').text()).toContain('Nie udało się sprawdzić')
  expect(wrapper.emitted('ready')?.at(-1)).toEqual([false])
})

it('odświeżenie szablonu z cache wymaga odpowiedzi i zachowuje blokadę po błędzie', async () => {
  let rejectRead!: (reason: Error) => void
  client.setQueryData(queryKeys.templates.day(3), template)
  client.setQueryData(queryKeys.recipes.detail(7, '1'), {
    id: 7,
    name: 'Stara nazwa',
    is_archived: false,
  })
  api.fetchDayTemplate.mockReturnValue(
    new Promise((_resolve, reject) => {
      rejectRead = reject
    }),
  )
  await render()
  expect(wrapper.get('[role="status"]').text()).toContain('Sprawdzamy')
  expect(wrapper.emitted('ready')?.at(-1)).toEqual([false])
  rejectRead(new Error('Odmowa odświeżenia'))
  await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('Nie udało się sprawdzić')
  expect(wrapper.emitted('ready')?.at(-1)).toEqual([false])
  expect(client.getQueryData(queryKeys.templates.day(3))).toEqual(template)
})
