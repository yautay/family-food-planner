import { VueQueryPlugin, useMutation } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { advanceSessionGeneration } from '@/lib/sessionGeneration'

import { setUnauthorizedHandler } from './client'
import { downloadExport } from './transfer'

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthorizedHandler(undefined)
  document.cookie = 'csrf_token=; Max-Age=0; Path=/'
})

describe('eksport należy do generacji sesji rozpoczynającej request', () => {
  it.each(['headers-401', 'error-json', 'blob'] as const)(
    'spóźnione %s nie wylogowuje B ani nie pobiera pliku A',
    async (phase) => {
      let headers!: (value: Response) => void
      let body!: (value: unknown) => void
      const response = new Response('', { status: phase === 'blob' ? 200 : 401 })
      const bodyPromise = new Promise((resolve) => {
        body = resolve
      })
      if (phase === 'blob') vi.spyOn(response, 'blob').mockReturnValue(bodyPromise as Promise<Blob>)
      else vi.spyOn(response, 'json').mockReturnValue(bodyPromise)
      vi.stubGlobal(
        'fetch',
        vi.fn(
          () =>
            new Promise<Response>((resolve) => {
              headers = resolve
            }),
        ),
      )
      const unauthorized = vi.fn()
      const download = vi.fn()
      setUnauthorizedHandler(unauthorized)
      let start!: () => void
      const component = defineComponent({
        setup() {
          const mutation = useMutation({ mutationFn: () => downloadExport(), onSuccess: download })
          start = () => mutation.mutate(undefined)
          return () => null
        },
      })
      const wrapper = mount(component, { global: { plugins: [VueQueryPlugin] } })
      start()
      await flushPromises()
      if (phase !== 'headers-401') {
        headers(response)
        await flushPromises()
      }
      advanceSessionGeneration()
      if (phase === 'headers-401') headers(response)
      body(
        phase === 'blob'
          ? new Blob(['private-A'])
          : { error: { code: 'unauthorized', message: 'expired' } },
      )
      await flushPromises()
      expect(unauthorized).not.toHaveBeenCalled()
      expect(download).not.toHaveBeenCalled()
      wrapper.unmount()
    },
  )

  it('własny eksport zachowuje blob, nazwę i poprawną obsługę 401', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('zip-data', {
          headers: { 'Content-Disposition': 'attachment; filename="family.zip"' },
        }),
      ),
    )
    const result = await downloadExport()
    expect(result.filename).toBe('family.zip')
    expect(await result.blob.text()).toBe('zip-data')
    const unauthorized = vi.fn()
    setUnauthorizedHandler(unauthorized)
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'unauthorized', message: 'expired' } }), {
        status: 401,
      }),
    )
    await expect(downloadExport()).rejects.toMatchObject({ status: 401 })
    expect(unauthorized).toHaveBeenCalledOnce()
  })
})
