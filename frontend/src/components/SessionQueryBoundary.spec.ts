import { QueryClient, VueQueryPlugin, useQueryClient } from '@tanstack/vue-query'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import SessionQueryBoundary from './SessionQueryBoundary.vue'

describe('klient zapytań chronionej generacji', () => {
  it('dziedziczy pełne defaultOptions i zamyka własny lifecycle przy odmontowaniu', () => {
    const defaults = {
      queries: {
        networkMode: 'always' as const,
        staleTime: 30_000,
        retry: 1,
        refetchOnWindowFocus: false,
      },
      mutations: { networkMode: 'always' as const },
    }
    const parent = new QueryClient({ defaultOptions: defaults })
    let child!: QueryClient
    const probe = defineComponent({
      setup() {
        child = useQueryClient()
        return () => null
      },
    })
    const wrapper = mount(SessionQueryBoundary, {
      slots: { default: () => h(probe) },
      global: { plugins: [[VueQueryPlugin, { queryClient: parent }]] },
    })
    expect(child).not.toBe(parent)
    expect(child.getDefaultOptions()).toEqual(defaults)
    const unmount = vi.spyOn(child, 'unmount')
    child.setQueryData(['private'], 'A')
    wrapper.unmount()
    expect(child.getQueryData(['private'])).toBeUndefined()
    expect(unmount).toHaveBeenCalledOnce()
  })
})
