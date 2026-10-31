import { expect, test, type APIRequestContext, type Page } from '@playwright/test'
import type { components } from '../src/api/generated.js'
import { cleanupE2eData, csrfHeaders } from './cleanup.js'

type Category = components['schemas']['CategoryRead']
type Product = components['schemas']['ProductRead']
type PantryItem = components['schemas']['PantryItemRead']
const PREFIX = 'E2E UX09 zapasy'
let categoryId: number
let products: Product[] = []
let pantry: PantryItem[] = []

// Po własnej kategorii także partie leżące poza pierwszymi 200 wierszami bazy.
async function cleanupOwnCategory(request: APIRequestContext): Promise<void> {
  const headers = await csrfHeaders(request)
  const response = await request.get('/api/v1/categories')
  expect(response.ok()).toBeTruthy()
  const categories = (await response.json()).items as Category[]
  for (const category of categories.filter((row) => row.name.startsWith(PREFIX))) {
    const stock = await request.get(`/api/v1/pantry?category_id=${category.id}&limit=200&offset=0`)
    expect(stock.ok()).toBeTruthy()
    for (const row of (await stock.json()).items as PantryItem[]) {
      if (row.product_name?.startsWith(PREFIX))
        expect((await request.delete(`/api/v1/pantry/${row.id}`, { headers })).status()).toBe(204)
    }
    const catalogue = await request.get(
      `/api/v1/products?category_id=${category.id}&limit=200&offset=0&include_archived=true`,
    )
    expect(catalogue.ok()).toBeTruthy()
    for (const row of (await catalogue.json()).items as Product[]) {
      if (row.name.startsWith(PREFIX))
        expect((await request.delete(`/api/v1/products/${row.id}`, { headers })).status()).toBe(204)
    }
    expect((await request.delete(`/api/v1/categories/${category.id}`, { headers })).status()).toBe(
      204,
    )
  }
}

test.beforeAll(async ({ request }) => {
  test.setTimeout(120_000)
  await cleanupOwnCategory(request)
  await cleanupE2eData(request, { namePrefix: PREFIX })
  const headers = await csrfHeaders(request)
  const category = await request.post('/api/v1/categories', {
    headers,
    data: { name: `${PREFIX} ${Date.now()}` },
  })
  expect(category.status()).toBe(201)
  categoryId = (await category.json()).id
  products = []
  pantry = []
  for (let i = 1; i <= 55; i += 1) {
    const response = await request.post('/api/v1/products', {
      headers,
      data: {
        name: `${PREFIX} ${String(i).padStart(3, '0')} — Płatki owsiane pełnoziarniste z otrębami, pestkami dyni i suszonymi owocami`,
        category_id: categoryId,
        measure_kind: 'mass',
      },
    })
    expect(response.status()).toBe(201)
    products.push(await response.json())
  }
  for (let i = 1; i <= 105; i += 1) {
    const response = await request.post('/api/v1/pantry', {
      headers,
      data: {
        product_id: i === 105 ? products[54]!.id : products[0]!.id,
        amount: '1500.125',
        expiry_date: i <= 2 ? '2000-01-01' : null,
        location: 'szafka',
        note: `partia ${i}`,
      },
    })
    expect(response.status()).toBe(201)
    pantry.push(await response.json())
  }
})
test.afterAll(async ({ request }) => {
  test.setTimeout(120_000)
  await cleanupOwnCategory(request)
  await cleanupE2eData(request, { namePrefix: PREFIX })
})

async function noOverflow(page: Page, width: number): Promise<void> {
  await page.setViewportSize({ width, height: 900 })
  expect(await page.locator('html').evaluate((element) => element.scrollWidth)).toBeLessThanOrEqual(
    width + 1,
  )
}

async function checkCompletenessDisclosure(
  page: Page,
  testid: string,
  missing: readonly string[],
): Promise<void> {
  await noOverflow(page, 390)
  const details = page.getByTestId(testid)
  const toggle = page.getByTestId(`${testid}-toggle`)
  const messages = page.getByTestId(`${testid}-messages`)
  expect(missing.length).toBeGreaterThan(0)
  await expect(toggle).toHaveText('Niepełne dane — szczegóły')
  await expect(details).not.toHaveAttribute('open', '')
  await expect(messages).toBeHidden()
  await toggle.focus()
  await toggle.press('Enter')
  await expect(details).toHaveAttribute('open', '')
  await expect(messages.getByRole('listitem')).toHaveText([...missing])
  await expect(messages).toBeVisible()
  await noOverflow(page, 390)
  await toggle.press('Enter')
  await expect(messages).toBeHidden()
  await expect(toggle).toBeFocused()
}

test('UX09: filtry serwera, edycja drugiej strony, pełne nazwy i powrót do biblioteki', async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(120_000)
  await page.goto('/spizarnia')
  await page.getByTestId('pantry-category-filter').selectOption(String(categoryId))
  await page.getByTestId('pantry-view-list').click()
  await expect(page.getByTestId('pantry-total')).toContainText('100 z 105')
  await noOverflow(page, 390)
  const urgentName = page.getByTestId(`pantry-urgent-name-${pantry[0]!.id}`)
  await expect(urgentName).toHaveText(products[0]!.name)
  const urgentLayout = await urgentName.evaluate((name) => ({
    nameWidth: name.getBoundingClientRect().width,
    rowWidth: name.parentElement!.getBoundingClientRect().width,
    height: name.getBoundingClientRect().height,
    lineHeight: Number.parseFloat(
      name.ownerDocument.defaultView!.getComputedStyle(name).lineHeight,
    ),
  }))
  expect(urgentLayout.nameWidth).toBeGreaterThanOrEqual(urgentLayout.rowWidth * 0.9)
  expect(urgentLayout.nameWidth).toBeGreaterThan(250)
  expect(urgentLayout.height).toBeLessThanOrEqual(urgentLayout.lineHeight * 5)
  await page.getByTestId('pantry-show-expiring').click()
  await expect(page.getByTestId('pantry-total')).toContainText('2 z 2')
  await expect(page.getByTestId('pantry-list').getByTestId('expiry-badge-expired')).toHaveCount(2)
  await page.getByTestId('pantry-expiring-only').uncheck()
  await expect(page.getByTestId('pantry-total')).toContainText('100 z 105')
  await page.getByTestId('pantry-load-more').click()
  await expect(page.getByTestId('pantry-total')).toContainText('105 z 105')
  const last = pantry[104]!
  const edit = page.getByTestId(`pantry-edit-${last.id}`)
  await edit.click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await noOverflow(page, 390)
  await testInfo.attach('ux09-pantry-panel-390.png', {
    body: await page.screenshot(),
    contentType: 'image/png',
  })
  await page.getByTestId('pantry-amount').fill('7')
  await page.getByTestId('pantry-amount').press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(edit).toBeFocused()
  await expect(page.getByTestId(`pantry-amount-${last.id}`)).toHaveText('1,500125 kg')
  await edit.click()
  await page.getByTestId('pantry-amount').fill('0,25')
  // Faktyczna awaria transportu przed wysłaniem; nie pozorujemy udanego zapisu.
  await page.route(`**/api/v1/pantry/${last.id}`, (route) => route.abort('failed'))
  await page.getByTestId('pantry-submit').click()
  await expect(page.getByTestId('pantry-error')).toBeVisible()
  await expect(page.getByTestId('pantry-amount')).toHaveValue('0,25')
  await page.unroute(`**/api/v1/pantry/${last.id}`)
  const saved = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/v1/pantry/${last.id}`) &&
      response.request().method() === 'PATCH' &&
      response.status() === 200,
  )
  await page.getByTestId('pantry-amount').press('Enter')
  await saved
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByTestId('pantry-total')).toContainText('105 z 105')
  await expect(page.getByTestId('pantry-category-filter')).toHaveValue(String(categoryId))
  await expect(page.getByTestId('pantry-view-list')).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId(`pantry-amount-${last.id}`)).toHaveText('0,25 g')
  await expect(edit).toBeFocused()
  const persisted = await request.get(
    `/api/v1/pantry?category_id=${categoryId}&limit=100&offset=100`,
  )
  expect(
    ((await persisted.json()).items as PantryItem[]).find((row) => row.id === last.id)?.amount,
  ).toBe('0.250')
  for (const width of [390, 768, 1024]) {
    await noOverflow(page, width)
    await page.getByTestId(`pantry-name-${last.id}`).scrollIntoViewIfNeeded()
    await expect(page.getByTestId(`pantry-name-${last.id}`)).toHaveText(products[54]!.name)
    await testInfo.attach(`ux09-pantry-${width}.png`, {
      body: await page.screenshot({ fullPage: true }),
      contentType: 'image/png',
    })
  }

  await page.goto('/produkty')
  await page.getByTestId('products-category-filter').selectOption(String(categoryId))
  await page.getByTestId('products-include-archived').check()
  await expect(page.getByTestId('products-total')).toContainText('50 z 55')
  await page.getByTestId('products-load-more').click()
  await expect(page.getByTestId('products-total')).toContainText('55 z 55')
  const product = products[54]!
  await page.getByTestId(`product-edit-${product.id}`).click()
  await expect(page.getByTestId('product-name')).toHaveValue(product.name)
  const changedName = `${product.name} — poprawione`
  await page.getByTestId('product-name').fill(changedName)
  await page.getByTestId('product-submit').click()
  await expect(page.getByTestId('product-saved')).toBeVisible()
  await expect(page.getByTestId('nutrition-incomplete')).toBeVisible()
  const productResponse = await request.get(`/api/v1/products/${product.id}`)
  expect(productResponse.ok()).toBeTruthy()
  const savedProduct = (await productResponse.json()) as Product
  await checkCompletenessDisclosure(page, 'nutrition-incomplete', savedProduct.completeness.missing)
  for (const width of [390, 768, 1024]) {
    await noOverflow(page, width)
    await testInfo.attach(`ux09-product-form-${width}.png`, {
      body: await page.screenshot({ fullPage: true }),
      contentType: 'image/png',
    })
  }
  await page.getByTestId('product-back').click()
  await expect(page.getByTestId('products-total')).toContainText('55 z 55')
  await expect(page.getByTestId('products-category-filter')).toHaveValue(String(categoryId))
  await expect(page.getByTestId('products-include-archived')).toBeChecked()
  await expect(page.getByTestId(`product-card-${product.id}`)).toContainText(changedName)
  await expect(page.getByTestId(`product-card-${product.id}`)).toBeFocused()
  // Zimne odtworzenie głębokości stron nie zależy od cache poprzedniej instancji.
  await page.reload()
  await expect(page.getByTestId('products-total')).toContainText('55 z 55')
  await checkCompletenessDisclosure(
    page,
    `product-incomplete-${product.id}`,
    savedProduct.completeness.missing,
  )
  for (const width of [390, 1024]) {
    await noOverflow(page, width)
    await testInfo.attach(`ux09-products-${width}.png`, {
      body: await page.screenshot({ fullPage: true }),
      contentType: 'image/png',
    })
  }
})
