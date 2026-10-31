import { expect, test } from '@playwright/test'
import type { Page, TestInfo } from '@playwright/test'
import type { components } from '../src/api/generated.js'
import { cleanupE2eData, csrfHeaders } from './cleanup.js'

type PlanDay = components['schemas']['DayRead']
type RecipeItemCreated = components['schemas']['RecipeItemCreatedResponse']

const PREFIX = 'E2E UX03 planowanie'
const DATES = ['2031-04-08', '2031-04-09', '2031-04-10']
const recipes: { id: number; name: string }[] = []

interface PanelLayout {
  viewportWidth: number
  focused: string | null
  dialog: { left: number; right: number; width: number }
  scrollports: {
    id: string
    left: number
    right: number
    clientWidth: number
    scrollWidth: number
    scrollLeft: number
  }[]
  elements: {
    id: string
    tag: string
    left: number
    right: number
    width: number
    clientWidth: number
    scrollWidth: number
    scrollLeft: number
    minWidth: string
    minInlineSize: string
    maxWidth: string
    display: string
    gridTemplateColumns: string
    overflowX: string
    whiteSpace: string
    overflowWrap: string
  }[]
}

async function assertPanelLayout(page: Page, testInfo: TestInfo, stage: string): Promise<void> {
  // Kod DOM wykonuje przeglądarka; bez treści pól, nazw profili i danych sesji w diagnostyce.
  const layout = await page.evaluate<PanelLayout>(`(() => {
    const dialog = document.querySelector('[data-testid="recipe-planning"]');
    const identify = (node, index) => node.getAttribute('data-testid') || node.tagName.toLowerCase() + ':' + index;
    const rect = (node) => { const box = node.getBoundingClientRect(); return { left: box.left, right: box.right, width: box.width }; };
    const visible = (node) => { if (node.closest('.sr-only')) return false; const box = node.getBoundingClientRect(); return box.width > 0 && box.height > 0; };
    const dimensions = (node) => ({ ...rect(node), clientWidth: node.clientWidth, scrollWidth: node.scrollWidth, scrollLeft: node.scrollLeft });
    const nodes = Array.from(dialog.querySelectorAll('fieldset, legend, label, input, select, p, [data-testid="recipe-picker"], [data-testid="recipe-picker-selected"], [data-testid="recipe-picker-selected"] > span, [data-testid="recipe-picker-results"] button > span'));
    return {
      viewportWidth: innerWidth,
      focused: document.activeElement ? identify(document.activeElement, 0) : null,
      dialog: rect(dialog),
      scrollports: Array.from(dialog.querySelectorAll('*')).filter(visible).filter(node => /auto|scroll/.test(getComputedStyle(node).overflowY)).map((node, index) => ({ id: identify(node, index), ...dimensions(node) })),
      elements: nodes.filter(visible).map((node, index) => {
        const style = getComputedStyle(node);
        return { id: identify(node, index), tag: node.tagName.toLowerCase(), ...dimensions(node), minWidth: style.minWidth, minInlineSize: style.minInlineSize, maxWidth: style.maxWidth, display: style.display, gridTemplateColumns: style.gridTemplateColumns, overflowX: style.overflowX, whiteSpace: style.whiteSpace, overflowWrap: style.overflowWrap };
      }),
    };
  })()`)
  await testInfo.attach(`planning-layout-${stage}.json`, {
    body: JSON.stringify(layout, null, 2),
    contentType: 'application/json',
  })
  const issues: string[] = []
  for (const port of layout.scrollports) {
    if (port.scrollWidth > port.clientWidth + 1)
      issues.push(`${port.id}: horizontal overflow ${port.scrollWidth} > ${port.clientWidth}`)
    if (Math.abs(port.scrollLeft) > 1)
      issues.push(`${port.id}: horizontal scrollLeft ${port.scrollLeft}`)
  }
  const left = Math.max(0, layout.dialog.left, ...layout.scrollports.map((port) => port.left))
  const right = Math.min(
    layout.viewportWidth,
    layout.dialog.right,
    ...layout.scrollports.map((port) => port.right),
  )
  for (const node of layout.elements) {
    if (node.left < left - 1 || node.right > right + 1)
      issues.push(`${node.id}: bounds ${node.left}..${node.right} outside ${left}..${right}`)
    if (
      ['p', 'span', 'label', 'legend'].includes(node.tag) &&
      node.clientWidth > 0 &&
      node.scrollWidth > node.clientWidth + 1
    )
      issues.push(`${node.id}: text clipped horizontally ${node.scrollWidth} > ${node.clientWidth}`)
  }
  // Soft assertions pozwalają zebrać również replace i stan po przejęciu fokusu przez błąd.
  expect
    .soft(issues, `Geometria ${stage}; pełne computed styles/rect/scroll w załączniku JSON`)
    .toEqual([])
}

async function assertDateTargets(page: Page, testInfo: TestInfo): Promise<void> {
  const targets = await page.getByTestId('plan-week').locator('button').all()
  const geometry = await Promise.all(
    targets.map(async (target) => ({
      id: await target.getAttribute('data-testid'),
      box: await target.boundingBox(),
    })),
  )
  await testInfo.attach('planning-date-targets.json', {
    body: JSON.stringify(geometry, null, 2),
    contentType: 'application/json',
  })
  expect.soft(geometry).toHaveLength(7)
  const tooSmall = geometry.filter(({ box }) => !box || box.width < 43.99 || box.height < 43.99)
  expect.soft(tooSmall, 'Każdy cel daty ma co najmniej 44 × 44 px').toEqual([])
}

test.beforeAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX, dates: DATES })
  const headers = await csrfHeaders(request)
  for (const name of [
    `${PREFIX} — Pełnoziarnista owsianka z pieczoną gruszką, orzechami i naturalnym jogurtem`,
    `${PREFIX} — Pełnoziarnista zapiekanka z pieczoną papryką, cukinią, serem i świeżymi ziołami`,
  ]) {
    const response = await request.post('/api/v1/recipes', {
      headers,
      data: { name, scope: 'private', instructions: '', base_servings: 1 },
    })
    expect(response.status()).toBe(201)
    recipes.push(await response.json())
  }
})
test.afterAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX, dates: DATES })
})

for (const [index, width] of [360, 1440].entries()) {
  test(`UX03 nowy posiłek, zamiana atomowa, błąd, odświeżenie i klawiatura — ${width}px`, async ({
    page,
  }, testInfo) => {
    const date = DATES[index]!
    const first = recipes[0]!
    const second = recipes[1]!
    await page.setViewportSize({ width, height: 900 })
    await page.goto(`/plan-dnia/${date}`)
    await expect(page.getByTestId('plan-empty')).toBeVisible()
    await assertDateTargets(page, testInfo)
    await page.getByTestId('plan-add-recipe').click()
    const panel = page.getByTestId('recipe-planning')
    await expect(panel).toHaveAttribute('role', 'dialog')
    await page
      .getByTestId('planning-meal-name')
      .fill(`${PREFIX} Późny obiad po długim spacerze i wspólnym powrocie do domu`)
    await page.getByTestId('recipe-picker-input').fill(first.name)
    await expect(page.getByTestId(`recipe-picker-option-${first.id}`)).toBeVisible()
    await assertPanelLayout(page, testInfo, 'add-search-results')
    await page.getByTestId(`recipe-picker-option-${first.id}`).click()
    await page.getByTestId('planning-servings').fill('2,2')
    await assertPanelLayout(page, testInfo, 'add-selected')
    await page.screenshot({
      path: testInfo.outputPath(`planning-add-${width}.png`),
      fullPage: true,
    })
    const createdResponse = page.waitForResponse(
      (response) =>
        response.url().includes('/recipe-items') && response.request().method() === 'POST',
    )
    await page.getByTestId('recipe-planning-submit').click()
    const response = await createdResponse
    expect(response.status()).toBe(201)
    const created = (await response.json()) as RecipeItemCreated
    await expect(panel).toBeHidden()
    await expect(page.getByTestId('plan-success')).toBeVisible()
    const row = page.getByTestId(`plan-item-${created.item_id}`)
    await expect(row).toContainText(first.name)
    await expect(page.getByTestId(`plan-item-servings-${created.item_id}`)).toHaveText('2,2')

    let fail = true
    await page.route(`**/api/v1/plan/items/${created.item_id}`, async (route) => {
      if (route.request().method() !== 'PATCH' || !fail) return route.continue()
      fail = false
      await route.fulfill({
        status: 422,
        json: {
          error: {
            code: 'validation_error',
            message: 'Test UX03: zamiana odrzucona.',
            details: {},
          },
        },
      })
    })
    await page.getByTestId(`plan-item-replace-${created.item_id}`).click()
    await assertPanelLayout(page, testInfo, 'replace-open')
    await page.getByTestId('recipe-picker-input').fill(second.name)
    await expect(page.getByTestId(`recipe-picker-option-${second.id}`)).toBeVisible()
    await assertPanelLayout(page, testInfo, 'replace-search-results')
    await page.getByTestId(`recipe-picker-option-${second.id}`).click()
    await assertPanelLayout(page, testInfo, 'replace-selected')
    await page.getByTestId('recipe-planning-submit').click()
    await expect(page.getByTestId('recipe-planning-error')).toHaveText(
      'Test UX03: zamiana odrzucona.',
    )
    await expect(page.getByTestId('recipe-planning-error')).toBeFocused()
    await assertPanelLayout(page, testInfo, 'replace-error-focused')
    await expect(page.getByTestId('recipe-picker-selected')).toContainText(second.name)
    // Serwer nie zmienił poprzedniej pozycji po błędzie; sprawdzamy także jej porcje i ID.
    const before = (await (await page.request.get(`/api/v1/plan/days/${date}`)).json()) as PlanDay
    const oldItem = before.meals
      .find((meal) => meal.id === created.meal_id)!
      .items.find((item) => item.id === created.item_id)!
    expect(oldItem.recipe_id).toBe(first.id)
    expect(oldItem.servings).toBe('2.20')
    await page.screenshot({
      path: testInfo.outputPath(`planning-error-${width}.png`),
      fullPage: true,
    })
    const patchedResponse = page.waitForResponse(
      (result) =>
        result.url().endsWith(`/plan/items/${created.item_id}`) &&
        result.request().method() === 'PATCH' &&
        result.status() === 200,
    )
    await page.getByTestId('recipe-planning-submit').click()
    const patched = (await (await patchedResponse).json()) as PlanDay
    const updated = patched.meals
      .find((meal) => meal.id === created.meal_id)!
      .items.find((item) => item.id === created.item_id)!
    expect(updated.recipe_id).toBe(second.id)
    expect(updated.servings).toBe(oldItem.servings)
    expect(updated.position).toBe(oldItem.position)
    expect(updated.servings_split).toEqual(oldItem.servings_split)
    await expect(panel).toBeHidden()
    await page.reload()
    await expect(page.getByTestId(`plan-item-${created.item_id}`)).toContainText(second.name)
    await expect(page.getByTestId('plan-summary')).toContainText('Cały plan')

    const trigger = page.getByTestId(`plan-item-replace-${created.item_id}`)
    await trigger.click()
    for (let tab = 0; tab < 14; tab += 1) {
      await page.keyboard.press(tab % 2 === 0 ? 'Tab' : 'Shift+Tab')
      await expect(panel.locator(':focus')).toHaveCount(1)
    }
    await page.keyboard.press('Escape')
    await expect(panel).toBeHidden()
    await expect(trigger).toBeFocused()
    await page.screenshot({
      path: testInfo.outputPath(`planning-saved-${width}.png`),
      fullPage: true,
    })
  })
}

test('UX03 utrata odpowiedzi po realnym POST odczytuje plan i nie ponawia zapisu', async ({
  page,
}) => {
  const date = DATES[2]!
  const recipe = recipes[0]!
  let posts = 0
  await page.route(`**/api/v1/plan/days/${date}/recipe-items`, async (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    posts += 1
    const result = await route.fetch()
    expect(result.status()).toBe(201)
    // Zapis został wykonany, ale jego odpowiedź nie dociera do aplikacji.
    await route.abort('failed')
  })
  await page.goto(`/plan-dnia/${date}`)
  await page.getByTestId('plan-add-recipe').click()
  await page.getByTestId('planning-meal-name').fill(`${PREFIX} Niepewne potwierdzenie`)
  await page.getByTestId('recipe-picker-input').fill(recipe.name)
  await page.getByTestId(`recipe-picker-option-${recipe.id}`).click()
  await page.getByTestId('recipe-planning-submit').click()
  await expect(page.getByTestId('planning-uncertain')).toBeVisible()
  await expect(page.getByTestId('recipe-planning-error')).toContainText(
    'Nie udało się potwierdzić zapisu',
  )
  await expect(page.getByTestId('planning-uncertain')).toContainText(recipe.name)
  await expect(page.getByTestId('recipe-planning-submit')).toBeDisabled()
  await expect(page.getByTestId('plan-success')).toHaveCount(0)
  expect(posts).toBe(1)
  await page.getByTestId('recipe-planning-cancel').click()
  await expect(page.locator('[data-testid^="plan-item-servings-"]')).toHaveCount(1)
  await expect(
    page.locator('[data-testid^="plan-item-"]').filter({ hasText: recipe.name }).first(),
  ).toBeVisible()
})
