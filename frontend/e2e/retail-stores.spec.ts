import { expect, test } from '@playwright/test'

import { cleanupE2eData } from './cleanup.js'

/**
 * Core flow BATCH_09 (08_TESTING §3), dwa przepływy z karty:
 *
 * 1. Karta produktu kanonicznego → „Dodaj produkt sklepowy" → drawer
 *    z `StorePicker` i INLINE CREATE sklepu → wariant widoczny na karcie.
 * 2. Ustawienia → „Sklepy" → edytor kolejności kategorii → przestawienie
 *    STRZAŁKAMI (obowiązkowa alternatywa dla DnD, 06_UIUX §2) → kolejność
 *    przetrwała odświeżenie strony.
 *
 * Drugi przepływ celowo NIE używa przeciągania: DnD sprawdzamy jako gest
 * ręcznie, a automat pilnuje ścieżki, która musi działać na telefonie i
 * z klawiatury — czyli tej, którą łatwo zepsuć nie zauważając.
 *
 * Sesja pochodzi z `auth.setup.ts` (storageState), a spec podpisuje encje
 * własnym prefiksem i sprząta w `beforeAll` I `afterAll` (ustalenie R2).
 */

/** Wspólny prefiks nazw tego specu — po nim sprząta `cleanupE2eData`. */
const PREFIX = 'E2E sklepy'

test.beforeAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX })
})

test.afterAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX })
})

test('dodanie produktu sklepowego z inline create sklepu z karty produktu', async ({ page }) => {
  const stamp = Date.now()
  // Nazwy unikalne per przebieg: `normalized_name` produktu i `name` sklepu są
  // globalnymi unikatami.
  const productName = `${PREFIX} Jogurt ${stamp}`
  const storeName = `${PREFIX} Market ${stamp}`
  const retailName = `${PREFIX} Jogurt Pilos 400 g ${stamp}`

  page.on('dialog', (dialog) => dialog.accept())

  // --- produkt kanoniczny, na którym wisi wariant -------------------------------
  await page.goto('/produkty/nowy')
  await expect(page.getByTestId('produkt-form-page')).toBeVisible()
  await page.getByTestId('product-name').fill(productName)
  await page.getByTestId('product-submit').click()

  // Po zapisie zostajemy w edycji TEGO produktu — dopiero tu jest sekcja retail.
  await expect(page.getByTestId('retail-section')).toBeVisible()
  await expect(page.getByTestId('retail-empty')).toBeVisible()

  // --- wariant sklepowy z nowym sklepem tworzonym w locie ------------------------
  await page.getByTestId('retail-add').click()
  await expect(page.getByTestId('retail-create-drawer')).toBeVisible()

  await page.getByTestId('retail-name').fill(retailName)
  await page.getByTestId('retail-brand').fill('Pilos')

  await page.getByTestId('store-picker-input').fill(storeName)
  await expect(page.getByTestId('store-picker-create')).toBeVisible()
  await page.getByTestId('store-picker-create').click()
  // Auto-wybór: wracamy do formularza wariantu z gotowym sklepem (06_UIUX §3.1).
  await expect(page.getByTestId('store-picker-selected')).toContainText(storeName)

  await page.getByTestId('retail-amount').fill('400')
  await page.getByTestId('retail-submit').click()

  // --- wariant widoczny na karcie produktu (AC 5) --------------------------------
  await expect(page.getByTestId('retail-create-drawer')).toHaveCount(0)
  const row = page.locator('[data-testid^="retail-row-"]').filter({ hasText: retailName })
  await expect(row).toHaveCount(1)
  await expect(row).toContainText('400 g')
  await expect(row).toContainText(storeName)
})

test('kolejność kategorii w profilu sklepu zmieniona strzałkami jest trwała', async ({
  page,
  request,
}) => {
  const storeName = `${PREFIX} Profil ${Date.now()}`

  page.on('dialog', (dialog) => dialog.accept())

  await page.goto('/ustawienia')
  await page.getByTestId('settings-tab-shopping').click()
  await expect(page.getByTestId('stores-section')).toBeVisible()

  // --- nowy sklep -----------------------------------------------------------------
  await page.getByTestId('store-add').click()
  await page.getByTestId('store-name').fill(storeName)
  await page.getByTestId('store-submit').click()

  const storeRow = page.locator('[data-testid^="store-row-"]').filter({ hasText: storeName })
  await expect(storeRow).toHaveCount(1)
  const storeTestId = await storeRow.getAttribute('data-testid')
  const storeId = storeTestId!.replace('store-row-', '')

  // --- profil: dwie pierwsze kategorie ze słownika ---------------------------------
  await page.getByTestId(`store-order-${storeId}`).click()
  await expect(page.getByTestId('category-order-editor')).toBeVisible()

  const available = page.locator('[data-testid^="order-add-"]')
  await expect(available.first()).toBeVisible()
  const firstId = (await available.nth(0).getAttribute('data-testid'))!.replace('order-add-', '')
  const secondId = (await available.nth(1).getAttribute('data-testid'))!.replace('order-add-', '')

  await page.getByTestId(`order-add-${firstId}`).click()
  await page.getByTestId(`order-add-${secondId}`).click()
  await page.getByTestId('order-save').click()
  await expect(page.getByTestId('order-saved')).toBeVisible()

  // --- przestawienie STRZAŁKĄ i zapis ---------------------------------------------
  await page.getByTestId(`order-down-${firstId}`).focus()
  await page.keyboard.press('Enter')
  const persistedOrder = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === `/api/v1/stores/${storeId}/category-order` &&
      response.request().method() === 'PUT',
  )
  await page.getByTestId('order-save').click()
  expect((await persistedOrder).ok()).toBe(true)
  await expect(page.getByTestId('order-saved')).toBeVisible()

  // --- kolejność przetrwała odświeżenie (dane, nie stan komponentu) ----------------
  await page.reload()
  await page.getByTestId('settings-tab-shopping').click()
  await page.getByTestId(`store-order-${storeId}`).click()
  await expect(page.getByTestId('category-order-editor')).toBeVisible()
  const rows = page.locator('[data-testid^="order-row-"]')
  await expect(rows.nth(0)).toHaveAttribute('data-testid', `order-row-${secondId}`)
  await expect(rows.nth(1)).toHaveAttribute('data-testid', `order-row-${firstId}`)

  // --- API potwierdza tę samą kolejność (kontrakt dla sortowania listy w B11) ------
  const order = await request.get(`/api/v1/stores/${storeId}/category-order`)
  expect(order.ok()).toBeTruthy()
  const body = (await order.json()) as { items: { category_id: number; position: number }[] }
  expect(body.items.map((item) => String(item.category_id))).toEqual([secondId, firstId])
})
