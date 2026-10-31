import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SettingsTabs from './SettingsTabs.vue'
import type { SettingsSection } from './SettingsTabs.vue'

describe('Sekcje ustawień z klawiatury', () => {
  it('strzałki, Home i End wybierają sekcję, przenoszą fokus i zawijają wybór', async () => {
    const host = defineComponent({
      setup() {
        const active = ref<SettingsSection>('family')
        return () =>
          h(SettingsTabs, {
            modelValue: active.value,
            'onUpdate:modelValue': (value) => {
              active.value = value
            },
          })
      },
    })
    const wrapper = mount(host, { attachTo: document.body })
    try {
      const family = wrapper.get<HTMLButtonElement>('[data-testid="settings-tab-family"]')
      family.element.focus()
      await family.trigger('keydown', { key: 'ArrowRight' })
      expect(document.activeElement?.id).toBe('settings-tab-goals')
      expect(wrapper.get('[data-testid="settings-tab-goals"]').attributes('aria-selected')).toBe(
        'true',
      )
      await wrapper.get('[data-testid="settings-tab-goals"]').trigger('keydown', { key: 'End' })
      expect(document.activeElement?.id).toBe('settings-tab-data')
      await wrapper
        .get('[data-testid="settings-tab-data"]')
        .trigger('keydown', { key: 'ArrowRight' })
      expect(document.activeElement?.id).toBe('settings-tab-family')
      await family.trigger('keydown', { key: 'ArrowLeft' })
      expect(document.activeElement?.id).toBe('settings-tab-data')
      await wrapper.get('[data-testid="settings-tab-data"]').trigger('keydown', { key: 'Home' })
      expect(document.activeElement?.id).toBe('settings-tab-family')
      expect(wrapper.findAll('[tabindex="0"]')).toHaveLength(1)
      expect(family.attributes('aria-controls')).toBe('settings-panel-family')
    } finally {
      wrapper.unmount()
    }
  })
})
