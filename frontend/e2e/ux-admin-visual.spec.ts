import { expect, test } from '@playwright/test'

import type { components } from '../src/api/generated.js'
import { PwaApi } from './ux-pwa-native-api.js'

test.use({ trace: 'off', video: 'off', screenshot: 'off' })

test('UX10: rzeczywiste ekrany administracji bez zmian danych', async ({
  page,
  baseURL,
}, testInfo) => {
  test.skip(process.env.UX_ADMIN_VISUAL !== '1', 'Jawny opt-in UX_ADMIN_VISUAL=1.')
  test.setTimeout(120_000)
  if (!baseURL || !['localhost', '127.0.0.1', '[::1]'].includes(new URL(baseURL).hostname))
    throw new Error('Odbiór administracji wyłącznie na localhost.')
  const api = new PwaApi(page.context(), baseURL)
  const response = await api.get('/api/v1/auth/me')
  expect(response.status()).toBe(200)
  const me = await response.json<components['schemas']['CurrentUser']>()
  expect(me.role).toBe('admin')
  const widths = [...new Set((process.env.UX_VISUAL_WIDTHS ?? '390,1024').split(',').map(Number))]
  if (widths.some((width) => !Number.isInteger(width) || width < 320 || width > 2560))
    throw new Error('Szerokość odbioru musi należeć do320–2560.')
  const failures: number[] = []
  page.on('response', (result) => {
    if (new URL(result.url()).pathname.startsWith('/api/v1/') && !result.ok())
      failures.push(result.status())
  })
  const pageErrors: string[] = []
  page.on('pageerror', () => pageErrors.push('Błąd skryptu strony'))
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 })
    for (const [label, route, testId, endpoint] of [
      ['users', '/admin/uzytkownicy', 'admin-users-page', '/api/v1/admin/users'],
      ['households', '/admin/rodziny', 'admin-households-page', '/api/v1/admin/households'],
      ['verification', '/admin/weryfikacja', 'admin-weryfikacja-page', '/api/v1/products'],
      ['data', '/admin/dane', 'admin-dane-page', null],
    ] as const) {
      const loaded = endpoint
        ? page.waitForResponse(
            (result) =>
              new URL(result.url()).pathname === endpoint && result.request().method() === 'GET',
          )
        : null
      await page.goto(route)
      if (loaded) expect((await loaded).ok()).toBe(true)
      await expect(page.getByTestId(testId)).toBeVisible()
      await expect(page.locator('[role="alert"]')).toHaveCount(0)
      await page.locator('html').evaluate(async (element) => {
        await element.ownerDocument.fonts.ready
      })
      const geometry = await page.locator('html').evaluate((element) => ({
        scroll: element.scrollWidth,
        viewport: element.ownerDocument.defaultView!.innerWidth,
      }))
      expect(geometry.scroll, `${label}: przepełnienie strony`).toBeLessThanOrEqual(
        geometry.viewport + 1,
      )
      expect(failures, `${label}: błędy rzeczywistych API`).toEqual([])
      expect(pageErrors, `${label}: błędy skryptu`).toEqual([])
      for (const fullPage of [false, true])
        await testInfo.attach(`admin-${label}-${width}-${fullPage ? 'full' : 'viewport'}.png`, {
          body: await page.screenshot({ fullPage, animations: 'disabled', caret: 'hide' }),
          contentType: 'image/png',
        })
    }
  }
})
