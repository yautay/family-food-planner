import { expect, test } from '@playwright/test'

import { cleanupE2eData } from './cleanup.js'

/**
 * Core flow BATCH_04 (08_TESTING §3): logowanie → Produkty → utworzenie produktu
 * (plakietka „Do weryfikacji") → uzupełnienie wartości → weryfikacja
 * na `/admin/weryfikacja` → plakietka znika.
 *
 * Test jedzie na koncie administratora z `.env` — ta sama zasada co w
 * `households.spec.ts`: w repozytorium nie ma i nie może być działającego hasła
 * (07_SECURITY §2). Administrator przechodzi tu OBIE role, bo ścieżka serwera
 * dla tworzenia produktu jest identyczna dla USERA (tworzenie jest dla każdego,
 * weryfikacja tylko dla ADMIN-a).
 *
 * Test sprząta po sobie: na koniec usuwa utworzony produkt.
 */

/** Wspólny prefiks nazw tego specu — po nim sprząta `cleanupE2eData`. */
const PREFIX = 'E2E produkt'

test.beforeAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX })
})

test.afterAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX })
})

test('użytkownik dodaje produkt, administrator go weryfikuje', async ({ page }) => {
  // Nazwa unikalna per przebieg: `normalized_name` jest globalnym unikatem.
  const productName = `${PREFIX} Kalarepa ${Date.now()}`

  page.on('dialog', (dialog) => dialog.accept())

  // Sesja pochodzi z `auth.setup.ts` (storageState) — patrz
  // `playwright.config.ts`. Logowanie per spec przekraczało limit 5/min.

  // --- utworzenie produktu ----------------------------------------------------
  await page.goto('/produkty')
  await expect(page.getByTestId('produkty-page')).toBeVisible()

  await page.getByTestId('products-add').click()
  await expect(page.getByTestId('produkt-form-page')).toBeVisible()

  await page.getByTestId('product-name').fill(productName)
  await page.getByTestId('product-submit').click()

  // Po zapisie zostajemy w edycji utworzonego produktu (sekcje wartości
  // i przeliczników wymagają istniejącego id).
  await expect(page).toHaveURL(/\/produkty\/\d+\/edytuj/)
  await expect(page.getByTestId('product-status')).toContainText('Do weryfikacji')

  const productId = page.url().match(/\/produkty\/(\d+)\/edytuj/)![1]

  // --- kolejka weryfikacji ------------------------------------------------------
  await page.goto('/admin/weryfikacja')
  const queueRow = page.getByTestId(`verification-row-${productId}`)
  await expect(queueRow).toBeVisible()
  await expect(queueRow).toContainText(productName)
  // Bez kompletu wartości weryfikacja jest niedostępna (backend odpowiedziałby 422).
  await expect(page.getByTestId(`verification-verify-${productId}`)).toBeDisabled()

  // --- uzupełnienie wartości przez administratora ---------------------------------
  await page.getByTestId(`verification-open-${productId}`).click()
  await expect(page.getByTestId('nutrition-form')).toBeVisible()

  await page.getByTestId('nutrition-kcal').fill('27')
  await page.getByTestId('nutrition-protein').fill('1,7')
  await page.getByTestId('nutrition-fat').fill('0,1')
  await page.getByTestId('nutrition-carbs').fill('6,2')
  await page.getByTestId('nutrition-gi').fill('20')
  await page.getByTestId('nutrition-source').fill('e2e:test')
  await page.getByTestId('nutrition-submit').click()
  await expect(page.getByTestId('nutrition-incomplete')).toHaveCount(0)

  // --- weryfikacja ------------------------------------------------------------------
  await page.goto('/admin/weryfikacja')
  await page.getByTestId(`verification-verify-${productId}`).click()
  await expect(page.getByTestId(`verification-row-${productId}`)).toHaveCount(0)

  await page.goto(`/produkty/${productId}/edytuj`)
  await expect(page.getByTestId('product-status')).toContainText('Zweryfikowany')

  // --- sprzątanie ---------------------------------------------------------------------
  await page.getByTestId('product-delete').click()
  await expect(page).toHaveURL(/\/produkty$/)
})
