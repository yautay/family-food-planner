import { expect, test } from '@playwright/test'
import type { components } from '../src/api/generated.js'
import { cleanupE2eData, csrfHeaders } from './cleanup.js'

type Day = components['schemas']['DayRead']
const PREFIX = 'E2E UX07 tydzien'
const WEEK = '2031-12-29'
const SOURCE = '2031-12-30'
const FIRST_TARGET = '2031-12-31'
const SECOND_TARGET = '2032-01-01'
const DATES = [WEEK, SOURCE, FIRST_TARGET, SECOND_TARGET, '2032-01-02', '2032-01-03', '2032-01-04']
const recipeName = `${PREFIX} — Pełnoziarnista zapiekanka z pieczoną papryką, cukinią, serem i świeżymi ziołami`
let recipeId: number

test.beforeAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX, dates: DATES })
  const headers = await csrfHeaders(request)
  const recipe = await request.post('/api/v1/recipes', {
    headers,
    data: { name: recipeName, scope: 'private', base_servings: 1, instructions: '' },
  })
  expect(recipe.status()).toBe(201)
  recipeId = (await recipe.json()).id
  for (const [date, name] of [
    [SOURCE, `${PREFIX} Obiad`],
    [SECOND_TARGET, `${PREFIX} Istniejąca kolacja`],
  ]) {
    const response = await request.post(`/api/v1/plan/days/${date}/recipe-items`, {
      headers,
      data: { recipe_id: recipeId, new_meal_name: name, servings: '1' },
    })
    expect(response.status()).toBe(201)
  }
})
test.afterAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX, dates: DATES })
})

test('UX07: agenda, kopiowanie klawiaturą przez rok, dopisywanie i powroty', async ({
  page,
  request,
}, testInfo) => {
  await page.goto(`/tydzien/${WEEK}?selectedDate=${SOURCE}`)
  const grid = page.getByTestId('week-grid')
  await expect(grid).toBeVisible()
  await expect(page.getByTestId(`week-day-${SOURCE}`)).toContainText(recipeName)
  for (const width of [360, 768, 1024]) {
    await page.setViewportSize({ width, height: 900 })
    const layout = await grid.evaluate((node) => {
      const view = node.ownerDocument.defaultView!
      const days = Array.from<typeof node>(node.children).map((day) => {
        const box = day.getBoundingClientRect()
        return { left: box.left, top: box.top, right: box.right }
      })
      return {
        days,
        width: view.innerWidth,
        documentWidth: node.ownerDocument.documentElement.scrollWidth,
        columns: view.getComputedStyle(node).gridTemplateColumns,
      }
    })
    expect(layout.documentWidth).toBeLessThanOrEqual(width + 1)
    expect(layout.days[1]!.top).toBeGreaterThan(layout.days[0]!.top)
    expect(layout.days.every((day) => day.left >= 0 && day.right <= width + 1)).toBe(true)
    await testInfo.attach(`week-agenda-${width}.png`, {
      body: await page.screenshot({ fullPage: true }),
      contentType: 'image/png',
    })
  }
  await page.getByTestId('week-complete').click()
  await page.getByTestId('action-copy-day').click()
  const calendar = page.getByTestId('copy-day-dates')
  await expect(calendar).toBeVisible()
  await page.getByTestId(`copy-day-dates-${FIRST_TARGET}`).focus()
  await page.keyboard.press('Space')
  await page.keyboard.press('ArrowRight')
  await expect(page.getByTestId(`copy-day-dates-${SECOND_TARGET}`)).toBeFocused()
  await page.keyboard.press('Space')
  await expect(page.getByTestId(`copy-day-dates-${SECOND_TARGET}`)).toHaveAttribute(
    'aria-pressed',
    'true',
  )
  await expect(page.getByTestId('reuse-targets')).toContainText('01.01.2032 — Widoczne posiłki: 1')
  for (const width of [360, 768, 1024]) {
    await page.setViewportSize({ width, height: 900 })
    const panel = page.getByTestId('copy-day-dialog')
    await expect(panel).toBeVisible()
    await expect(page.getByTestId('copy-day-dialog-submit')).toBeEnabled()
    await calendar.scrollIntoViewIfNeeded()
    const geometry = await panel.evaluate((node) => {
      const view = node.ownerDocument.defaultView!
      const box = node.getBoundingClientRect()
      return {
        width: view.innerWidth,
        box: { left: box.left, right: box.right },
        overflowing: Array.from<typeof node>(node.querySelectorAll('*')).filter((element) => {
          const style = view.getComputedStyle(element)
          return (
            /auto|scroll/.test(style.overflowY) && element.scrollWidth > element.clientWidth + 1
          )
        }).length,
      }
    })
    expect(geometry.box.left).toBeGreaterThanOrEqual(0)
    expect(geometry.box.right).toBeLessThanOrEqual(width + 1)
    expect(geometry.overflowing).toBe(0)
    await testInfo.attach(`week-calendar-${width}.png`, {
      body: await page.screenshot(),
      contentType: 'image/png',
    })
    if (width === 360 || width === 1024) {
      await page.getByTestId('reuse-targets').scrollIntoViewIfNeeded()
      await expect(page.getByTestId('copy-day-dialog-submit')).toBeEnabled()
      await testInfo.attach(`week-preview-bottom-${width}.png`, {
        body: await page.screenshot(),
        contentType: 'image/png',
      })
      await calendar.scrollIntoViewIfNeeded()
    }
  }
  await page.getByTestId('copy-day-dialog-submit').click()
  await expect(page.getByTestId('copy-day-dialog')).toBeHidden()
  await expect(page.getByTestId('week-result')).toContainText(SECOND_TARGET)
  for (const date of [FIRST_TARGET, SECOND_TARGET]) {
    const response = await request.get(`/api/v1/plan/days/${date}`)
    expect(response.ok()).toBe(true)
    const day = (await response.json()) as Day
    expect(
      day.meals.some(
        (meal) =>
          meal.name === `${PREFIX} Obiad` && meal.items.some((item) => item.recipe_id === recipeId),
      ),
    ).toBe(true)
    if (date === SECOND_TARGET)
      expect(day.meals.some((meal) => meal.name === `${PREFIX} Istniejąca kolacja`)).toBe(true)
    expect(day.meals).toHaveLength(date === SECOND_TARGET ? 2 : 1)
  }
  const source = page.getByTestId(`week-day-${SOURCE}`)
  await source.getByRole('link', { name: recipeName }).click()
  await expect(page.getByTestId('recipe-back')).toHaveText('Wróć do tygodnia')
  await page.getByTestId('recipe-back').click()
  await expect(page).toHaveURL(
    new RegExp(`/tydzien/${WEEK}\\?selectedDate=${SOURCE}&from=${WEEK}&to=2032-01-04$`),
  )
  await expect(source).toHaveClass(/ring-2/)
  await source.getByRole('link', { name: recipeName }).click()
  await page.goBack()
  await expect(source).toHaveClass(/ring-2/)
  await page.getByTestId('week-shopping').click()
  await expect(page).toHaveURL(
    new RegExp(`/zakupy\\?selectedDate=${SOURCE}&from=${WEEK}&to=2032-01-04$`),
  )
  await expect(page.getByTestId('zakupy-date-from')).toHaveValue(WEEK)
  await expect(page.getByTestId('zakupy-date-to')).toHaveValue('2032-01-04')
})
