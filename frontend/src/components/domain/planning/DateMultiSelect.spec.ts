import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import DateMultiSelect from './DateMultiSelect.vue'

let wrapper: VueWrapper<InstanceType<typeof DateMultiSelect>>
afterEach(() => {
  wrapper?.unmount()
  document.body.innerHTML = ''
})
function calendar(selected: string[] = []) {
  wrapper = mount(DateMultiSelect, {
    attachTo: document.body,
    props: {
      modelValue: selected,
      initialDate: '2031-12-31',
      testid: 'dates',
      'onUpdate:modelValue': (dates: string[]) => {
        void wrapper.setProps({ modelValue: dates })
      },
    },
  })
  return wrapper
}
describe('kalendarz wielu dat UX07', () => {
  it('zachowuje dni z grudnia po przejściu do stycznia i usuwa konkretną datę', async () => {
    calendar()
    await wrapper.get('[data-testid="dates-2031-12-31"]').trigger('click')
    await wrapper.get('[data-testid="dates-next"]').trigger('click')
    await wrapper.get('[data-testid="dates-2032-01-02"]').trigger('click')
    expect(wrapper.props().modelValue).toEqual(['2031-12-31', '2032-01-02'])
    expect(wrapper.get('[data-testid="dates-2032-01-02"]').attributes('aria-pressed')).toBe('true')
    await wrapper.get('[data-testid="dates-remove-2031-12-31"]').trigger('click')
    expect(wrapper.props().modelValue).toEqual(['2032-01-02'])
  })
  it('klawiatura przesuwa fokus przez granicę roku, Home/End i PageUp', async () => {
    calendar()
    const day = wrapper.get<HTMLButtonElement>('[data-date="2031-12-31"]')
    day.element.focus()
    await day.trigger('keydown', { key: 'ArrowRight' })
    await flushPromises()
    expect(document.activeElement?.getAttribute('data-date')).toBe('2032-01-01')
    await wrapper.get('[data-date="2032-01-01"]').trigger('click')
    expect(wrapper.props().modelValue).toEqual(['2032-01-01'])
    await wrapper.get('[data-date="2032-01-01"]').trigger('keydown', { key: 'Home' })
    expect(document.activeElement?.getAttribute('data-date')).toBe('2031-12-29')
    await wrapper.get('[data-date="2031-12-29"]').trigger('keydown', { key: 'End' })
    expect(document.activeElement?.getAttribute('data-date')).toBe('2032-01-04')
    await wrapper.get('[data-date="2032-01-04"]').trigger('keydown', { key: 'PageUp' })
    expect(document.activeElement?.getAttribute('data-date')).toBe('2031-12-01')
    expect(wrapper.findAll('button[tabindex="0"]')).toHaveLength(1)
  })
  it('nie dodaje ponad 62 daty i pozwala odznaczyć wybraną', async () => {
    const dates = Array.from(
      { length: 62 },
      (_, index) =>
        `2030-${String(Math.floor(index / 28) + 1).padStart(2, '0')}-${String((index % 28) + 1).padStart(2, '0')}`,
    )
    calendar(dates)
    const initialDay = wrapper.get<HTMLButtonElement>('[data-date="2031-12-31"]')
    expect(initialDay.element.disabled).toBe(false)
    expect(initialDay.attributes('aria-disabled')).toBe('true')
    initialDay.element.focus()
    await initialDay.trigger('click')
    expect(wrapper.props().modelValue).toHaveLength(62)
    await initialDay.trigger('keydown', { key: 'ArrowRight' })
    const target = wrapper.get<HTMLButtonElement>('[data-date="2032-01-01"]')
    expect(document.activeElement).toBe(target.element)
    expect(target.element.disabled).toBe(false)
    expect(target.element.tabIndex).toBe(0)
    expect(wrapper.findAll('button[tabindex="0"]')).toHaveLength(1)
    const tab = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true })
    target.element.dispatchEvent(tab)
    expect(tab.defaultPrevented).toBe(false)
    // jsdom nie realizuje natywnego Tab. Sprawdzamy pozostawiony, dostępny
    // punkt wejścia do siatki po oddaniu fokusu innemu elementowi.
    const nextMonth = wrapper.get<HTMLButtonElement>('[data-testid="dates-next"]')
    nextMonth.element.focus()
    expect(document.activeElement).toBe(nextMonth.element)
    wrapper.get<HTMLButtonElement>('button[data-date][tabindex="0"]').element.focus()
    expect(document.activeElement).toBe(target.element)
    await wrapper.get(`[data-testid="dates-remove-${dates[0]}"]`).trigger('click')
    expect(wrapper.props().modelValue).toHaveLength(61)
    expect(
      wrapper.get<HTMLButtonElement>('[data-date="2031-12-31"]').attributes('aria-disabled'),
    ).toBe('false')
  })
})
