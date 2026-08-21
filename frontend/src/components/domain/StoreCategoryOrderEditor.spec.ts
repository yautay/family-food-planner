import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import StoreCategoryOrderEditor from './StoreCategoryOrderEditor.vue'

/**
 * Edytor kolejności kategorii (B09).
 *
 * Testujemy ALTERNATYWĘ PRZYCISKOWĄ, nie drag&drop: strzałki są obowiązkowe
 * (06_UIUX §2), bo na telefonie i z klawiatury to jedyna droga. Natywny DnD
 * przechodzi tym samym `move()`, więc jego logika jest tu pokryta pośrednio,
 * a gest sprawdza E2E.
 */

const CATEGORIES = [
  { id: 1, name: 'Warzywa', position: 1, perishability: 'fresh' as const },
  { id: 2, name: 'Nabiał', position: 2, perishability: 'fresh' as const },
  { id: 3, name: 'Pieczywo', position: 3, perishability: 'fresh' as const },
]

const ORDER = [
  { category_id: 1, category_name: 'Warzywa', position: 0 },
  { category_id: 2, category_name: 'Nabiał', position: 1 },
]

function mountEditor() {
  return mount(StoreCategoryOrderEditor, {
    props: { categories: CATEGORIES, order: ORDER },
  })
}

function visibleOrder(wrapper: ReturnType<typeof mountEditor>): string[] {
  return wrapper.findAll('[data-testid^="order-row-"]').map((row) => row.attributes('data-testid')!)
}

describe('StoreCategoryOrderEditor', () => {
  it('pokazuje profil w kolejności z serwera i kategorie poza profilem', () => {
    const wrapper = mountEditor()

    expect(visibleOrder(wrapper)).toEqual(['order-row-1', 'order-row-2'])
    // Pieczywo nie jest w profilu, więc czeka w „Kategorie poza profilem".
    expect(wrapper.find('[data-testid="order-add-3"]').exists()).toBe(true)
  })

  it('strzałka w dół przestawia pozycję i emituje nową kolejność', async () => {
    const wrapper = mountEditor()

    await wrapper.get('[data-testid="order-down-1"]').trigger('click')
    expect(visibleOrder(wrapper)).toEqual(['order-row-2', 'order-row-1'])

    await wrapper.get('[data-testid="order-save"]').trigger('click')
    expect(wrapper.emitted('save')).toEqual([[[2, 1]]])
  })

  it('strzałka w górę wraca do stanu wyjściowego, a zapis jest wtedy zablokowany', async () => {
    const wrapper = mountEditor()

    await wrapper.get('[data-testid="order-down-1"]').trigger('click')
    await wrapper.get('[data-testid="order-up-1"]').trigger('click')

    expect(visibleOrder(wrapper)).toEqual(['order-row-1', 'order-row-2'])
    // Brak zmian = nie ma czego zapisywać (jedno kliknięcie mniej, 06_UIUX §2).
    expect(wrapper.get('[data-testid="order-save"]').attributes('disabled')).toBeDefined()
  })

  it('skrajne strzałki są wyłączone', () => {
    const wrapper = mountEditor()

    expect(wrapper.get('[data-testid="order-up-1"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="order-down-2"]').attributes('disabled')).toBeDefined()
  })

  it('dodanie i usunięcie kategorii zmienia zapisywaną listę', async () => {
    const wrapper = mountEditor()

    await wrapper.get('[data-testid="order-add-3"]').trigger('click')
    await wrapper.get('[data-testid="order-remove-1"]').trigger('click')
    await wrapper.get('[data-testid="order-save"]').trigger('click')

    expect(wrapper.emitted('save')).toEqual([[[2, 3]]])
  })

  it('przeciągnięcie wiersza na miejsce innego zmienia kolejność', async () => {
    const wrapper = mountEditor()

    await wrapper.get('[data-testid="order-row-2"]').trigger('dragstart')
    await wrapper.get('[data-testid="order-row-1"]').trigger('drop')

    expect(visibleOrder(wrapper)).toEqual(['order-row-2', 'order-row-1'])
  })

  it('refetch tej samej kolejności NIE kasuje niezapisanych przestawień', async () => {
    // Regresja z /code-review B09: `SklepySection` unieważnia cały klucz
    // `['stores']`, więc profil bywa refetchowany w środku edycji (np. po
    // archiwizacji innego sklepu). Szkic użytkownika musi to przeżyć.
    const wrapper = mountEditor()
    await wrapper.get('[data-testid="order-down-1"]').trigger('click')
    expect(visibleOrder(wrapper)).toEqual(['order-row-2', 'order-row-1'])

    // Nowa TABLICA o tej samej treści = dokładnie to, co robi refetch.
    await wrapper.setProps({ order: ORDER.map((entry) => ({ ...entry })) })

    expect(visibleOrder(wrapper)).toEqual(['order-row-2', 'order-row-1'])
    await wrapper.get('[data-testid="order-save"]').trigger('click')
    expect(wrapper.emitted('save')).toEqual([[[2, 1]]])
  })

  it('kolejność zmieniona na serwerze wchodzi, gdy szkic nie jest brudny', async () => {
    const wrapper = mountEditor()

    await wrapper.setProps({
      order: [
        { category_id: 3, category_name: 'Pieczywo', position: 0 },
        { category_id: 1, category_name: 'Warzywa', position: 1 },
      ],
    })

    expect(visibleOrder(wrapper)).toEqual(['order-row-3', 'order-row-1'])
  })

  it('pusty profil uczy, co zrobić dalej', () => {
    const wrapper = mount(StoreCategoryOrderEditor, {
      props: { categories: CATEGORIES, order: [] },
    })

    expect(wrapper.get('[data-testid="order-empty"]').text()).toContain('profilu')
  })
})
