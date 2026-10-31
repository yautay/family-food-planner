import { expect, test } from '@playwright/test'

import { cleanupE2eData } from './cleanup.js'

/**
 * Core flow 3 (08_TESTING §3.2): zakupy od planu do list.
 *
 * Ścieżka: plan dnia (dwie pozycje z produktów seedu) → `/zakupy` → jawne
 * zaznaczenie „Uwzględnić stan domowy?" → podgląd z opakowaniami i resztkami →
 * toggle „mam już w domu" → finalizacja → listy utworzone per tura.
 *
 * **Spec pracuje na produktach z seedu demo** (`task db-seed-demo`, 08_TESTING
 * §5), a nie na własnych. To nie oszczędność, a wymóg sprzątania: pozycja
 * finalnej listy zakupowej trzyma produkt i wariant sklepowy FK RESTRICT
 * (ADR-012), a listy zakupowej ten batch jeszcze nie umie usunąć (to BATCH_11).
 * Własny produkt zostałby więc w bazie na zawsze i zatruwałby szukajkę
 * trigramową w kolejnych przebiegach — dokładnie ten dług, który R2 zamykał dla
 * przepisów. Produkty seedu są trwałe i mają warianty sklepowe z opakowaniami,
 * więc podgląd pokazuje realne „2 × 1 kg" i „Zostanie: 610 g".
 *
 * Konto testowe zakłada `task create-admin` (nigdy seed z hasłem w repo,
 * 07_SECURITY §2). Daty są w oknie zarezerwowanym dla E2E (lata 2030+).
 */

/** Poniedziałek–niedziela w oknie E2E (2033-03-07 to poniedziałek). */
const WEEK_START = '2033-03-07'
const WEEK_END = '2033-03-13'
const TOUCHED_DATES = Array.from(
  { length: 7 },
  (_, offset) => `2033-03-${String(offset + 7).padStart(2, '0')}`,
)

const PREFIX = 'E2E zakupy'

/**
 * Produkty z seedu demo: pierwszy TRWAŁY (ma opakowania 1 kg i 2 kg — widać
 * wybór wariantu i resztkę), drugi ŚWIEŻY (trafia do obu tur, bo okno świeżych
 * presetu ma 4 dni z 7).
 */
const DURABLE_PRODUCT = 'Mąka pszenna typ 500'
const FRESH_PRODUCT = 'Pomidor'

test.beforeAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX, dates: TOUCHED_DATES })
})

test.afterAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX, dates: TOUCHED_DATES })
})

test('zakupy: plan → podgląd ze spiżarnią → „mam w domu" → listy per tura', async ({ page }) => {
  page.on('dialog', (dialog) => dialog.accept())

  // --- plan: dwie pozycje z produktów seedu w dwóch różnych dniach -------------------
  for (const [index, day] of [WEEK_START, WEEK_END].entries()) {
    await page.goto(`/plan-dnia/${day}`)
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
      await page.getByTestId('item-amount').fill(index === 0 ? '400' : '300')
      await page.getByTestId('item-submit').click()
      await expect(page.locator('[data-testid^="plan-item-servings-"]').first()).toBeVisible()
    }
  }

  // --- zakupy: tury z presetu + jawna zgoda na spiżarnię -----------------------------
  await page.goto('/zakupy')
  await expect(page.getByTestId('zakupy-page')).toBeVisible()
  // Preset niedziela/środa zasiewa backend przy pierwszym GET (02_DOMAIN §9.2).
  await expect(page.getByTestId('round-configs-list')).toContainText('Niedziela')
  await expect(page.getByTestId('round-configs-list')).toContainText('Środa')

  const pantryCheckbox = page.getByTestId('zakupy-use-pantry')
  // Kluczowa asercja karty B10: checkbox jest ODZNACZONY, dopóki człowiek go
  // nie zaznaczy (02_DOMAIN §8).
  await expect(pantryCheckbox).not.toBeChecked()
  await page.getByTestId('zakupy-date-from').fill(WEEK_START)
  await page.getByTestId('zakupy-date-to').fill(WEEK_END)
  await pantryCheckbox.check()

  await page.getByTestId('zakupy-generate').click()
  await expect(page.getByTestId('zakupy-preview')).toBeVisible()

  // --- podgląd: tury, opakowania, resztki, panel spiżarni ---------------------------
  const preview = page.getByTestId('zakupy-preview')
  await expect(preview).toContainText('Niedziela')
  await expect(preview).toContainText('Środa')
  await expect(preview).toContainText(DURABLE_PRODUCT.slice(0, 4))
  // Resztka jest zawsze wyeksponowana (02_DOMAIN §9.3).
  await expect(page.locator('[data-testid^="leftover-badge"]').first()).toBeVisible()
  // Panel odjęć pojawia się tylko przy jawnej zgodzie — i tu ją daliśmy.
  await expect(page.getByTestId('preview-pantry-panel')).toBeVisible()

  // --- toggle „mam już w domu" ------------------------------------------------------
  const firstToggle = page.locator('[data-testid^="preview-toggle-have-"]').first()
  const toggleId = (await firstToggle.getAttribute('data-testid')) ?? ''
  const productId = toggleId.replace('preview-toggle-have-', '')
  await firstToggle.check()
  // `already_have` jest decyzją o PRODUKCIE, więc produkt świeży oznacza się
  // w obu turach naraz — dlatego `first()`, a nie pojedynczy element.
  await expect(page.getByTestId(`preview-already-have-${productId}`).first()).toBeVisible()

  // --- finalizacja: listy per tura --------------------------------------------------
  const finalize = page.getByTestId('preview-finalize')
  await expect(finalize).toBeEnabled()
  await finalize.click()

  const created = page.getByTestId('zakupy-created-lists')
  await expect(created).toBeVisible()
  await expect(created).toContainText('Niedziela')
  await expect(created.locator('[data-testid^="created-list-"]').first()).toBeVisible()
})
