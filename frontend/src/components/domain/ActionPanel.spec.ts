import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import ActionPanel from './ActionPanel.vue'

let wrapper: VueWrapper | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  document.body.innerHTML = ''
})

function element<T extends HTMLElement = HTMLElement>(selector: string): T {
  const found = document.querySelector<T>(selector)
  if (!found) throw new Error(`Brak elementu: ${selector}`)
  return found
}

async function openPanel(extra: Record<string, unknown> = {}): Promise<HTMLButtonElement> {
  const opener = document.createElement('button')
  opener.textContent = 'Zaplanuj obiad'
  document.body.append(opener)
  opener.focus()
  wrapper = mount(ActionPanel, {
    attachTo: document.body,
    props: {
      open: false,
      title: 'Zaplanuj przepis',
      description: '6 stycznia · późny obiad · Żurek',
      submitLabel: 'Zaplanuj',
      ...extra,
    },
    slots: {
      default: ({ formId }: { formId: string }) =>
        h('label', ['Nazwa posiłku', h('input', { name: 'meal', required: true, form: formId })]),
    },
  })
  await wrapper.setProps({ open: true })
  await flushPromises()
  await vi.waitFor(() => expect(document.querySelector('[role="dialog"]')).not.toBeNull())
  await vi.waitFor(() =>
    expect(element('[role="dialog"]').contains(document.activeElement)).toBe(true),
  )
  return opener
}

function sendForm(): void {
  element('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
}

describe('ActionPanel — rzeczywisty Reka Dialog', () => {
  it('ma nazwę, opis kontekstu, fokus w modalu i powrót po Escape', async () => {
    const opener = await openPanel()
    const dialog = element('[role="dialog"]')
    const labelId = dialog.getAttribute('aria-labelledby')
    const descriptionId = dialog.getAttribute('aria-describedby')
    expect(document.getElementById(labelId!)?.textContent).toBe('Zaplanuj przepis')
    expect(document.getElementById(descriptionId!)?.textContent).toContain('6 stycznia')
    await vi.waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true))
    // Reka utrzymuje fokus także przy próbie wyjścia do kontrolki za panelem.
    opener.focus()
    expect(dialog.contains(document.activeElement)).toBe(true)
    document.activeElement?.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }),
    )
    await flushPromises()
    expect(wrapper!.emitted('close')).toHaveLength(1)
    await wrapper!.setProps({ open: false })
    await vi.waitFor(() => expect(document.activeElement).toBe(opener))
  })

  it('waliduje natywne pola i przekazany komunikat, bez wysłania niepoprawnych danych', async () => {
    await openPanel()
    sendForm()
    await flushPromises()
    expect(wrapper!.emitted('submit')).toBeUndefined()
    const input = element<HTMLInputElement>('input[name="meal"]')
    expect(document.activeElement).toBe(input)
    input.value = 'Późny obiad'
    await wrapper!.setProps({ validationMessage: 'Wybierz co najmniej jedną osobę.' })
    sendForm()
    expect(wrapper!.emitted('submit')).toBeUndefined()
    expect(element('[data-testid="action-panel-validation"]').textContent).toContain('Wybierz')
    await wrapper!.setProps({ validationMessage: null })
    sendForm()
    await flushPromises()
    expect(wrapper!.emitted('submit')).toHaveLength(1)
  })

  it('blokuje podwójne wysłanie, edycję i zamknięcie w pending; po błędzie zachowuje szkic', async () => {
    await openPanel()
    const input = element<HTMLInputElement>('input[name="meal"]')
    input.value = 'Żurek po spacerze'
    sendForm()
    sendForm()
    expect(wrapper!.emitted('submit')).toHaveLength(1)
    await wrapper!.setProps({ pending: true })
    expect(element('[aria-busy]').getAttribute('aria-busy')).toBe('true')
    expect(element<HTMLFieldSetElement>('fieldset').disabled).toBe(true)
    expect(element<HTMLButtonElement>('[data-testid="action-panel-submit"]').disabled).toBe(true)
    expect(element<HTMLButtonElement>('[data-testid="action-panel-cancel"]').disabled).toBe(true)
    element('[data-testid="action-panel-close"]').click()
    document.activeElement?.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }),
    )
    sendForm()
    await flushPromises()
    expect(wrapper!.emitted('close')).toBeUndefined()
    expect(wrapper!.emitted('submit')).toHaveLength(1)
    await wrapper!.setProps({ pending: false, error: 'Zapis się nie powiódł. Spróbuj ponownie.' })
    await flushPromises()
    expect(input.value).toBe('Żurek po spacerze')
    expect(document.activeElement).toBe(element('[data-testid="action-panel-error"]'))
    sendForm()
    await flushPromises()
    expect(wrapper!.emitted('submit')).toHaveLength(2)
    element('[data-testid="action-panel-cancel"]').click()
    expect(wrapper!.emitted('close')).toHaveLength(1)
  })

  it('nie zamyka przez kliknięcie poza formularzem i nie resetuje pól przy odświeżeniu propsów', async () => {
    const opener = await openPanel({ warnings: ['Przepis jest archiwalny.'] })
    const input = element<HTMLInputElement>('input[name="meal"]')
    input.value = 'Obiad'
    opener.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await wrapper!.setProps({ description: '7 stycznia · obiad · Żurek' })
    expect(wrapper!.emitted('close')).toBeUndefined()
    expect(input.value).toBe('Obiad')
    expect(element('[data-testid="action-panel-warnings"]').textContent).toContain('archiwalny')
  })
})
