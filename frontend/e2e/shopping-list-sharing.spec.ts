import { expect, test } from '@playwright/test'

import { cleanupE2eData } from './cleanup.js'

/**
 * Core flow 3 DOMKNIĘTY (08_TESTING §3, karta B11 §Tests).
 *
 * Ścieżka: plan → zakupy z jawnym pytaniem o spiżarnię → podgląd z resztkami →
 * finalizacja → strona listy → odhaczenie → udostępnienie → otwarcie
 * `/l/{token}` w **kontekście BEZ SESJI** → odhaczenie bez logowania → stan
 * widoczny u zalogowanego po odświeżeniu → odwołanie linku → ekran wygaśnięcia.
 *
 * Dlaczego osobny kontekst przeglądarki, a nie druga karta: `browser.newContext()`
 * startuje bez `storageState`, więc nie ma ciasteczka sesji. Gdybyśmy otworzyli
 * publiczny link w tej samej sesji, test przechodziłby także wtedy, gdy strona
 * publiczna po cichu korzysta z cookies — czyli dokładnie w sytuacji, której
 * ADR-010 zabrania.
 *
 * Spec pracuje na produktach SEEDU (`task db-seed-demo`, 08_TESTING §5), jak
 * `shopping-generate`: pozycje listy trzymają produkt i wariant sklepowy
 * FK RESTRICT, a listy z okna E2E sprząta `clearShoppingLists`.
 */

/** Poniedziałek–niedziela w oknie E2E (2033-04-04 to poniedziałek). */
const WEEK_START = '2033-04-04'
const WEEK_END = '2033-04-10'
const TOUCHED_DATES = Array.from(
  { length: 7 },
  (_, offset) => `2033-04-${String(offset + 4).padStart(2, '0')}`,
)

const PREFIX = 'E2E lista'

/**
 * Produkty z seedu. Trwały ma opakowania (widać resztkę), świeży dokłada DRUGĄ
 * pozycję do tej samej listy — jedna pozycja nie wystarczy, bo zalogowany
 * i osoba z linkiem mają odhaczyć RÓŻNE pozycje.
 */
const DURABLE_PRODUCT = 'Mąka pszenna typ 500'
const FRESH_PRODUCT = 'Pomidor'

test.beforeAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX, dates: TOUCHED_DATES })
})

test.afterAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX, dates: TOUCHED_DATES })
})

test('lista zakupowa: sklep → odhaczanie → publiczny link bez logowania → odwołanie', async ({
  page,
  browser,
}) => {
  page.on('dialog', (dialog) => dialog.accept())

  // --- plan: dwie pozycje w jednym posiłku (dwie pozycje na liście) -----------------
  await page.goto(`/plan-dnia/${WEEK_START}`)
  await expect(page.getByTestId('plan-dnia-page')).toBeVisible()
  await page.getByTestId('plan-add-meal').click()
  await page.getByTestId('meal-name-input').fill(`Obiad ${PREFIX}`)
  await page.getByTestId('meal-submit').click()
  for (const product of [DURABLE_PRODUCT, FRESH_PRODUCT]) {
    const addProduct = page.locator('[data-testid^="meal-add-product-"]').first()
    if (!(await addProduct.isVisible()))
      await page.locator('[data-testid^="meal-menu-"]').first().click()
    await addProduct.click()
    await page.getByTestId('picker-input').fill(product)
    await page.locator('[data-testid^="picker-option-"]').first().click()
    await expect(page.getByTestId('picker-selected')).toContainText(product)
    await page.getByTestId('item-amount').fill('1400')
    await page.getByTestId('item-submit').click()
    await expect(page.locator('[data-testid^="plan-item-servings-"]').first()).toBeVisible()
  }

  // --- zakupy: jawne pytanie o spiżarnię → podgląd → finalizacja --------------------
  await page.goto('/zakupy')
  await expect(page.getByTestId('zakupy-page')).toBeVisible()
  const pantryCheckbox = page.getByTestId('zakupy-use-pantry')
  await expect(pantryCheckbox).not.toBeChecked()
  await page.getByTestId('zakupy-date-from').fill(WEEK_START)
  await page.getByTestId('zakupy-date-to').fill(WEEK_END)
  await pantryCheckbox.check()
  await page.getByTestId('zakupy-generate').click()

  await expect(page.getByTestId('zakupy-preview')).toBeVisible()
  // Resztka jest zawsze eksponowana już w podglądzie (02_DOMAIN §9.3).
  await expect(page.locator('[data-testid^="leftover-badge"]').first()).toBeVisible()
  await page.getByTestId('preview-finalize').click()
  await expect(page.getByTestId('zakupy-created-lists')).toBeVisible()

  // --- strona listy: sekcje, checkbox 48 px, trwałe odhaczenie ---------------------
  await page.locator('[data-testid^="created-list-link-"]').first().click()
  await expect(page.getByTestId('lista-zakupowa-page')).toBeVisible()
  await expect(page.getByTestId('lista-nazwa')).toContainText('Zakupy')

  // Dwie pozycje: pierwszą odhacza zalogowany, drugą osoba z publicznym linkiem.
  const checkboxes = page.locator('[data-testid^="shopping-check-"]')
  await expect(checkboxes).toHaveCount(2)
  const itemId = ((await checkboxes.first().getAttribute('data-testid')) ?? '').replace(
    'shopping-check-',
    '',
  )
  const publicItemId = ((await checkboxes.nth(1).getAttribute('data-testid')) ?? '').replace(
    'shopping-check-',
    '',
  )
  await checkboxes.first().check()
  await expect(page.getByTestId('lista-progress')).toContainText('Odhaczone 1')

  // Odhaczenie MUSI przetrwać odświeżenie (AC 1) — inaczej optimistic update
  // byłby tylko efektem wizualnym.
  await page.reload()
  await expect(page.getByTestId(`shopping-check-${itemId}`)).toBeChecked()

  // --- udostępnienie: link + QR ----------------------------------------------------
  await page.getByTestId('lista-share-open').click()
  await expect(page.getByTestId('share-dialog')).toBeVisible()
  await page.getByTestId('share-create').click()
  await expect(page.getByTestId('share-url')).toBeVisible()
  const shareUrl = ((await page.getByTestId('share-url').textContent()) ?? '').trim()
  expect(shareUrl).toMatch(/\/l\/[A-Za-z0-9_-]{43}$/)

  // QR renderuje się kliencko z PEŁNEGO adresu (ADR-010).
  await page.getByTestId('share-qr').click()
  await expect(page.getByTestId('share-qr-image')).toBeVisible()

  // --- publiczna strona w kontekście BEZ SESJI -------------------------------------
  const publicPath = new URL(shareUrl).pathname
  const anonymous = await browser.newContext()
  const anonymousPage = await anonymous.newPage()
  await anonymousPage.goto(publicPath)
  await expect(anonymousPage.getByTestId('public-list-page')).toBeVisible()
  // Zero danych rodziny: nie ma shella, nawigacji ani przycisku wylogowania.
  await expect(anonymousPage.getByTestId('nav-sidebar')).toHaveCount(0)
  await expect(anonymousPage.getByTestId('logout-button')).toHaveCount(0)

  // Stan z serwera jest wspólny: pozycja odhaczona przez zalogowanego przychodzi
  // odhaczona także tutaj (to samo `checked`, ten sam wiersz w bazie).
  await expect(anonymousPage.getByTestId(`shopping-check-${itemId}`)).toBeChecked()

  // Odhaczenie BEZ logowania — pozycja, której zalogowany nie dotknął.
  await anonymousPage.getByTestId(`shopping-check-${publicItemId}`).check()
  await expect(anonymousPage.getByTestId('public-list-meta')).toContainText('Odhaczone 2 z 2')

  // --- stan widoczny u zalogowanego po odświeżeniu ---------------------------------
  await page.reload()
  await expect(page.getByTestId(`shopping-check-${publicItemId}`)).toBeChecked()
  await expect(page.getByTestId('lista-progress')).toContainText('Odhaczone 2 z 2')

  // --- odwołanie linku → ekran wygaśnięcia na publicznej stronie -------------------
  // Panel trzeba OTWORZYĆ ponownie: `page.reload()` powyżej wyzerował stan UI
  // (otwarcie panelu to stan komponentu, nie adres). Potwierdzenie
  // `window.confirm` łapie handler `dialog` z góry testu.
  await page.getByTestId('lista-share-open').click()
  await expect(page.getByTestId('share-dialog')).toBeVisible()
  await page.getByTestId('share-revoke').click()
  await expect(page.getByTestId('share-revoked')).toBeVisible()

  await anonymousPage.reload()
  await expect(anonymousPage.getByTestId('public-list-unavailable')).toContainText(
    'Ta lista zakupowa już wygasła lub została usunięta.',
  )

  await anonymous.close()
})
