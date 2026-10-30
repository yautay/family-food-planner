import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import BlockCopyDialog from './BlockCopyDialog.vue'
import TemplateSaveDialog from './TemplateSaveDialog.vue'
import CycleEditorDialog from './CycleEditorDialog.vue'

let wrapper: VueWrapper | undefined
afterEach(() => {
  wrapper?.unmount()
  document.body.innerHTML = ''
})
function get<T extends HTMLElement = HTMLElement>(testid: string): T {
  const node = document.querySelector<T>(`[data-testid="${testid}"]`)
  if (!node) throw new Error(`Brak kontrolki ${testid}`)
  return node
}

describe('PlanningDialog — kompatybilność istniejących formularzy', () => {
  it('zmiana komunikatu walidacji podczas pisania nazwy cyklu nie odbiera fokusu', async () => {
    wrapper = mount(CycleEditorDialog, {
      attachTo: document.body,
      props: {
        open: true,
        weekStart: '2032-03-01',
        cycles: [],
        weekTemplates: [
          {
            id: 1,
            name: 'Tydzień warzywny',
            scope: 'private',
            owner_user_id: 1,
            summary: '7 dni',
            created_at: '2032-03-01T00:00:00Z',
            updated_at: '2032-03-01T00:00:00Z',
          },
        ],
      },
    })
    await flushPromises()
    await vi.waitFor(() =>
      expect(document.querySelector('[role="dialog"]')?.contains(document.activeElement)).toBe(
        true,
      ),
    )
    expect(get('cycle-editor-dialog-validation').textContent).toContain('Podaj nazwę')
    const input = get<HTMLInputElement>('cycle-name')
    input.focus()
    for (const character of 'Łucja i Żaneta') {
      expect(document.activeElement).toBe(input)
      input.setRangeText(
        character,
        input.selectionStart ?? input.value.length,
        input.selectionEnd ?? input.value.length,
        'end',
      )
      input.dispatchEvent(
        new InputEvent('input', { data: character, inputType: 'insertText', bubbles: true }),
      )
      await flushPromises()
      expect(document.activeElement).toBe(input)
    }
    expect(input.value).toBe('Łucja i Żaneta')
    expect(get('cycle-editor-dialog-validation').textContent).toContain('Dodaj przynajmniej')
    expect(get<HTMLButtonElement>('cycle-editor-dialog-submit').disabled).toBe(true)
  })
  it('zachowuje walidację bloku, podgląd i dotychczasowy payload', async () => {
    wrapper = mount(BlockCopyDialog, {
      attachTo: document.body,
      props: { open: true, sourceFrom: '2032-03-01' },
    })
    await flushPromises()
    await vi.waitFor(() => expect(document.querySelector('[role="dialog"]')).not.toBeNull())
    const input = get<HTMLInputElement>('block-source-days')
    input.value = '0'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await flushPromises()
    expect(get<HTMLButtonElement>('block-copy-dialog-submit').disabled).toBe(true)
    get('block-copy-dialog-submit').click()
    expect(wrapper.emitted('apply')).toBeUndefined()
    get('block-preset-222').click()
    await flushPromises()
    expect(get('block-preview-count').textContent).toBe('6')
    get('block-copy-dialog-submit').click()
    await flushPromises()
    expect(wrapper.emitted('apply')).toEqual([
      [
        {
          sourceFrom: '2032-03-01',
          sourceDays: 3,
          repeatEach: 2,
          targetStart: '2032-03-08',
        },
      ],
    ])
  })

  it('nie usuwa nazwy szablonu po błędzie i zachowuje selektory przy ponowieniu', async () => {
    wrapper = mount(TemplateSaveDialog, {
      attachTo: document.body,
      props: { open: true, selectedDate: '2032-03-01', weekDates: ['2032-03-01'] },
    })
    await flushPromises()
    expect(get<HTMLButtonElement>('template-save-dialog-submit').disabled).toBe(true)
    const input = get<HTMLInputElement>('template-name')
    input.value = 'Dzień Łucji i Żanety'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await flushPromises()
    get('template-save-dialog-submit').click()
    await wrapper.setProps({ pending: true })
    expect(get<HTMLButtonElement>('template-save-dialog-cancel').disabled).toBe(true)
    await wrapper.setProps({ pending: false, error: 'Nie udało się zapisać szablonu.' })
    await flushPromises()
    expect(input.value).toBe('Dzień Łucji i Żanety')
    expect(get('template-save-dialog-error').textContent).toContain('Nie udało')
    get('template-save-dialog-submit').click()
    await flushPromises()
    expect(wrapper.emitted('apply')).toHaveLength(2)
    expect(wrapper.emitted('apply')?.[1]).toEqual([
      {
        kind: 'day',
        name: 'Dzień Łucji i Żanety',
        scope: 'private',
        sourceDate: '2032-03-01',
      },
    ])
  })
})
