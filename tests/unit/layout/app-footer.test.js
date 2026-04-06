import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import AppFooter from '../../../src/components/layout/AppFooter.vue'
import { useUiStore } from '../../../src/stores/uiStore'
import { appMeta } from '../../../src/config/appMeta'

describe('AppFooter', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('renders repository, version and codename metadata', () => {
    const uiStore = useUiStore()
    uiStore.setLocale('en')

    const wrapper = mount(AppFooter)

    expect(wrapper.text()).toContain(appMeta.version)
    expect(wrapper.text()).toContain(appMeta.codename)
    expect(wrapper.text()).toContain(appMeta.author)

    const repositoryLink = wrapper.find('a')
    expect(repositoryLink.attributes('href')).toBe(appMeta.repositoryUrl)
  })
})
