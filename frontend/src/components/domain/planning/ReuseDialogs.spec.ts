import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { TemplateSummary, Cycle } from '@/api/templates'
import TemplateApplyDialog from './TemplateApplyDialog.vue'
import CycleEditorDialog from './CycleEditorDialog.vue'
import ReuseHistoryDialog from './ReuseHistoryDialog.vue'
import DateMultiSelect from './DateMultiSelect.vue'
import PlanningDialog from './PlanningDialog.vue'
import TemplateSourcePreview from './TemplateSourcePreview.vue'
import PlanReusePreview from './PlanReusePreview.vue'
import { queryKeys } from '@/api/queryKeys'
import { daysBetween } from '@/lib/dates'
const api = vi.hoisted(() => ({
  fetchPlanDays: vi.fn(),
  fetchDayTemplate: vi.fn(),
  fetchWeekTemplate: vi.fn(),
  fetchRecipe: vi.fn(),
}))
vi.mock('@/api/planning', () => api)
vi.mock('@/api/templates', () => api)
vi.mock('@/api/recipes', () => api)
let wrapper: VueWrapper
let client: QueryClient
const summary: TemplateSummary = {
  id: 1,
  name: 'Dzień zimowy',
  scope: 'private',
  owner_user_id: 1,
  summary: '1 posiłek',
  created_at: '2031-01-01T12:00:00Z',
  updated_at: '2031-01-01T12:00:00Z',
}
beforeEach(() => {
  vi.resetAllMocks()
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  api.fetchPlanDays.mockResolvedValue({ items: [] })
  api.fetchDayTemplate.mockResolvedValue({
    ...summary,
    payload: { meals: [{ name: 'Obiad', items: [] }] },
  })
  api.fetchWeekTemplate.mockImplementation(async (id: number) => ({
    ...summary,
    id,
    payload: {
      days: [
        { offset: 0, day: { meals: [{ name: `Posiłek ${id}`, items: [{ recipe_id: id }] }] } },
      ],
    },
  }))
  api.fetchRecipe.mockImplementation(async (id: number) => ({
    id,
    name: `Archiwalny przepis ${id}`,
    is_archived: true,
  }))
})
afterEach(() => {
  wrapper?.unmount()
  client.clear()
  document.body.innerHTML = ''
})
const global = () => ({
  plugins: [
    [VueQueryPlugin, { queryClient: client }] as [
      typeof VueQueryPlugin,
      { queryClient: QueryClient },
    ],
  ],
})
it('szablon zachowuje kalendarz przy dociągnięciu opcji i po błędzie zapisu', async () => {
  wrapper = mount(TemplateApplyDialog, {
    props: {
      open: true,
      selectedDate: '2031-12-31',
      weekStart: '2031-12-29',
      dayTemplates: [],
      weekTemplates: [],
      loading: true,
    },
    global: global(),
  })
  await flushPromises()
  expect(wrapper.findComponent(PlanningDialog).props('validationMessage')).toBeNull()
  await wrapper.setProps({ dayTemplates: [summary], loading: false })
  await flushPromises()
  wrapper.getComponent(DateMultiSelect).vm.$emit('update:modelValue', ['2031-12-31', '2032-01-02'])
  await flushPromises()
  await wrapper.setProps({ dayTemplates: [{ ...summary }] })
  await flushPromises()
  expect(wrapper.getComponent(DateMultiSelect).props('modelValue')).toEqual([
    '2031-12-31',
    '2032-01-02',
  ])
  expect(wrapper.getComponent(PlanningDialog).props('submitDisabled')).toBe(false)
  wrapper.getComponent(PlanningDialog).vm.$emit('submit')
  await flushPromises()
  await wrapper.setProps({ error: 'Błąd zapisu' })
  wrapper.getComponent(PlanningDialog).vm.$emit('submit')
  await flushPromises()
  expect(wrapper.emitted('apply-day')).toEqual([
    [{ templateId: 1, dates: ['2031-12-31', '2032-01-02'] }],
    [{ templateId: 1, dates: ['2031-12-31', '2032-01-02'] }],
  ])
})
it('cykl przed datą kotwicy sprawdza użyte szablony, a nie archiwalne przepisy z niewykorzystanego tygodnia', async () => {
  const cycle: Cycle = {
    id: 4,
    name: 'Rotacja',
    scope: 'private',
    owner_user_id: 1,
    template_ids: [1, 2, 3],
    template_names: ['A', 'B', 'C'],
    start_date: '2032-01-19',
    created_at: summary.created_at,
    updated_at: summary.updated_at,
  }
  wrapper = mount(CycleEditorDialog, {
    attachTo: document.body,
    props: {
      open: true,
      weekStart: '2032-01-05',
      cycles: [cycle],
      weekTemplates: [summary, { ...summary, id: 2 }, { ...summary, id: 3 }],
    },
    global: global(),
  })
  await flushPromises()
  expect(api.fetchWeekTemplate.mock.calls.map((call) => call[0])).toEqual([2, 3])
  expect(api.fetchRecipe).not.toHaveBeenCalledWith(1, '1')
  const to = document.querySelector<HTMLInputElement>('[data-testid="cycle-date-to"]')!
  to.value = '2032-01-06'
  to.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
  expect(wrapper.getComponent(TemplateSourcePreview).props('references')).toEqual([
    { kind: 'week', id: 2 },
  ])
  expect(
    document.querySelector('[data-testid="template-archive-warnings"]')?.textContent,
  ).toContain('Archiwalny przepis 2')
  expect(
    document.querySelector('[data-testid="template-archive-warnings"]')?.textContent,
  ).not.toContain('Archiwalny przepis 3')
  wrapper.getComponent(PlanningDialog).vm.$emit('submit')
  await flushPromises()
  expect(wrapper.emitted('apply')).toEqual([
    [{ cycleId: 4, dateFrom: '2032-01-05', dateTo: '2032-01-06' }],
  ])
})
it('błąd historii jest błędem, a nie pustą historią', async () => {
  wrapper = mount(ReuseHistoryDialog, {
    props: {
      open: true,
      selectedDate: '2031-12-31',
      history: [],
      unavailable: true,
      error: 'Nie udało się wczytać historii.',
    },
    global: global(),
  })
  await flushPromises()
  const panel = wrapper.getComponent(PlanningDialog)
  expect(panel.props('validationMessage')).toBeNull()
  expect(panel.props('error')).toContain('Nie udało')
  panel.vm.$emit('submit')
  await flushPromises()
  expect(wrapper.emitted('apply')).toBeUndefined()
})

it('zmiana szablonu na wpis z cache blokuje zastosowanie do zakończenia bieżącego GET', async () => {
  let rejectRead!: (reason: Error) => void
  const cached = { ...summary, id: 2, payload: { meals: [{ name: 'Stara zawartość', items: [] }] } }
  client.setQueryData(queryKeys.templates.day(2), cached)
  api.fetchDayTemplate.mockImplementation((id: number) =>
    id === 2
      ? new Promise((_resolve, reject) => {
          rejectRead = reject
        })
      : Promise.resolve({ ...summary, payload: { meals: [] } }),
  )
  wrapper = mount(TemplateApplyDialog, {
    attachTo: document.body,
    props: {
      open: true,
      selectedDate: '2031-12-31',
      weekStart: '2031-12-29',
      dayTemplates: [summary, { ...summary, id: 2 }],
      weekTemplates: [],
    },
    global: global(),
  })
  await flushPromises()
  expect(wrapper.getComponent(PlanningDialog).props('submitDisabled')).toBe(false)
  const select = document.querySelector<HTMLSelectElement>('[data-testid="apply-day-template"]')!
  select.value = '2'
  select.dispatchEvent(new Event('change', { bubbles: true }))
  await flushPromises()
  const panel = wrapper.getComponent(PlanningDialog)
  expect(panel.props('submitDisabled')).toBe(true)
  panel.vm.$emit('submit')
  await flushPromises()
  expect(wrapper.emitted('apply-day')).toBeUndefined()
  rejectRead(new Error('Odmowa odświeżenia'))
  await flushPromises()
  expect(panel.props('submitDisabled')).toBe(true)
  expect(
    document.querySelector('[data-testid="template-source-preview"] [role="alert"]')?.textContent,
  ).toContain('Nie udało się sprawdzić')
  panel.vm.$emit('submit')
  await flushPromises()
  expect(wrapper.emitted('apply-day')).toBeUndefined()
})

const initialCycle: Cycle = {
  id: 4,
  name: 'Rotacja',
  scope: 'private',
  owner_user_id: 1,
  template_ids: [1, 2],
  template_names: ['A', 'B'],
  start_date: null,
  created_at: summary.created_at,
  updated_at: summary.updated_at,
}
it('odświeżenie listy cykli ukrywa stare źródła i blokuje Apply aż do sprawdzenia nowej rotacji', async () => {
  wrapper = mount(CycleEditorDialog, {
    attachTo: document.body,
    props: {
      open: true,
      weekStart: '2032-01-05',
      cycles: [initialCycle],
      weekTemplates: [summary],
    },
    global: global(),
  })
  await flushPromises()
  const panel = wrapper.getComponent(PlanningDialog)
  expect(panel.props('submitDisabled')).toBe(false)
  await wrapper.setProps({ loading: true })
  await flushPromises()
  expect(wrapper.findComponent(TemplateSourcePreview).exists()).toBe(false)
  expect(panel.props('submitDisabled')).toBe(true)
  panel.vm.$emit('submit')
  await flushPromises()
  expect(wrapper.emitted('apply')).toBeUndefined()
  await wrapper.setProps({
    loading: false,
    cycles: [{ ...initialCycle, template_ids: [3, 4], template_names: ['C', 'D'] }],
  })
  await flushPromises()
  expect(wrapper.getComponent(TemplateSourcePreview).props('references')).toEqual([
    { kind: 'week', id: 3 },
    { kind: 'week', id: 4 },
  ])
  expect(wrapper.getComponent(PlanReusePreview).props('sourceLabel')).toContain('C → D')
  expect(panel.props('submitDisabled')).toBe(false)
  await wrapper.setProps({ unavailable: true, error: 'Nie udało się odświeżyć cykli.' })
  await flushPromises()
  expect(panel.props('submitDisabled')).toBe(true)
  expect(wrapper.findComponent(TemplateSourcePreview).exists()).toBe(false)
  panel.vm.$emit('submit')
  await flushPromises()
  expect(wrapper.emitted('apply')).toBeUndefined()
})

it('daleki legalny zakres ma podgląd tylko bieżących 28 dni, a Apply zachowuje pełny payload', async () => {
  wrapper = mount(CycleEditorDialog, {
    attachTo: document.body,
    props: {
      open: true,
      weekStart: '2032-01-05',
      cycles: [initialCycle],
      weekTemplates: [summary],
    },
    global: global(),
  })
  await flushPromises()
  const from = document.querySelector<HTMLInputElement>('[data-testid="cycle-date-from"]')!
  const to = document.querySelector<HTMLInputElement>('[data-testid="cycle-date-to"]')!
  from.value = '0001-01-01'
  from.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
  to.value = '9999-12-31'
  to.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
  expect(wrapper.getComponent(PlanReusePreview).props('dates')).toHaveLength(28)
  expect(document.querySelector('[data-testid="reuse-targets"]')?.children).toHaveLength(28)
  expect(document.querySelector('[data-testid="cycle-range-summary"]')?.textContent).toContain(
    '0001-01-01 – 9999-12-31',
  )
  expect(document.querySelector('[data-testid="cycle-preview-slice"]')?.textContent).toContain(
    'Pozostałe dni nie są sprawdzone',
  )
  expect(api.fetchPlanDays.mock.calls.length).toBeLessThanOrEqual(3)
  expect(api.fetchPlanDays.mock.calls.every(([from, to]) => daysBetween(from, to) < 28)).toBe(true)
  expect(api.fetchWeekTemplate.mock.calls.map(([id]) => id)).toEqual([1, 2])
  document.querySelector<HTMLButtonElement>('[data-testid="cycle-preview-next"]')!.click()
  await flushPromises()
  expect(wrapper.getComponent(PlanReusePreview).props('dates')[0]).toBe('0001-01-29')
  expect(document.querySelector('[data-testid="reuse-targets"]')?.children).toHaveLength(28)
  expect(api.fetchPlanDays.mock.calls.length).toBeLessThanOrEqual(4)
  wrapper.getComponent(PlanningDialog).vm.$emit('submit')
  await flushPromises()
  expect(wrapper.emitted('apply')).toEqual([
    [{ cycleId: 4, dateFrom: '0001-01-01', dateTo: '9999-12-31' }],
  ])
})
