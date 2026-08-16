import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AppShell from './AppShell.vue'

describe('AppShell', () => {
  it('renderuje szkielet aplikacji z nazwą produktu', () => {
    const wrapper = mount(AppShell)

    expect(wrapper.text()).toContain('Family Food Planner')
    expect(wrapper.find('header').exists()).toBe(true)
    expect(wrapper.find('main').exists()).toBe(true)
  })
})
