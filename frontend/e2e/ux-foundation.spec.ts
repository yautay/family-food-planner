import { expect, test } from '@playwright/test'
import { cleanupE2eData } from './cleanup.js'

test('UX01: druk zachowuje datę i usuwa dekorację oraz nawigację', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/plan-dnia/2032-03-01')
  await expect(page.getByTestId('plan-add-meal')).toBeVisible()
  const date = page.getByTestId('plan-date')
  const decoration = page.getByTestId('header-decoration')
  const sidebar = page.getByTestId('nav-sidebar')
  await expect(date).toBeVisible()
  await expect(date).toContainText('2032-03-01')
  await expect(decoration).toBeVisible()
  await expect(sidebar).toBeVisible()
  await page.emulateMedia({ media: 'print' })
  await expect(decoration).toBeHidden()
  await expect(sidebar).toBeHidden()
  await expect(date).toBeVisible()
  await expect(date).toContainText('2032-03-01')
  await expect(date).toHaveCSS('color', 'rgb(0, 0, 0)')
  await page.screenshot({ path: testInfo.outputPath('foundation-print.png'), fullPage: true })
})

/**
 * Rzeczywisty formularz tygodnia. Odczyty korzystają z normalnej sesji i API.
 * POST jest przechwycony przed serwerem: test kontroluje pending i błąd,
 * nie zapisuje szablonu ani nie sprząta cudzych danych.
 */
for (const width of [360, 1440]) {
  test(`UX01: klawiatura, walidacja i zachowany formularz — ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 900 })
    let requests = 0
    let release: () => void = () => {}
    const waiting = new Promise<void>((resolve) => {
      release = resolve
    })
    await page.route('**/api/v1/templates/days', async (route) => {
      if (route.request().method() !== 'POST') return route.continue()
      requests += 1
      await waiting
      await route.fulfill({
        status: 503,
        json: {
          error: {
            code: 'service_unavailable',
            message: 'Test UX01: zapis się nie powiódł.',
            details: {},
          },
        },
      })
    })
    try {
      await page.goto('/tydzien/2032-03-01')
      await expect(page.getByTestId('plan-tygodnia-page')).toBeVisible()
      const opener = page.getByTestId('action-template-save')
      await opener.focus()
      await page.keyboard.press('Enter')
      const panel = page.getByTestId('template-save-dialog')
      const submit = page.getByTestId('template-save-dialog-submit')
      const name = page.getByTestId('template-name')
      await expect(panel).toHaveRole('dialog')
      await expect(panel.locator(':focus')).toHaveCount(1)
      await expect(submit).toBeDisabled()
      // Tab i Shift+Tab pozostają wewnątrz obsługiwanego przez Reka modalu.
      for (let index = 0; index < 15; index += 1) {
        await page.keyboard.press(index % 3 === 0 ? 'Shift+Tab' : 'Tab')
        await expect(panel.locator(':focus')).toHaveCount(1)
      }
      await name.fill('E2E UX01 — Dzień Łucji i Żanety')
      await page.screenshot({ path: testInfo.outputPath(`panel-filled-${width}.png`) })
      await name.press('Enter')
      await expect.poll(() => requests).toBe(1)
      await expect(submit).toBeDisabled()
      await expect(name).toBeDisabled()
      await expect(page.getByTestId('template-save-dialog-cancel')).toBeDisabled()
      await page.keyboard.press('Escape')
      await expect(panel).toBeVisible()
      expect(requests).toBe(1)
      await page.screenshot({ path: testInfo.outputPath(`panel-pending-${width}.png`) })
      release()
      await expect(page.getByTestId('template-save-dialog-error')).toHaveText(
        'Test UX01: zapis się nie powiódł.',
      )
      await expect(name).toHaveValue('E2E UX01 — Dzień Łucji i Żanety')
      await expect(page.getByTestId('template-save-dialog-error')).toBeFocused()
      await expect(submit).toBeEnabled()
      await page.screenshot({ path: testInfo.outputPath(`panel-error-${width}.png`) })
      await page.keyboard.press('Escape')
      await expect(panel).toBeHidden()
      await expect(opener).toBeFocused()
    } finally {
      release()
    }
  })
}

test.describe('UX01: przyciski w rzeczywistej siatce planu', () => {
  const prefix = 'E2E UX01 siatka'
  const dates = ['2032-05-03', '2032-05-04']
  test.beforeAll(async ({ request }) => {
    await cleanupE2eData(request, { namePrefix: prefix, dates })
  })
  test.afterAll(async ({ request }) => {
    await cleanupE2eData(request, { namePrefix: prefix, dates })
  })
  for (const [index, width] of [360, 1440].entries()) {
    test(`przyciski zachowują naturalną wysokość i rosną wraz z tekstem — ${width}px`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 900 })
      await page.goto(`/plan-dnia/${dates[index]}`)
      await expect(page.getByTestId('plan-dnia-page')).toBeVisible()
      await page.getByTestId('plan-add-meal').click()
      await page.getByTestId('meal-name-input').fill(`${prefix} — Późny obiad`)
      await page.getByTestId('meal-submit').click()
      const controls = [
        page.getByTestId('plan-add-meal'),
        page.getByTestId('plan-copy-open'),
        page.locator('[data-testid^="meal-add-item-"]').first(),
      ]
      for (const control of controls) {
        await expect(control).toBeVisible()
        const box = await control.boundingBox()
        expect(box).not.toBeNull()
        expect(box!.height).toBeGreaterThanOrEqual(44)
        expect(box!.height).toBeLessThanOrEqual(60)
      }
      await page.screenshot({
        path: testInfo.outputPath(`day-grid-buttons-${width}.png`),
        fullPage: true,
      })
      await page.addStyleTag({
        // Powiększamy także interlinię: samo font-size zostawiłoby stałe 20 px
        // z text-sm. Transition-all zmienia font przez 150 ms, więc pomiar
        // wykonujemy dopiero po osiągnięciu docelowych stylów, bez stałego sleep.
        content:
          '[data-testid="plan-add-meal"] { font-size: 32px; line-height: 1.5; max-width: 180px; }',
      })
      await expect(controls[0]!).toHaveCSS('font-size', '32px')
      await expect(controls[0]!).toHaveCSS('line-height', '48px')
      await expect
        .poll(async () => (await controls[0]!.boundingBox())?.height ?? 0)
        .toBeGreaterThan(60)
      await page.screenshot({
        path: testInfo.outputPath(`day-grid-buttons-large-text-${width}.png`),
        fullPage: true,
      })
    })
  }
})
