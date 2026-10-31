import {
  expect,
  test,
  type APIRequestContext,
  type Page,
  type Route,
  type TestInfo,
} from '@playwright/test'
import type { components } from '../src/api/generated.js'
import { decimalsEqual } from '../src/lib/decimal.js'
import { cleanupE2eData, csrfHeaders } from './cleanup.js'

type Detail = components['schemas']['RecipeDetail']
type Recipes = components['schemas']['RecipeListResponse']
type Products = components['schemas']['ProductListResponse']
type Tags = components['schemas']['TagListResponse']
type Created = components['schemas']['RecipeItemCreatedResponse']
type Day = components['schemas']['DayRead']
type Rating = components['schemas']['RatingResponse']

const PREFIX = 'E2E UX04 ksiegakataloguxcztery'
const SEARCH = 'ksiegakataloguxcztery'
const DATES = ['2036-05-12', '2036-05-13', '2036-05-14', '2036-05-15']
const records: Detail[] = []
let favoriteId: number

async function purge(request: APIRequestContext): Promise<void> {
  await cleanupE2eData(request, { namePrefix: PREFIX, dates: DATES })
  // Helper historyczny czyta pierwsze 200. Ten katalog może mieć więcej stron.
  const ownIds: number[] = []
  for (let offset = 0; ; offset += 200) {
    const response = await request.get('/api/v1/recipes', {
      params: { limit: 200, offset, include_archived: true },
    })
    expect(response.ok()).toBe(true)
    const page = (await response.json()) as Recipes
    ownIds.push(...page.items.filter((item) => item.name.startsWith(PREFIX)).map((item) => item.id))
    if (page.items.length === 0 || offset + page.items.length >= page.total) break
  }
  const headers = await csrfHeaders(request)
  for (const id of ownIds) {
    const response = await request.delete(`/api/v1/recipes/${id}`, { headers })
    expect(response.status()).toBe(204)
  }
}

test.beforeAll(async ({ request }, testInfo) => {
  testInfo.setTimeout(90_000)
  await purge(request)
  const headers = await csrfHeaders(request)
  const tagsResponse = await request.get('/api/v1/tags')
  expect(tagsResponse.ok()).toBe(true)
  const tags = (await tagsResponse.json()) as Tags
  const favorite = tags.items.find((tag) => tag.name === 'ulubione')
  expect(favorite, 'Wymagany istniejący systemowy tag ulubione').toBeTruthy()
  favoriteId = favorite!.id
  const productsResponse = await request.get('/api/v1/products?limit=200&offset=0')
  expect(productsResponse.ok()).toBe(true)
  const products = (await productsResponse.json()) as Products
  const product = products.items.find((item) => item.measure_kind === 'mass' && !item.is_archived)
  expect(product, 'Rzeczywisty produkt masowy do sprawdzenia skalowania').toBeTruthy()
  records.length = 0
  for (let index = 0; index < 55; index += 1) {
    const response = await request.post('/api/v1/recipes', {
      headers,
      data: {
        name: `${PREFIX} ${String(index + 1).padStart(3, '0')} — Pełnoziarnista zapiekanka z pieczoną papryką, cukinią i świeżymi ziołami`,
        scope: 'private',
        instructions: '1. Przygotuj składniki.\n2. Upiecz i podaj ciepłe.',
        base_servings: 2,
        prep_time_min: index === 52 ? 31 : index === 53 ? null : 30,
        tag_ids: [favoriteId],
        ingredients:
          index === 54
            ? [{ product_id: product!.id, quantity: '200', unit: 'g', note: 'dokładnie odważone' }]
            : [],
      },
    })
    expect(response.status(), await response.text()).toBe(201)
    records.push((await response.json()) as Detail)
  }
})
test.afterAll(async ({ request }, testInfo) => {
  testInfo.setTimeout(90_000)
  await purge(request)
})

async function assertNoOverflow(page: Page): Promise<void> {
  const geometry = await page.evaluate<{
    width: number
    document: number
    cards: { client: number; scroll: number }[]
  }>(`(() => ({
    width: innerWidth,
    document: document.documentElement.scrollWidth,
    cards: [...document.querySelectorAll('[data-testid^="recipe-card-"]')].map((node) => ({
      client: node.clientWidth, scroll: node.scrollWidth,
    })),
  }))()`)
  expect(geometry.document).toBeLessThanOrEqual(geometry.width + 1)
  expect(geometry.cards.filter((item) => item.scroll > item.client + 1)).toEqual([])
}
async function saveToDay(page: Page, date: string, recipeId: number): Promise<Created> {
  await expect(page.getByTestId('planning-date')).toHaveValue(date)
  await page.getByTestId('planning-meal-name').fill(`${PREFIX} Późny obiad`)
  await page.getByTestId('planning-servings').fill('2,2')
  const saved = page.waitForResponse(
    (response) =>
      response.url().includes(`/plan/days/${date}/recipe-items`) &&
      response.request().method() === 'POST',
  )
  await page.getByTestId('recipe-planning-submit').click()
  const response = await saved
  expect(response.status()).toBe(201)
  const body = (await response.json()) as Created
  expect(body.day.day).toBe(date)
  expect(body.meal_id).toBeGreaterThan(0)
  expect(body.item_id).toBeGreaterThan(0)
  const savedItem = body.day.meals
    .find((meal) => meal.id === body.meal_id)
    ?.items.find((item) => item.id === body.item_id)
  expect(savedItem).toMatchObject({
    recipe_id: recipeId,
    servings_split: [],
  })
  expect(decimalsEqual(savedItem!.servings, '2.2')).toBe(true)
  await expect(page).toHaveURL(new RegExp(`/plan-dnia/${date}`))
  await expect(page.getByTestId(`plan-item-servings-${body.item_id}`)).toBeVisible()
  const persisted = await page.request.get(`/api/v1/plan/days/${date}`)
  expect(persisted.ok()).toBe(true)
  const day = (await persisted.json()) as Day
  expect(
    day.meals
      .find((meal) => meal.id === body.meal_id)
      ?.items.find((item) => item.id === body.item_id)?.recipe_id,
  ).toBe(recipeId)
  return body
}

for (const [index, width] of [360, 1440].entries()) {
  test(`UX04 URL, serwerowe filtry, druga strona, powrót ze scrollem i planowanie — ${width}px`, async ({
    page,
  }) => {
    test.setTimeout(60_000)
    const date = DATES[index]!
    const last = records[54]!
    await page.setViewportSize({ width, height: 900 })
    await page.goto(`/przepisy?selectedDate=${date}&from=2036-05-12&to=2036-05-18`)
    await page.getByTestId('recipes-search').fill(SEARCH)
    await expect(page).toHaveURL(new RegExp(`q=${SEARCH}`))
    await page.getByTestId('recipes-filters-toggle').click()
    await page.getByTestId('recipes-scope-private').click()
    await page.getByTestId(`recipes-tag-${favoriteId}`).click()
    await page.getByTestId('recipes-filters-toggle').click()
    await page.getByTestId('recipes-quick').click()
    await expect(page.getByTestId('recipes-total')).toContainText('50 z 53')
    await expect(page.getByTestId(`recipe-card-${records[52]!.id}`)).toHaveCount(0)
    await expect(page.getByTestId(`recipe-card-${records[53]!.id}`)).toHaveCount(0)
    await page.getByTestId('recipes-load-more').click()
    await expect(page.getByTestId('recipes-total')).toContainText('53 z 53')
    await expect(page.getByTestId(`recipe-card-${last.id}`)).toBeVisible()
    await expect(page.getByTestId(`recipe-card-${last.id}`).getByRole('heading')).toHaveText(
      last.name,
    )
    await expect(
      page.getByTestId(`recipe-card-${last.id}`).getByTestId('recipe-image-fallback'),
    ).toBeVisible()
    await assertNoOverflow(page)
    const catalogURL = page.url()
    await page.getByTestId(`recipe-open-${last.id}`).scrollIntoViewIfNeeded()
    const scroll = await page.evaluate<number>('scrollY')
    expect(scroll).toBeGreaterThan(100)
    await page.getByTestId(`recipe-open-${last.id}`).click()
    await expect(page.getByTestId('recipe-name')).toHaveText(last.name)
    await expect(page.getByTestId('recipe-ingredients')).toBeVisible()
    await expect(page.getByTestId('recipe-instructions')).toBeVisible()
    await page.getByTestId('servings-increase').click()
    await expect(page.getByTestId('recipe-scaled-for')).toContainText('1,5')
    await expect(page.getByTestId(`recipe-ingredient-${last.ingredients[0]!.id}`)).toContainText(
      '150 g',
    )
    const rating = index === 0 ? 4 : 5
    const rated = page.waitForResponse(
      (response) =>
        response.url().includes(`/recipes/${last.id}/rating`) &&
        response.request().method() === 'PUT',
    )
    await page.getByRole('radio', { name: `Ocena ${rating} na 5` }).focus()
    await page.keyboard.press('Space')
    const ratingResponse = await rated
    expect(ratingResponse.status()).toBe(200)
    expect(((await ratingResponse.json()) as Rating).my_rating).toBe(rating)
    await expect(page.getByTestId('recipe-success')).toContainText('Ocena została zapisana')
    await expect(page.getByRole('radio', { name: `Ocena ${rating} na 5` })).toBeChecked()
    await page.getByTestId('recipe-back').click()
    await expect(page).toHaveURL(catalogURL)
    await expect(page.getByTestId('recipes-total')).toContainText('53 z 53')
    await expect.poll(() => page.evaluate<number>('scrollY')).toBeGreaterThan(scroll - 80)
    await expect(page.getByTestId('recipes-search')).toHaveValue(SEARCH)
    await expect(page.getByTestId('recipes-quick')).toHaveAttribute('aria-pressed', 'true')
    await page.getByTestId(`recipe-plan-${last.id}`).focus()
    await page.keyboard.press('Enter')
    await expect(page.getByTestId('recipe-planning')).toHaveAttribute('role', 'dialog')
    await page.keyboard.press('Escape')
    await expect(page.getByTestId(`recipe-plan-${last.id}`)).toBeFocused()
    await page.keyboard.press('Enter')
    await saveToDay(page, date, last.id)

    // Drugi rzeczywisty zapis zaczyna się na szczególe; data może zmienić się w panelu.
    await page.goto(`/przepisy/${last.id}?selectedDate=${date}`)
    await page.getByTestId('recipe-plan').click()
    const secondDate = DATES[index + 2]!
    await page.getByTestId('planning-date').fill(secondDate)
    await saveToDay(page, secondDate, last.id)
    await page.reload()
    await expect(page.getByTestId('plan-dnia-page')).toBeVisible()
    await expect(
      page.getByTestId('plan-dnia-page').getByRole('heading', { name: last.name, exact: true }),
    ).toBeVisible()
  })
}

test('UX04 błąd pierwszego odczytu, refetch z cache i kolejnej strony nie udają pustych danych', async ({
  page,
}) => {
  test.setTimeout(60_000)
  await page.setViewportSize({ width: 390, height: 900 })
  let blocked: 'all' | 'next' | null = 'all'
  const handler = (route: Route) => {
    const url = new URL(route.request().url())
    if (blocked === 'all' || (blocked === 'next' && url.searchParams.get('offset') === '50'))
      return route.abort('failed')
    return route.continue()
  }
  await page.route('**/api/v1/recipes?*', handler)
  await page.goto(`/przepisy?q=${SEARCH}&scope=private`)
  await expect(page.getByTestId('recipes-error')).toBeVisible()
  await expect(page.getByTestId('recipes-empty')).toHaveCount(0)
  blocked = null
  await page.getByTestId('recipes-error').getByRole('button').click()
  await expect(page.getByTestId('recipes-total')).toContainText('50 z 55')
  blocked = 'next'
  await page.getByTestId('recipes-load-more').click()
  await expect(page.getByTestId('recipes-load-more-error')).toBeVisible()
  await expect(page.locator('[data-testid^="recipe-card-"]')).toHaveCount(50)
  blocked = null
  await page.getByTestId('recipes-load-more').click()
  await expect(page.getByTestId('recipes-total')).toContainText('55 z 55')
  blocked = 'all'
  await page.getByTestId('recipes-refresh').click()
  await expect(page.getByTestId('recipes-refresh-error')).toBeVisible()
  await expect(page.locator('[data-testid^="recipe-card-"]')).toHaveCount(55)
  await expect(page.getByTestId('recipes-empty')).toHaveCount(0)
  blocked = null
  await page.getByTestId('recipes-refresh-error').getByRole('button').click()
  await expect(page.getByTestId('recipes-refresh-error')).toHaveCount(0)
  await expect(page.getByTestId('recipes-total')).toContainText('55 z 55')
  await page.unroute('**/api/v1/recipes?*', handler)
})

test('UX04 nowy i edycja zachowują filtry oraz datę po zapisie i powrocie z edytora', async ({
  page,
}) => {
  test.setTimeout(60_000)
  const date = DATES[0]!
  const catalogURL = `/przepisy?q=${SEARCH}&tag=${favoriteId}&scope=private&prep_time_max=30&selectedDate=${date}&from=2036-05-12&to=2036-05-18`
  function expectContext(): void {
    const query = new URL(page.url()).searchParams
    expect(query.get('q')).toBe(SEARCH)
    expect(query.getAll('tag')).toEqual([String(favoriteId)])
    expect(query.get('scope')).toBe('private')
    expect(query.get('prep_time_max')).toBe('30')
    expect(query.get('selectedDate')).toBe(date)
    expect(query.get('from')).toBe('2036-05-12')
    expect(query.get('to')).toBe('2036-05-18')
  }
  await page.goto(catalogURL)
  await page.getByTestId('recipes-add').click()
  await expect(page.getByTestId('przepis-edytor-page')).toBeVisible()
  await page.getByTestId('recipe-editor-back').click()
  await expect(page.getByTestId('przepisy-page')).toBeVisible()
  expectContext()

  await page.getByTestId('recipes-add').click()
  await expect(page.getByTestId('przepis-edytor-page')).toBeVisible()
  const name = `${PREFIX} nowy przepis z kontekstem`
  await page.getByTestId('recipe-name').fill(name)
  const created = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/v1/recipes') && response.request().method() === 'POST',
  )
  await page.getByTestId('recipe-submit').click()
  const response = await created
  expect(response.status()).toBe(201)
  const recipe = (await response.json()) as Detail
  await expect(page.getByTestId('recipe-name')).toHaveText(name)
  expectContext()
  await page.getByTestId('recipe-plan').click()
  await expect(page.getByTestId('planning-date')).toHaveValue(date)
  await page.keyboard.press('Escape')

  await page.getByTestId('recipe-edit').click()
  await expect(page.getByTestId('przepis-edytor-page')).toBeVisible()
  const editedName = `${PREFIX} przepis po edycji z kontekstem`
  await page.getByTestId('recipe-name').fill(editedName)
  const updated = page.waitForResponse(
    (saved) =>
      saved.url().endsWith(`/api/v1/recipes/${recipe.id}`) && saved.request().method() === 'PUT',
  )
  await page.getByTestId('recipe-submit').click()
  expect((await updated).status()).toBe(200)
  await expect(page.getByTestId('recipe-name')).toHaveText(editedName)
  expectContext()
  await page.getByTestId('recipe-plan').click()
  await expect(page.getByTestId('planning-date')).toHaveValue(date)
  await page.keyboard.press('Escape')

  await page.getByTestId('recipe-edit').click()
  await expect(page.getByTestId('przepis-edytor-page')).toBeVisible()
  await page.getByTestId('recipe-editor-back').click()
  await expect(page.getByTestId('przepisy-page')).toBeVisible()
  expectContext()
})

async function assertFirstRecipeHierarchy(page: Page, testInfo: TestInfo): Promise<void> {
  const layout = await page.evaluate<{
    width: number
    height: number
    scrollY: number
    usableBottom: number
    title: { top: number; bottom: number } | null
    action: { top: number; bottom: number } | null
    summary: { width: number; height: number } | null
  }>(`(() => {
    const card = document.querySelector('[data-testid^="recipe-card-"]');
    const rect = (node) => node ? (() => { const r = node.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, width: r.width, height: r.height }; })() : null;
    const nav = rect(document.querySelector('[data-testid="nav-bottom"]'));
    return { width: innerWidth, height: innerHeight, scrollY, usableBottom: nav && nav.height > 0 ? Math.min(nav.top, innerHeight) : innerHeight,
      title: rect(card?.querySelector('h2')), action: rect(card?.querySelector('[data-testid^="recipe-plan-"]')),
      summary: rect(document.querySelector('[data-testid="recipes-filters-toggle"]')) };
  })()`)
  await testInfo.attach('recipes-first-viewport-geometry.json', {
    body: JSON.stringify(layout, null, 2),
    contentType: 'application/json',
  })
  expect.soft(layout.scrollY, 'Domyślny katalog jest sprawdzany przed przewinięciem').toBe(0)
  expect.soft(layout.summary?.width).toBeGreaterThanOrEqual(44)
  expect.soft(layout.summary?.height).toBeGreaterThanOrEqual(44)
  expect.soft(layout.title?.top).toBeGreaterThanOrEqual(0)
  expect
    .soft(layout.title?.bottom, 'Pełny tytuł pierwszego dania nad rzeczywistą dolną nawigacją')
    .toBeLessThanOrEqual(layout.usableBottom)
  expect.soft(layout.action?.top).toBeGreaterThanOrEqual(0)
  expect
    .soft(layout.action?.bottom, 'Zaplanuj pierwszej karty nad rzeczywistą dolną nawigacją')
    .toBeLessThanOrEqual(layout.usableBottom)
}

for (const width of [390, 1440]) {
  test(`UX04 pierwszy ekran pokazuje danie, dodatkowe filtry otwierają się klawiaturą — ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/przepisy')
    const cards = page.locator('[data-testid^="recipe-card-"]')
    await expect(cards.first().getByRole('heading')).toBeVisible()
    const panel = page.getByTestId('recipes-filters')
    const summary = page.getByTestId('recipes-filters-toggle')
    await expect(panel).not.toHaveAttribute('open', '')
    await expect(page.getByTestId('recipes-scope-private')).toBeHidden()
    await assertFirstRecipeHierarchy(page, testInfo)
    const closedPath = testInfo.outputPath(`recipes-closed-${width}.png`)
    await page.screenshot({ path: closedPath, fullPage: false })
    await testInfo.attach(`recipes-closed-${width}.png`, {
      path: closedPath,
      contentType: 'image/png',
    })

    await summary.focus()
    await page.keyboard.press('Enter')
    await expect(panel).toHaveAttribute('open', '')
    await expect(page.getByTestId('recipes-scope-private')).toBeVisible()
    await expect(page.getByTestId(`recipes-tag-${favoriteId}`)).toBeVisible()
    const expandedPath = testInfo.outputPath(`recipes-expanded-${width}.png`)
    await page.screenshot({ path: expandedPath, fullPage: false })
    await testInfo.attach(`recipes-expanded-${width}.png`, {
      path: expandedPath,
      contentType: 'image/png',
    })

    await page.getByTestId('recipes-scope-private').click()
    await expect(page).toHaveURL(/scope=private/)
    const filtered = page.waitForResponse((response) => {
      const url = new URL(response.url())
      return (
        url.pathname === '/api/v1/recipes' &&
        url.searchParams.get('scope') === 'private' &&
        url.searchParams.getAll('tag').includes(String(favoriteId))
      )
    })
    await page.getByTestId(`recipes-tag-${favoriteId}`).click()
    const response = await filtered
    expect(response.status()).toBe(200)
    const data = (await response.json()) as Recipes
    await expect(cards.first().getByRole('heading')).toHaveText(data.items[0]!.name)
    await expect(page.getByTestId('recipes-total')).toContainText(`50 z ${data.total}`)
    const query = new URL(page.url()).search
    const ids = await Promise.all(
      (await cards.all()).map((card) => card.getAttribute('data-testid')),
    )
    await summary.focus()
    await page.keyboard.press('Space')
    await expect(panel).not.toHaveAttribute('open', '')
    await expect(summary).toBeFocused()
    expect(new URL(page.url()).search).toBe(query)
    expect(
      await Promise.all((await cards.all()).map((card) => card.getAttribute('data-testid'))),
    ).toEqual(ids)
    await expect(page.getByTestId('recipes-active-filters')).toContainText('Aktywne filtry (2)')
    await expect(page.getByTestId('recipes-active-filters')).toContainText('Prywatny')
    await expect(page.getByTestId('recipes-active-filters')).toContainText('ulubione')
    await expect(page.getByTestId('recipes-clear')).toBeVisible()
  })
}
