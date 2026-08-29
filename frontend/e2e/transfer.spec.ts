import { expect, test } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'

import { cleanupE2eData, csrfHeaders } from './cleanup.js'

/**
 * Smoke transferu (karta B14 §Tests): Ustawienia → eksport (plik pobrany) →
 * import TEGO SAMEGO pliku → raport kolizji → apply → podsumowanie.
 *
 * Plik wraca na to samo konto, więc kolizje są GWARANTOWANE: przepis nosi tę
 * samą nazwę, a produkt ten sam `normalized_name`. To najostrzejszy wariant
 * scenariusza i jednocześnie ten, który użytkownik wykona pierwszy („czy mój
 * backup w ogóle się wczytuje?").
 *
 * Dla przepisu wybieramy „Utwórz kopię": domyślne „użyj istniejącego" nie
 * stworzyłoby niczego, więc podsumowanie nie miałoby czego pokazać. Kopia
 * dziedziczy prefiks nazwy, więc sprząta ją to samo `cleanupE2eData`.
 */
const PREFIX = 'E2E transfer'
// Prefiks jest NA POCZĄTKU nazwy: `cleanupE2eData` dopasowuje encje po PREFIKSIE
// (`byPrefix`), więc „Zupa E2E transfer" przeżyłaby sprzątanie i zatruła kolejne
// specy — trigramowa szukajka przepisów znalazłaby ją przy innej frazie
// i zablokowała inline create (dokładnie dług U15 z review R2).
const RECIPE_NAME = `${PREFIX} Zupa`
/** Produkt z seedu demo (`task db-seed-demo`) — trwały, z kompletem wartości. */
const SEED_PRODUCT = 'Mąka pszenna typ 500'

const API = '/api/v1'

async function seedRecipe(request: APIRequestContext): Promise<void> {
  const headers = await csrfHeaders(request)
  const products = await request.get(
    `${API}/products?q=${encodeURIComponent(SEED_PRODUCT)}&limit=1`,
  )
  expect(products.ok(), await products.text()).toBe(true)
  const items = ((await products.json()) as { items: { id: number }[] }).items
  expect(
    items.length,
    `Seed demo musi zawierać „${SEED_PRODUCT}" (task db-seed-demo)`,
  ).toBeGreaterThan(0)

  const response = await request.post(`${API}/recipes`, {
    headers,
    data: {
      name: RECIPE_NAME,
      scope: 'private',
      instructions: 'Gotować.',
      base_servings: 2,
      ingredients: [{ product_id: items[0]!.id, quantity: '300', unit: 'g' }],
      tag_ids: [],
    },
  })
  expect(response.status(), await response.text()).toBe(201)
}

test.beforeAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX })
  await seedRecipe(request)
})

test.afterAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX })
})

test('transfer: eksport moich danych, import tego pliku, kolizje i podsumowanie', async ({
  page,
}) => {
  await page.goto('/ustawienia')
  await expect(page.getByTestId('ustawienia-page')).toBeVisible()

  // --- eksport: plik faktycznie się pobiera ---------------------------------------
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByTestId('transfer-export').click(),
  ])
  expect(download.suggestedFilename()).toContain('ffp-export-')
  const archivePath = await download.path()
  expect(archivePath, 'Playwright musi mieć plik na dysku, żeby go odesłać').toBeTruthy()
  await expect(page.getByTestId('transfer-export-done')).toBeVisible()

  // --- import: krok 1 (plik) → krok 2 (raport dry-run) -----------------------------
  await page.getByTestId('transfer-import-open').click()
  await expect(page.getByTestId('transfer-import-dialog')).toBeVisible()
  await page.getByTestId('transfer-file').setInputFiles(archivePath!)

  const [dryRun] = await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().endsWith('/transfer/import') && response.request().method() === 'POST',
    ),
    page.getByTestId('transfer-analyze').click(),
  ])
  expect(dryRun.status(), await dryRun.text()).toBe(200)
  await expect(page.getByTestId('transfer-step-report')).toBeVisible()

  // Raport kolizji MUSI pokazać przepis o tej samej nazwie — plik wraca na to
  // samo konto, więc kolizja jest pewna.
  const collision = page
    .getByTestId('transfer-collisions')
    .locator('li')
    .filter({ hasText: RECIPE_NAME })
  await expect(collision).toHaveCount(1)
  await collision.getByRole('button', { name: 'Utwórz kopię' }).click()

  // --- apply: krok 3 (podsumowanie) ------------------------------------------------
  const [applied] = await Promise.all([
    page.waitForResponse((response) => response.url().includes('/transfer/import/')),
    page.getByTestId('transfer-confirm').click(),
  ])
  expect(applied.status(), await applied.text()).toBe(200)

  await expect(page.getByTestId('transfer-step-summary')).toBeVisible()
  await expect(page.getByTestId('transfer-summary-created')).toContainText('Przepisy: 1')

  // Kopia jest realna: widać ją na liście przepisów pod nazwą z sufiksem
  // (też z prefiksem na początku, więc sprzątanie ją złapie).
  await page.goto(`/przepisy?q=${encodeURIComponent(RECIPE_NAME)}`)
  await expect(page.getByText(`${RECIPE_NAME} (import)`)).toBeVisible()
})
