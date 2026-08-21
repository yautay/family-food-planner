import { expect, test } from '@playwright/test'

import { cleanupE2eData } from './cleanup.js'

/**
 * Core flow BATCH_08 (08_TESTING §3): Spiżarnia → „+ Dodaj produkt" →
 * `ProductPicker` z inline create nieistniejącego produktu → pozycja na liście
 * → wyzerowanie (pozycja ZOSTAJE) → usunięcie.
 *
 * Inline create jest tu sednem, nie ozdobą (06_UIUX §3.1): użytkownik notuje
 * stan domowy i nie ma zamiaru iść do katalogu założyć produkt, żeby wrócić.
 *
 * Sesja pochodzi z `auth.setup.ts` (storageState), a spec podpisuje encje
 * własnym prefiksem i sprząta w `beforeAll` I `afterAll` (ustalenie R2) —
 * inaczej stara „Kasza E2E …" zostawałaby w wynikach szukajki i chowała opcję
 * „+ Dodaj".
 */

/** Wspólny prefiks nazw tego specu — po nim sprząta `cleanupE2eData`. */
const PREFIX = 'E2E spizarnia'

test.beforeAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX })
})

test.afterAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX })
})

test('dodanie pozycji z inline create produktu, wyzerowanie i usunięcie', async ({ page }) => {
  // Nazwa unikalna per przebieg: `normalized_name` jest globalnym unikatem.
  const productName = `${PREFIX} Kasza ${Date.now()}`

  page.on('dialog', (dialog) => dialog.accept())

  await page.goto('/spizarnia')
  await expect(page.getByTestId('spizarnia-page')).toBeVisible()

  // --- dodanie pozycji z produktem tworzonym w locie -----------------------------
  await page.getByTestId('pantry-add').click()
  await expect(page.getByTestId('pantry-form')).toBeVisible()

  await page.getByTestId('picker-input').fill(productName)
  await expect(page.getByTestId('picker-create')).toBeVisible()
  await page.getByTestId('picker-create').click()

  // Drawer dostaje wpisaną nazwę w prefillu; zapis tworzy produkt UNVERIFIED.
  await expect(page.getByTestId('product-create-drawer')).toBeVisible()
  await expect(page.getByTestId('drawer-product-name')).toHaveValue(productName)
  await page.getByTestId('drawer-submit').click()

  // Auto-wybór: wracamy do formularza spiżarni z wybranym produktem.
  await expect(page.getByTestId('picker-selected')).toContainText(productName)

  await page.getByTestId('pantry-amount').fill('1500')
  await page.getByTestId('pantry-location-input').fill('szafka')
  await page.getByTestId('pantry-submit').click()

  // --- pozycja widoczna od razu, z ilością w kilogramach ---------------------------
  await expect(page.getByTestId('pantry-form')).toHaveCount(0)
  const card = page.getByTestId('pantry-list').getByText(productName)
  await expect(card).toBeVisible()

  const itemId = await page
    .locator('[data-testid^="pantry-card-"]')
    .filter({ hasText: productName })
    .first()
    .getAttribute('data-testid')
  const id = itemId!.replace('pantry-card-', '')
  await expect(page.getByTestId(`pantry-amount-${id}`)).toHaveText('1,5 kg')

  // --- wyzerowanie: pozycja ZOSTAJE ------------------------------------------------
  await page.getByTestId(`pantry-zero-${id}`).click()
  await expect(page.getByTestId(`pantry-amount-${id}`)).toHaveText('Skończyło się')
  await expect(page.getByTestId(`pantry-card-${id}`)).toBeVisible()

  // --- usunięcie (dialog potwierdzenia akceptuje handler wyżej) ----------------------
  await page.getByTestId(`pantry-remove-${id}`).click()
  await expect(page.getByTestId(`pantry-card-${id}`)).toHaveCount(0)
})
