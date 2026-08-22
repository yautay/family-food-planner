import { expect, test } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'

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

test('statystyki: słupki dni, luka bez planu, średnia ze statusem i zmiana zakresu', async ({
  page,
}) => {
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
  await expect(page.getByTestId('stats-tile-kcal')).toContainText('2000')
  await expect(page.getByTestId('stats-status-kcal')).toBeVisible()

  // --- zakładka makroskładników ----------------------------------------------------
  await page.getByTestId('stats-tab-macros').click()
  await expect(page.getByTestId('stats-chart-macros')).toBeVisible()
  await expect(page.getByTestId('stats-tile-protein_g')).toBeVisible()

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
})
