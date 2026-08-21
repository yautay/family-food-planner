import { expect, test } from '@playwright/test'

import { cleanupE2eData } from './cleanup.js'

/**
 * Core flow 1 (08_TESTING §3, karta B05): login → nowy przepis → w ProductPickerze
 * wpis bez trafienia → `+ Dodaj produkt` → drawer → zapis → auto-wybór → ilość →
 * zapis przepisu → szczegół pokazuje wartości per porcja → zmiana porcji
 * przelicza składniki na żywo.
 *
 * Konto z `.env` (E2E_ADMIN_*) — w repozytorium nie ma działającego hasła.
 * Test sprząta po sobie: usuwa przepis i utworzony produkt.
 */

/** Wspólny prefiks nazw tego specu — po nim sprząta `cleanupE2eData`. */
const PREFIX = 'E2E przepis'

test.beforeAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX })
})

test.afterAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX })
})

test('przepis z inline create produktu i przeliczaniem porcji', async ({ page }) => {
  // Nazwy unikalne per przebieg: normalized_name produktu jest globalnym unikatem.
  const stamp = Date.now()
  const productName = `${PREFIX} Kalarepa ${stamp}`
  const recipeName = `${PREFIX} Surówka ${stamp}`

  page.on('dialog', (dialog) => dialog.accept())

  // Sesja pochodzi z `auth.setup.ts` (storageState) — patrz
  // `playwright.config.ts`. Logowanie per spec przekraczało limit 5/min.

  // --- nowy przepis -------------------------------------------------------------
  await page.goto('/przepisy')
  await expect(page.getByTestId('przepisy-page')).toBeVisible()
  await page.getByTestId('recipes-add').click()
  await expect(page.getByTestId('przepis-edytor-page')).toBeVisible()

  await page.getByTestId('recipe-name').fill(recipeName)
  await page.getByTestId('recipe-base-servings').fill('2')

  // --- składnik przez inline create produktu (06_UIUX §3.1) ------------------------
  await page.getByTestId('ingredient-add').click()
  await page.getByTestId('picker-input').fill(productName)
  await expect(page.getByTestId('picker-create')).toBeVisible()
  await page.getByTestId('picker-create').click()

  // Drawer dostaje wpisaną nazwę w prefillu; zapis tworzy produkt UNVERIFIED.
  await expect(page.getByTestId('product-create-drawer')).toBeVisible()
  await expect(page.getByTestId('drawer-product-name')).toHaveValue(productName)
  await page.getByTestId('drawer-submit').click()

  // Auto-wybór: wracamy do edycji przepisu z wybranym produktem.
  await expect(page.getByTestId('picker-selected')).toContainText(productName)

  await page.getByTestId('ingredient-amount-0').fill('250')
  await page.getByTestId('recipe-submit').click()

  // --- szczegóły: wartości per porcja -----------------------------------------------
  await expect(page).toHaveURL(/\/przepisy\/\d+$/)
  await expect(page.getByTestId('recipe-name')).toContainText(recipeName)
  // Produkt świeżo z inline create nie ma wartości — plakietka „niepełne dane"
  // z listą braków (06_UIUX §3.5) musi być widoczna.
  await expect(page.getByTestId('recipe-incomplete')).toBeVisible()

  // Składnik per porcja: 250 g / 2 porcje = 125 g.
  await expect(page.getByTestId('recipe-ingredients')).toContainText('125 g')

  // --- regulacja porcji przelicza na żywo ---------------------------------------------
  await page.getByTestId('servings-increase').click()
  await expect(page.getByTestId('servings-value')).toHaveText('1,5')
  // 250 g x 1,5 / 2 = 187,5 g.
  await expect(page.getByTestId('recipe-ingredients')).toContainText('187,5 g')

  // --- sprzątanie -----------------------------------------------------------------------
  const recipeId = page.url().match(/\/przepisy\/(\d+)$/)![1]
  await page.getByTestId('recipe-delete').click()
  await expect(page).toHaveURL(/\/przepisy$/)
  await expect(page.getByTestId(`recipe-card-${recipeId}`)).toHaveCount(0)

  // Produkt utworzony inline: do kosza przez formularz produktu (ADMIN).
  await page.goto('/produkty')
  await page.getByTestId('products-search').fill(productName)
  const card = page.locator('[data-testid^="product-edit-"]').first()
  await expect(card).toBeVisible()
  await card.click()
  await expect(page.getByTestId('produkt-form-page')).toBeVisible()
  await page.getByTestId('product-delete').click()
  await expect(page).toHaveURL(/\/produkty$/)
})
