import { h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ShoppingChecklistSection from './ShoppingChecklistSection.vue'

describe('ShoppingChecklistSection', () => {
  it('zachowuje cel fokusu także po disabled i utracie fokusu przed optimistic collapse', async () => {
    const wrapper = mount(ShoppingChecklistSection, {
      attachTo: document.body,
      props: { name: 'Warzywa', items: [{ id: 1, checked: false, already_have: false }] },
      slots: {
        item: ({ collapsed }) =>
          h('li', { class: collapsed ? 'shopping-item-collapsed' : '' }, [
            h('input', { type: 'checkbox' }),
          ]),
      },
    })
    try {
      const input = wrapper.get('input')
      input.element.focus()
      await input.trigger('change')
      input.element.disabled = true
      input.element.blur()
      await wrapper.setProps({ items: [{ id: 1, checked: true, already_have: false }] })
      await flushPromises()
      expect(document.activeElement).toBe(wrapper.get('button').element)
    } finally {
      wrapper.unmount()
    }
  })
  it('przenosi fokus z chowanego checkboxa do rozwijania jego kategorii', async () => {
    const wrapper = mount(ShoppingChecklistSection, {
      attachTo: document.body,
      props: { name: 'Warzywa', items: [{ id: 1, checked: false, already_have: false }] },
      slots: {
        item: ({ collapsed }) =>
          h('li', { class: collapsed ? 'shopping-item-collapsed' : '' }, [
            h('input', { type: 'checkbox' }),
          ]),
      },
    })
    try {
      wrapper.get('input').element.focus()
      await wrapper.setProps({ items: [{ id: 1, checked: true, already_have: false }] })
      await flushPromises()
      expect(document.activeElement).toBe(wrapper.get('button').element)
    } finally {
      wrapper.unmount()
    }
  })
  it('zwija tylko kupione, bez przenoszenia wierszy i bez chowania already_have', async () => {
    const wrapper = mount(ShoppingChecklistSection, {
      props: {
        name: 'Warzywa',
        items: [
          { id: 7, checked: true, already_have: false },
          { id: 2, checked: false, already_have: false },
          { id: 9, checked: true, already_have: true },
        ],
      },
      slots: {
        item: ({ item, collapsed }) =>
          h('li', { class: collapsed ? 'shopping-item-collapsed' : '', 'data-id': item.id }),
      },
    })
    expect(wrapper.findAll('li').map((row) => row.attributes('data-id'))).toEqual(['7', '2', '9'])
    expect(
      wrapper.findAll('.shopping-item-collapsed').map((row) => row.attributes('data-id')),
    ).toEqual(['7'])
    const toggle = wrapper.get('button')
    expect(toggle.text()).toContain('Kupione (1)')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(wrapper.get('ul').attributes('id')).toBe(toggle.attributes('aria-controls'))
    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('.shopping-item-collapsed').exists()).toBe(false)
    await toggle.trigger('click')
    expect(wrapper.find('.shopping-item-collapsed').exists()).toBe(true)
  })
})
