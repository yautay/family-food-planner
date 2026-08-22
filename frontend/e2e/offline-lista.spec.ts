import { expect, test } from '@playwright/test'

import { cleanupE2eData } from './cleanup.js'

/**
 * Lista zakupowa działa BEZ SIECI (ADR-009, karta B12 §Tests, AC 2–5).
 *
 * Ścieżka: plan → generacja → lista → **odcięcie sieci** → dwa odhaczenia →
 * powrót sieci → reload → stan JEST NA SERWERZE. Potem to samo pod publicznym
 * linkiem `/l/{token}`, w kontekście bez sesji.
 *
 * Dlaczego to musi być E2E, a nie vitest: kolejka offline składa się z czterech
 * niezależnych mechanizmów przeglądarki (zdarzenia `online`/`offline`,
 * IndexedDB, cykl życia strony, prawdziwe żądania HTTP). Test jednostkowy
 * sprawdza każdy z nich osobno i przechodzi nawet wtedy, gdy razem nie działają
 * — a „razem" jest jedyną rzeczą, na której zależy osobie w sklepie.
 *
 * **Bez reloadu w trybie offline.** Suita jedzie na dev serverze Vite, gdzie
 * service worker jest świadomie WYŁĄCZONY (`devOptions.enabled: false`), żeby
 * precache nie zatruwał pracy. Odświeżenie strony bez sieci nie miałoby więc
 * skąd wziąć shella — to ograniczenie ŚRODOWISKA TESTOWEGO, nie aplikacji;
 * precache z buildu produkcyjnego weryfikuje Lighthouse (Verification checklist).
 * Trwałość snapshotu w IndexedDB pokrywa vitest (`hydrate.spec.ts`).
 */

/** Poniedziałek–niedziela w oknie E2E; inny tydzień niż pozostałe specy. */
const WEEK_START = '2033-05-02'
const WEEK_END = '2033-05-08'
const TOUCHED_DATES = Array.from(
  { length: 7 },
  (_, offset) => `2033-05-${String(offset + 2).padStart(2, '0')}`,
)

const PREFIX = 'E2E offline'

/** Produkty z seedu (`task db-seed-demo`) — dwie pozycje, dwa odhaczenia. */
const DURABLE_PRODUCT = 'Mąka pszenna typ 500'
const FRESH_PRODUCT = 'Pomidor'

test.beforeAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX, dates: TOUCHED_DATES })
})

test.afterAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX, dates: TOUCHED_DATES })
})

test('lista zakupowa offline: odhaczenia przeżywają brak sieci i trafiają na serwer', async ({
  page,
  browser,
}) => {
  page.on('dialog', (dialog) => dialog.accept())

  // --- plan: jeden posiłek, dwie pozycje --------------------------------------------
  await page.goto(`/plan-dnia/${WEEK_START}`)
  await expect(page.getByTestId('plan-dnia-page')).toBeVisible()
  await page.getByTestId('plan-add-meal').click()
  await page.getByTestId('meal-name-input').fill(`Obiad ${PREFIX}`)
  await page.getByTestId('meal-submit').click()
  for (const product of [DURABLE_PRODUCT, FRESH_PRODUCT]) {
    await page.locator('[data-testid^="meal-add-item-"]').first().click()
    await page.getByTestId('item-mode-product').click()
    await page.getByTestId('picker-input').fill(product)
    await page.locator('[data-testid^="picker-option-"]').first().click()
    await expect(page.getByTestId('picker-selected')).toContainText(product)
    await page.getByTestId('item-amount').fill('1400')
    await page.getByTestId('item-submit').click()
    await expect(page.locator('[data-testid^="plan-item-servings-"]').first()).toBeVisible()
  }

  // --- generacja i finalizacja ------------------------------------------------------
  await page.goto('/zakupy')
  await expect(page.getByTestId('zakupy-page')).toBeVisible()
  await page.getByTestId('zakupy-date-from').fill(WEEK_START)
  await page.getByTestId('zakupy-date-to').fill(WEEK_END)
  await page.getByTestId('zakupy-generate').click()
  await expect(page.getByTestId('zakupy-preview')).toBeVisible()
  await page.getByTestId('preview-finalize').click()
  await expect(page.getByTestId('zakupy-created-lists')).toBeVisible()

  await page.locator('[data-testid^="created-list-link-"]').first().click()
  await expect(page.getByTestId('lista-zakupowa-page')).toBeVisible()
  const listUrl = page.url()

  const checkboxes = page.locator('[data-testid^="shopping-check-"]')
  await expect(checkboxes).toHaveCount(2)
  const ids = await checkboxes.evaluateAll((nodes) =>
    nodes.map((node) => (node.getAttribute('data-testid') ?? '').replace('shopping-check-', '')),
  )
  const [first, second] = ids
  expect(first).toBeTruthy()
  expect(second).toBeTruthy()

  // Online kolejka jest pusta, więc paska nie ma w ogóle (06_UIUX §5 — bez szumu).
  await expect(page.getByTestId('offline-banner')).toHaveCount(0)

  // --- ODCIĘCIE SIECI ----------------------------------------------------------------
  await page.context().setOffline(true)
  await expect(page.getByTestId('offline-banner')).toContainText('Tryb offline')

  await page.getByTestId(`shopping-check-${first}`).check()
  await page.getByTestId(`shopping-check-${second}`).check()

  // UI reaguje NATYCHMIAST (AC 3), a licznik pokazuje, ile czeka (AC 5).
  await expect(page.getByTestId('lista-progress')).toContainText('Odhaczone 2 z 2')
  await expect(page.getByTestId('offline-pending')).toContainText('2')

  // Zmiana sklepu offline jest zablokowana: kolejność sekcji układa serwer
  // z profilu sklepu, a przeglądarka go nie zna (ustalenie R3).
  await expect(page.getByTestId('lista-sklep')).toContainText('Zmiana sklepu wymaga połączenia')

  // --- SIEĆ WRACA: kolejka sama się opróżnia -----------------------------------------
  await page.context().setOffline(false)
  await expect(page.getByTestId('offline-banner')).toHaveCount(0)

  // Dowód, że zmiany są NA SERWERZE, a nie tylko w pamięci karty.
  await page.goto(listUrl)
  await expect(page.getByTestId(`shopping-check-${first}`)).toBeChecked()
  await expect(page.getByTestId(`shopping-check-${second}`)).toBeChecked()
  await expect(page.getByTestId('lista-progress')).toContainText('Odhaczone 2 z 2')

  // --- ten sam mechanizm pod publicznym linkiem, BEZ logowania -----------------------
  await page.getByTestId('lista-share-open').click()
  await expect(page.getByTestId('share-dialog')).toBeVisible()
  await page.getByTestId('share-create').click()
  const shareUrl = ((await page.getByTestId('share-url').textContent()) ?? '').trim()
  const publicPath = new URL(shareUrl).pathname

  const anonymous = await browser.newContext()
  const anonymousPage = await anonymous.newPage()
  await anonymousPage.goto(publicPath)
  await expect(anonymousPage.getByTestId('public-list-page')).toBeVisible()
  await expect(anonymousPage.getByTestId(`shopping-check-${first}`)).toBeChecked()

  await anonymous.setOffline(true)
  await expect(anonymousPage.getByTestId('offline-banner')).toContainText('Tryb offline')
  // Odznaczenie offline: decyzja MŁODSZA niż zapisana na serwerze, więc po
  // synchronizacji ma wygrać LWW (ADR-009), a nie zostać odrzucona.
  await anonymousPage.getByTestId(`shopping-check-${first}`).uncheck()
  await expect(anonymousPage.getByTestId('public-list-meta')).toContainText('Odhaczone 1 z 2')

  await anonymous.setOffline(false)
  await expect(anonymousPage.getByTestId('offline-banner')).toHaveCount(0)

  // Stan wspólny: zalogowany widzi odznaczenie zrobione offline pod linkiem.
  await page.goto(listUrl)
  await expect(page.getByTestId(`shopping-check-${first}`)).not.toBeChecked()
  await expect(page.getByTestId('lista-progress')).toContainText('Odhaczone 1 z 2')

  await anonymous.close()
})
