import { expect, test } from '@playwright/test'
import type { components } from '../src/api/generated.js'
import { cleanupE2eData, csrfHeaders } from './cleanup.js'

type Recipe = components['schemas']['RecipeDetail']
const PREFIX = 'E2E UX08 edytor'
const productName = `${PREFIX} — Pełnoziarniste płatki owsiane z otrębami, pestkami dyni i suszonymi owocami do domowego śniadania`
let productId: number

test.beforeAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX })
  const headers = await csrfHeaders(request)
  const categories = await request.get('/api/v1/categories')
  expect(categories.ok()).toBe(true)
  const categoryId = ((await categories.json()) as components['schemas']['CategoryListResponse'])
    .items[0]!.id
  const response = await request.post('/api/v1/products', {
    headers,
    data: {
      name: productName,
      category_id: categoryId,
      measure_kind: 'mass',
      piece_weight_g: null,
    },
  })
  expect(response.status()).toBe(201)
  productId = ((await response.json()) as components['schemas']['ProductDetail']).id
})
test.afterAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX })
})

for (const width of [390, 1024]) {
  test(`UX08 ${width}: klawiatura, ostrzeżenie, 422/403/409 i rzeczywisty zapis zachowują dane`, async ({
    page,
    request,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 900 })
    const headers = await csrfHeaders(request)
    const originalName = `${PREFIX} Śniadanie ${width}`
    const created = await request.post('/api/v1/recipes', {
      headers,
      data: {
        name: originalName,
        scope: 'private',
        base_servings: 2,
        prep_time_min: 15,
        instructions: 'Namocz przez noc.',
        difficulty: 2,
        ingredients: [{ product_id: productId, quantity: '250', unit: 'g', note: 'Bez gotowania' }],
      },
    })
    expect(created.status()).toBe(201)
    const recipeId = ((await created.json()) as Recipe).id
    await page.goto(
      `/przepisy/${recipeId}/edytuj?q=sniadanie&tag=2&selectedDate=2031-04-09&from=2031-04-07&to=2031-04-13&next=evil&offset=50`,
    )
    await expect(page.getByTestId('recipe-name')).toHaveValue(originalName)
    await expect(page.getByTestId('picker-selected')).toContainText(productName)
    const nameSpan = page.getByTestId('picker-selected').locator('span').first()
    const fullName = await nameSpan.evaluate((node) => ({
      scroll: node.scrollWidth,
      client: node.clientWidth,
      nowrap: node.ownerDocument.defaultView!.getComputedStyle(node).whiteSpace,
    }))
    expect(fullName.nowrap).not.toBe('nowrap')
    expect(fullName.scroll).toBeLessThanOrEqual(fullName.client + 1)
    expect(await page.locator('html').evaluate((node) => node.scrollWidth)).toBeLessThanOrEqual(
      width + 1,
    )
    await testInfo.attach(`editor-base-${width}.png`, {
      body: await page.screenshot({ fullPage: true }),
      contentType: 'image/png',
    })

    const changedName = `${originalName} po zmianie`
    await page.getByTestId('recipe-name').fill(changedName)
    await page.getByTestId('recipe-instructions').fill('Namocz przez noc. Rano dodaj owoce.')
    await expect(page.getByTestId('recipe-dirty-status')).toHaveText('Masz niezapisane zmiany')
    const dirtyDialog = page.waitForEvent('dialog')
    await page.getByTestId('recipe-editor-back').focus()
    const attemptLeave = page.keyboard.press('Enter')
    const dialog = await dirtyDialog
    expect(dialog.type()).toBe('confirm')
    await dialog.dismiss()
    await attemptLeave
    await expect(page).toHaveURL(new RegExp(`/przepisy/${recipeId}/edytuj`))
    await expect(page.getByTestId('recipe-name')).toHaveValue(changedName)

    // Dwie aktywne wyszukiwarki: klik etykiety musi ogniskować właściwy input.
    await page.getByTestId('ingredient-add').click()
    await page.getByTestId('ingredient-add').click()
    const secondEmpty = page.getByTestId('ingredient-row-2')
    await secondEmpty.getByText('Produkt — składnik 3', { exact: true }).click()
    await expect(secondEmpty.getByTestId('picker-input')).toBeFocused()
    await page.getByTestId('ingredient-remove-2').click()
    await page.getByTestId('recipe-submit').click()
    await expect(page.getByTestId('ingredient-error-1')).toContainText('Wybierz produkt')
    const newRow = page.getByTestId('ingredient-row-1')
    await expect(newRow.getByTestId('picker-input')).toBeFocused()
    await expect(page.getByTestId('ingredient-amount-0')).toHaveValue('250,000')
    await expect(page.getByTestId('ingredient-note-0')).toHaveValue('Bez gotowania')
    await newRow.getByTestId('picker-input').fill(productName)
    await newRow.getByTestId(`picker-option-${productId}`).click()
    await page.getByTestId('ingredient-amount-1').fill('12,5')

    const statuses = [422, 403, 409]
    let failureIndex = 0
    await page.route(`**/api/v1/recipes/${recipeId}`, async (route) => {
      if (route.request().method() !== 'PUT' || failureIndex >= statuses.length)
        return route.continue()
      const status = statuses[failureIndex++]!
      await route.fulfill({
        status,
        json: {
          error: {
            code: status === 422 ? 'validation_error' : status === 403 ? 'forbidden' : 'conflict',
            message: `Kontrolowany błąd ${status}. Wpisane dane pozostają w edytorze.`,
            details:
              status === 422
                ? {
                    fields: [
                      { field: 'difficulty', message: 'Invalid value', type: 'value_error' },
                    ],
                  }
                : {},
          },
        },
      })
    })
    for (const status of statuses) {
      await page.getByTestId('recipe-submit').click()
      await expect(page.getByTestId('recipe-editor-error')).toContainText(`błąd ${status}`)
      if (status === 422) {
        await expect(page.getByTestId('recipe-difficulty')).toBeFocused()
        await expect(page.getByTestId('recipe-extras')).toHaveAttribute('open', '')
        const focused = await page.getByTestId('recipe-difficulty').evaluate((node) => {
          const bounds = node.getBoundingClientRect()
          const view = node.ownerDocument.defaultView!
          const overlays = ['recipe-save-bar', 'nav-bottom'].flatMap((testid) => {
            const overlay = node.ownerDocument.querySelector(`[data-testid="${testid}"]`)
            if (!overlay) return []
            const box = overlay.getBoundingClientRect()
            if (
              box.width === 0 ||
              box.height === 0 ||
              view.getComputedStyle(overlay).visibility === 'hidden'
            )
              return []
            return [
              {
                testid,
                overlaps:
                  bounds.left < box.right &&
                  bounds.right > box.left &&
                  bounds.top < box.bottom &&
                  bounds.bottom > box.top,
              },
            ]
          })
          return {
            top: bounds.top,
            bottom: bounds.bottom,
            left: bounds.left,
            right: bounds.right,
            height: view.innerHeight,
            width: view.innerWidth,
            overlays,
          }
        })
        expect(focused.top).toBeGreaterThanOrEqual(0)
        expect(focused.bottom).toBeLessThanOrEqual(focused.height)
        expect(focused.left).toBeGreaterThanOrEqual(0)
        expect(focused.right).toBeLessThanOrEqual(focused.width)
        expect(focused.overlays).toContainEqual({ testid: 'recipe-save-bar', overlaps: false })
        for (const overlay of focused.overlays) expect(overlay.overlaps, overlay.testid).toBe(false)
        if (width === 390)
          expect(focused.overlays).toContainEqual({ testid: 'nav-bottom', overlaps: false })
        await page.getByTestId('recipe-difficulty').fill('3')
      } else await expect(page.getByTestId('recipe-editor-error')).toBeFocused()
      await expect(page.getByTestId('recipe-name')).toHaveValue(changedName)
      await expect(page.getByTestId('ingredient-amount-1')).toHaveValue('12,5')
      await expect(page.getByTestId('recipe-instructions')).toHaveValue(
        'Namocz przez noc. Rano dodaj owoce.',
      )
      expect(await page.locator('html').evaluate((node) => node.scrollWidth)).toBeLessThanOrEqual(
        width + 1,
      )
      await testInfo.attach(`editor-error-${status}-${width}.png`, {
        body: await page.screenshot({ fullPage: true }),
        contentType: 'image/png',
      })
    }
    let unexpectedDialogs = 0
    page.on('dialog', async (unexpected) => {
      unexpectedDialogs++
      await unexpected.dismiss()
    })
    await page.getByTestId('recipe-submit').click()
    await expect(page).toHaveURL(new RegExp(`/przepisy/${recipeId}\\?`))
    expect(unexpectedDialogs).toBe(0)
    const url = new URL(page.url())
    expect(url.searchParams.get('selectedDate')).toBe('2031-04-09')
    expect(url.searchParams.get('q')).toBe('sniadanie')
    expect(url.searchParams.get('next')).toBeNull()
    expect(url.searchParams.get('offset')).toBeNull()
    await expect(page.getByTestId('recipe-name')).toHaveText(changedName)
    const saved = await request.get(`/api/v1/recipes/${recipeId}`)
    expect(saved.status()).toBe(200)
    const body = (await saved.json()) as Recipe
    expect(body.instructions).toBe('Namocz przez noc. Rano dodaj owoce.')
    expect(body.ingredients).toHaveLength(2)
    expect(body.ingredients[1]!.display_qty).toBe('12.500')
  })
}
