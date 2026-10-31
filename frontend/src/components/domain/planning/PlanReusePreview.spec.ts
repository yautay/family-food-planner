import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { queryKeys } from '@/api/queryKeys'
import PlanReusePreview from './PlanReusePreview.vue'
const api = vi.hoisted(() => ({ fetchPlanDays: vi.fn() }))
vi.mock('@/api/planning', () => api)
let wrapper: VueWrapper
let client: QueryClient
beforeEach(() => {
  vi.resetAllMocks()
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
})
afterEach(() => {
  wrapper?.unmount()
  client.clear()
})
async function render(dates: string[], sourceDates: string[] = []) {
  wrapper = mount(PlanReusePreview, {
    props: { dates, sourceDates },
    global: { plugins: [[VueQueryPlugin, { queryClient: client }]] },
  })
  await flushPromises()
}
describe('podgląd źródła i celów', () => {
  it('cache nie potwierdza trwającego odświeżenia; odmowa GET blokuje gotowość', async () => {
    let rejectRead!: (reason: Error) => void
    client.setQueryData(queryKeys.planDays.range('2032-01-02', '2032-01-02'), { items: [] })
    api.fetchPlanDays.mockReturnValue(
      new Promise((_resolve, reject) => {
        rejectRead = reject
      }),
    )
    await render(['2032-01-02'])
    expect(wrapper.get('[role="status"]').text()).toContain('Sprawdzamy')
    expect(wrapper.find('[data-testid="reuse-targets"]').exists()).toBe(false)
    expect(wrapper.emitted('ready')?.at(-1)).toEqual([false])
    rejectRead(new Error('Odmowa odświeżenia'))
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('Nie udało się sprawdzić')
    expect(wrapper.emitted('ready')?.at(-1)).toEqual([false])
  })
  it('pokazuje rzeczywiste istniejące posiłki, puste źródło i semantykę dopisywania', async () => {
    api.fetchPlanDays.mockResolvedValue({
      items: [{ day: '2032-01-02', meals: [{ name: 'Własny obiad' }, { name: 'Kolacja' }] }],
    })
    await render(['2032-01-02'], ['2031-12-31'])
    expect(wrapper.get('[data-testid="reuse-targets"]').text()).toContain('Widoczne posiłki: 2')
    expect(wrapper.get('[data-testid="reuse-empty-source"]').text()).toContain('31.12.2031')
    expect(wrapper.text()).toContain('Istniejące posiłki pozostaną')
    expect(wrapper.text()).toContain('Przy dostępie administracyjnym')
    expect(wrapper.emitted('ready')?.at(-1)).toEqual([true])
  })
  it('błąd odczytu blokuje podgląd i nie przedstawia celu jako pustego; ponowienie odzyskuje dane', async () => {
    api.fetchPlanDays.mockRejectedValueOnce(new Error('Sieć')).mockResolvedValue({ items: [] })
    await render(['2032-01-02'])
    expect(wrapper.get('[role="alert"]').text()).toContain('Nie udało się sprawdzić')
    expect(wrapper.find('[data-testid="reuse-targets"]').exists()).toBe(false)
    expect(wrapper.emitted('ready')?.at(-1)).toEqual([false])
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="reuse-targets"]').text()).toContain('Brak posiłków')
    expect(wrapper.emitted('ready')?.at(-1)).toEqual([true])
  })
  it('rozłączne dni z różnych lat nie przekraczają limitu odczytu i zachowują standardowe klucze cache', async () => {
    api.fetchPlanDays.mockResolvedValue({ items: [] })
    await render(['2031-12-31', '2032-01-01', '2034-01-01'])
    expect(api.fetchPlanDays.mock.calls).toEqual([
      ['2031-12-31', '2032-01-01'],
      ['2034-01-01', '2034-01-01'],
    ])
    expect(client.getQueryData(queryKeys.planDays.range('2031-12-31', '2032-01-01'))).toEqual({
      items: [],
    })
  })
})
