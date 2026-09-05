import { expect, test, type APIRequestContext } from '@playwright/test'

import { cleanupE2eData, csrfHeaders } from './cleanup.js'

/**
 * BATCH_19: da się dojść do OSTATNIEJ pozycji listy (Acceptance Criteria 1–2).
 *
 * Dług, który to zamyka (ustalenie R4, P1): `/produkty` renderowało 50 pozycji
 * i pisało obok „Produktów: 185". Test musi więc przekroczyć stronę — seed demo
 * ma 15 produktów, czyli sam z siebie problemu nie pokaże.
 *
 * Dane seedujemy PRZEZ API (60 produktów w WŁASNEJ kategorii), a nie klikaniem:
 * sześćdziesiąt przejść przez formularz trwałoby minuty i testowałoby formularz,
 * nie paginację. Filtrujemy po KATEGORII, nie szukajką — szukajka jest
 * trigramowa, więc kolejność wyników zależy od progu podobieństwa, a asercja
 * „pozycji z drugiej strony nie było na pierwszej" wymaga porządku
 * deterministycznego (bez `?q=` serwer sortuje po nazwie).
 */

/** Wspólny prefiks nazw tego specu — po nim sprząta `cleanupE2eData`. */
const PREFIX = 'E2E paginacja'
const API = '/api/v1'

/** Ponad stronę (`PAGE_SIZE` = 50), żeby drugie kliknięcie miało co pokazać. */
const PRODUCT_COUNT = 60
const PAGE_SIZE = 50

async function seedProducts(
  request: APIRequestContext,
  stamp: number,
): Promise<{ categoryName: string; lastName: string }> {
  const headers = await csrfHeaders(request)
  const categoryName = `${PREFIX} ${stamp}`

  const category = await request.post(`${API}/categories`, {
    headers,
    data: { name: categoryName },
  })
  expect(category.ok(), await category.text()).toBeTruthy()
  const categoryId = ((await category.json()) as { id: number }).id

  // Numeracja z wiodącymi zerami: serwer sortuje po nazwie, więc „060" ma być
  // ostatnie także tekstowo (bez zer „10" trafiłoby przed „9").
  for (let index = 1; index <= PRODUCT_COUNT; index += 1) {
    const name = `${PREFIX} ${stamp} ${String(index).padStart(3, '0')}`
    const created = await request.post(`${API}/products`, {
      headers,
      data: { name, category_id: categoryId, measure_kind: 'mass' },
    })
    expect(created.ok(), await created.text()).toBeTruthy()
  }

  return {
    categoryName,
    lastName: `${PREFIX} ${stamp} ${String(PRODUCT_COUNT).padStart(3, '0')}`,
  }
}

test.beforeAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX })
})

test.afterAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX })
})

test('„pokaż więcej" dowozi pozycje spoza pierwszej strony katalogu', async ({ page, request }) => {
  const stamp = Date.now()
  const { categoryName, lastName } = await seedProducts(request, stamp)

  await page.goto('/produkty')
  await expect(page.getByTestId('produkty-page')).toBeVisible()

  await page.getByTestId('products-category-filter').selectOption({ label: categoryName })

  // Pierwsza strona: licznik mówi PRAWDĘ o obu liczbach (AC 2).
  await expect(page.getByTestId('products-total')).toContainText(`${PAGE_SIZE} z ${PRODUCT_COUNT}`)
  await expect(page.getByTestId('products-list').getByRole('listitem')).toHaveCount(PAGE_SIZE)

  // Ostatniej pozycji NIE MA na pierwszej stronie — to jest dokładnie ten
  // wiersz, którego przed tym batchem nie dało się osiągnąć z UI.
  await expect(page.getByText(lastName, { exact: true })).toHaveCount(0)

  await page.getByTestId('products-load-more').click()

  await expect(page.getByTestId('products-list').getByRole('listitem')).toHaveCount(PRODUCT_COUNT)
  await expect(page.getByText(lastName, { exact: true })).toBeVisible()
  await expect(page.getByTestId('products-total')).toContainText(
    `${PRODUCT_COUNT} z ${PRODUCT_COUNT}`,
  )

  // Wszystko wczytane ⇒ przycisku nie ma (AC 1: koniec listy jest widoczny).
  await expect(page.getByTestId('products-load-more')).toHaveCount(0)
})
