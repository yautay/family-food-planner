import { expect, test } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'
import type { components } from '../src/api/generated.js'

import { cleanupE2eData, csrfHeaders } from './cleanup.js'

/**
 * Smoke statystyk (karta B13 §Tests): plan trzech dni + cel → `/statystyki` →
 * słupki, luka, średnia i status; zmiana zakresu przeładowuje dane.
 *
 * Dane seedujemy PRZEZ API (te same endpointy, których używa aplikacja), bo
 * klikanie trzech dni planu w UI sprawdzałoby jeszcze raz plan dnia, a nie
 * statystyki. Daty leżą w oknie zarezerwowanym dla E2E (lata 2030+), więc
 * presety „Tydzień"/„Miesiąc" (liczone od „dziś") nie mogłyby ich pokazać —
 * spec używa zakresu WŁASNEGO, dokładnie jak użytkownik patrzący w przeszłość.
 *
 * Cel żywieniowy należy do konta, a konto jest w E2E jedno, więc `valid_from`
 * ustawiamy W OKNIE testowym i usuwamy cel w `afterAll` — inaczej statusy
 * innych specow zaczęłyby zależeć od kolejności przebiegu.
 */
const PREFIX = 'E2E statystyki'
const RANGE_FROM = '2031-05-04'
const RANGE_TO = '2031-05-10'
/** Trzy dni z planem i celowa LUKA 2031-05-07 — na niej stoi asercja „brak planu". */
const PLANNED_DAYS = ['2031-05-05', '2031-05-06', '2031-05-08']
const TOUCHED_DATES = Array.from(
  { length: 7 },
  (_, offset) => `2031-05-${String(offset + 4).padStart(2, '0')}`,
)
const GOAL_VALID_FROM = '2031-05-01'
/** Produkt z seedu demo (`task db-seed-demo`) — trwały, z kompletem wartości. */
const SEED_PRODUCT = 'Mąka pszenna typ 500'

const API = '/api/v1'

let goalId: number | null = null

async function seedGoal(request: APIRequestContext): Promise<void> {
  const response = await request.post(`${API}/goals`, {
    headers: await csrfHeaders(request),
    data: { valid_from: GOAL_VALID_FROM, kcal: '2000', protein_g: '120.0' },
  })
  expect(response.status(), await response.text()).toBe(201)
  goalId = ((await response.json()) as { id: number }).id
}

async function seedPlan(request: APIRequestContext): Promise<void> {
  const headers = await csrfHeaders(request)
  const products = await request.get(
    `${API}/products?q=${encodeURIComponent(SEED_PRODUCT)}&limit=1`,
  )
  expect(products.ok(), await products.text()).toBe(true)
  const items = ((await products.json()) as { items: { id: number; name: string }[] }).items
  expect(
    items.length,
    `Seed demo musi zawierać „${SEED_PRODUCT}" (task db-seed-demo)`,
  ).toBeGreaterThan(0)
  const productId = items[0]!.id

  for (const day of PLANNED_DAYS) {
    const meal = await request.post(`${API}/plan/days/${day}/meals`, {
      headers,
      data: { name: `Obiad ${PREFIX}` },
    })
    expect(meal.status(), await meal.text()).toBe(201)
    const created = (await meal.json()) as { meals: { id: number; name: string }[] }
    const mealId = created.meals.find((entry) => entry.name === `Obiad ${PREFIX}`)!.id

    const item = await request.post(`${API}/plan/meals/${mealId}/items`, {
      headers,
      data: { product_id: productId, quantity: '500', unit: 'g' },
    })
    expect(item.status(), await item.text()).toBe(201)
  }
}

test.beforeAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX, dates: TOUCHED_DATES })
  await seedGoal(request)
  await seedPlan(request)
})

test.afterAll(async ({ request }) => {
  if (goalId !== null) {
    await request.delete(`${API}/goals/${goalId}`, { headers: await csrfHeaders(request) })
    goalId = null
  }
  await cleanupE2eData(request, { namePrefix: PREFIX, dates: TOUCHED_DATES })
})

test('statystyki: słupki dni, luka bez planu, średnia całego planu i odrębna historia celu i zmiana zakresu', async ({
  page,
}, testInfo) => {
  await page.goto('/statystyki')
  await expect(page.getByTestId('statystyki-page')).toBeVisible()

  // --- zakres własny w oknie E2E ---------------------------------------------------
  await page.getByTestId('stats-preset-custom').click()
  // Sama data „od" z lat 2031 daje zakres odwrócony (data „do" to jeszcze bieżący
  // tydzień), więc zapytanie leci dopiero po uzupełnieniu drugiego pola.
  await page.getByTestId('stats-from').fill(RANGE_FROM)
  const [loaded] = await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().includes('/stats/daily') && response.url().includes(`to=${RANGE_TO}`),
    ),
    page.getByTestId('stats-to').fill(RANGE_TO),
  ])
  expect(loaded.status(), await loaded.text()).toBe(200)

  // --- słupki dni z planem i LUKA dnia bez planu -----------------------------------
  await expect(page.getByTestId('stats-kcal-chart-bar-2031-05-05-kcal')).toBeVisible()
  await expect(page.getByTestId('stats-kcal-chart-bar-2031-05-06-kcal')).toBeVisible()
  await expect(page.getByTestId('stats-kcal-chart-bar-2031-05-08-kcal')).toBeVisible()
  await expect(page.getByTestId('stats-kcal-chart-gap-2031-05-07')).toBeVisible()
  await expect(page.getByTestId('stats-kcal-chart-bar-2031-05-07-kcal')).toHaveCount(0)

  // --- średnia dzienna + status wobec celu ----------------------------------------
  await expect(page.getByTestId('stats-days')).toContainText('3 z 7')
  await expect(page.getByTestId('stats-tile-kcal')).toBeVisible()
  const statsBody = (await loaded.json()) as components['schemas']['StatsDailyResponse']
  await expect(page.getByTestId('stats-tile-kcal')).toContainText(
    statsBody.summary.avg!.kcal.replace(/\.0+$/, ''),
  )
  await expect(page.getByTestId('stats-account-averages')).toContainText('2000')
  await expect(page.getByTestId('stats-status-kcal')).toHaveCount(0)
  await expect(page.getByTestId('stats-goal-legend')).toContainText('odczyt archiwalny')
  await expect(page.getByTestId('stats-semantics')).toContainText('cały plan')

  for (const width of [390, 1024]) {
    await page.setViewportSize({ width, height: 900 })
    await page.screenshot({
      path: testInfo.outputPath(`ux10-summary-kcal-${width}.png`),
      fullPage: true,
    })
  }

  // --- zakładka makroskładników ----------------------------------------------------
  await page.getByTestId('stats-tab-macros').click()
  await expect(page.getByTestId('stats-chart-macros')).toBeVisible()
  await expect(page.getByTestId('stats-tile-protein_g')).toBeVisible()

  for (const width of [390, 1024]) {
    await page.setViewportSize({ width, height: 900 })
    await page.screenshot({
      path: testInfo.outputPath(`ux10-summary-macros-${width}.png`),
      fullPage: true,
    })
  }

  // --- zmiana zakresu przeładowuje dane -------------------------------------------
  const [reloaded] = await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().includes('/stats/daily') && response.url().includes('to=2031-05-06'),
    ),
    page.getByTestId('stats-to').fill('2031-05-06'),
  ])
  expect(reloaded.status(), await reloaded.text()).toBe(200)
  await expect(page.getByTestId('stats-days')).toContainText('2 z 3')
  const [longRange] = await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().includes('/stats/daily') && response.url().includes('to=2031-08-03'),
    ),
    page.getByTestId('stats-to').fill('2031-08-03'),
  ])
  expect(longRange.status()).toBe(200)
  await expect(page.getByTestId('stats-days')).toContainText('3 z 92')
  await page.setViewportSize({ width: 390, height: 900 })
  const chart = page.getByRole('region', {
    name: 'Makroskładniki całego planu na dzień — przewijany wykres',
  })
  await expect(chart).toHaveAttribute('tabindex', '0')
  await chart.focus()
  await page.keyboard.press('End')
  const geometry = await page.locator('html').evaluate((element) => {
    const html = element as unknown as { scrollWidth: number; clientWidth: number }
    return { content: html.scrollWidth, viewport: html.clientWidth }
  })
  expect(geometry.content).toBeLessThanOrEqual(geometry.viewport + 1)
  await page.screenshot({
    path: testInfo.outputPath('ux10-summary-92days-390.png'),
    fullPage: true,
  })
  await page.getByTestId('stats-to').fill('2031-08-04')
  await expect(page.getByTestId('stats-error')).toContainText('92')
  await expect(page.getByTestId('stats-range-blocked')).toBeVisible()
})
