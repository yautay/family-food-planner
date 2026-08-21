import type { Locator } from '@playwright/test'
import { expect, test } from '@playwright/test'

import { cleanupE2eData } from './cleanup.js'

/**
 * Core flow 2 (08_TESTING §3.2): tydzień przez szablon i cykl.
 *
 * Ścieżka: login → zbuduj dzień (posiłek z przepisem) → widok tygodnia →
 * zapisz jako szablon dnia → zastosuj na 2 inne dni → zapisz tydzień jako
 * szablon → utwórz cykl z tego szablonu → zastosuj cykl na następny tydzień →
 * siatka pokazuje skopiowane posiłki, `BarChart` jest niezerowy → przenieś
 * posiłek między dniami.
 *
 * Przeniesienie posiłku testujemy WARIANTEM PRZYCISKOWYM („Przenieś do dnia…"),
 * nie drag&dropem: DnD w CI jest chwiejny, a wariant przyciskowy jest
 * obowiązkowy (06_UIUX §2) i jest jedyną drogą na telefonie. Sam DnD pokrywa
 * ręczna weryfikacja na desktopie (karta B07 §Verification checklist).
 *
 * Konto testowe zakłada `task create-admin` (nigdy seed z hasłem w repo,
 * 07_SECURITY §2). Brak zmiennych = błąd testu, nie pominięcie (08_TESTING §6).
 *
 * Daty są w odległej przyszłości i unikalne per przebieg, żeby test nie mieszał
 * się z ręcznym klikaniem po „dziś" ani z innymi przebiegami.
 */

/** Poniedziałki dwóch kolejnych tygodni roku 2032 (2032-03-01 to poniedziałek). */
const WEEK_START = '2032-03-01'
const NEXT_WEEK_START = '2032-03-08'
const TUESDAY = '2032-03-02'
const WEDNESDAY = '2032-03-03'
const THURSDAY = '2032-03-04'

/**
 * Wspólny prefiks nazw + pełny zakres dat, których spec dotyka.
 *
 * Ten spec zostawiał najwięcej śmieci (przepis, szablon dnia, szablon
 * tygodnia, cykl i dwa tygodnie planu) i NIC nie sprzątał, więc drugi przebieg
 * padał na `expect(targetDay).toContainText('Brak posiłków')` — czwartek miał
 * już posiłek z poprzedniego uruchomienia. Sprzątanie po obu stronach testu
 * (`beforeAll` leczy stan po przerwanym przebiegu) jest właściwą naprawą,
 * nie osłabienie asercji (ustalenie R2, dług U15).
 */
const PREFIX = 'E2E tydzien'

/**
 * Produkt z seedu demo (`task db-seed-demo`, 08_TESTING §5) — 353 kcal/100 g.
 *
 * Po co: przepis z inline create ma tylko nazwę i porcję bazową, więc dzień
 * zbudowany wyłącznie z niego ma ZERO kcal, a wtedy `BarChart` renderuje
 * komunikat „brak danych" zamiast słupków i asercja „przynajmniej jeden słupek
 * > 0" jest niespełnialna z definicji (ustalenie R2 — poprawka z B07 zmieniła
 * sposób pomiaru słupka, ale nie to, że dane były zerowe). Dopisanie pozycji
 * z produktem, który MA wartości, daje tygodniowi realne kalorie i zamienia tę
 * asercję w prawdziwy test: „cykl skopiował plan RAZEM z jego wartościami".
 */
const SEED_PRODUCT = 'Ryż brązowy'
const TOUCHED_DATES = Array.from(
  { length: 14 },
  (_, offset) => `2032-03-${String(offset + 1).padStart(2, '0')}`,
)

test.beforeAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX, dates: TOUCHED_DATES })
})

test.afterAll(async ({ request }) => {
  await cleanupE2eData(request, { namePrefix: PREFIX, dates: TOUCHED_DATES })
})

/**
 * Wybiera opcję `<select>` po FRAGMENCIE tekstu.
 *
 * `selectOption` przyjmuje wyłącznie dokładny `label` albo `value`, a etykiety
 * szablonów zawierają doklejone podsumowanie („Szablon dnia 123 · 1 posiłek,
 * 1 pozycja"), więc dopasowujemy tekst i wybieramy po `value`.
 */
async function selectByText(select: Locator, fragment: string): Promise<void> {
  const value = await select.locator('option', { hasText: fragment }).first().getAttribute('value')
  if (value === null) {
    throw new Error(`Brak opcji zawierającej „${fragment}" w liście wyboru.`)
  }
  await select.selectOption(value)
}

test('tydzień przez szablon i cykl: dzień → szablon → daty → tydzień → cykl → przeniesienie', async ({
  page,
}) => {
  const stamp = Date.now()
  const recipeName = `${PREFIX} Zupa ${stamp}`
  const dayTemplateName = `${PREFIX} Szablon dnia ${stamp}`
  const weekTemplateName = `${PREFIX} Szablon tygodnia ${stamp}`
  const cycleName = `${PREFIX} Cykl ${stamp}`

  page.on('dialog', (dialog) => dialog.accept())

  // --- login ------------------------------------------------------------------------
  // Sesja pochodzi z `auth.setup.ts` (storageState) — patrz
  // `playwright.config.ts`. Logowanie per spec przekraczało limit 5/min.

  // --- dzień źródłowy: posiłek + pozycja z przepisu (inline create) ------------------
  await page.goto(`/plan-dnia/${WEEK_START}`)
  await expect(page.getByTestId('plan-dnia-page')).toBeVisible()

  await page.getByTestId('plan-add-meal').click()
  await page.getByTestId('meal-name-input').fill('Obiad E2E')
  await page.getByTestId('meal-submit').click()

  await page.locator('[data-testid^="meal-add-item-"]').first().click()
  await page.getByTestId('recipe-picker-input').fill(recipeName)
  await expect(page.getByTestId('recipe-picker-create')).toBeVisible()
  await page.getByTestId('recipe-picker-create').click()
  // `recipe-picker-create` tylko OTWIERA drawer — przepis powstaje po zapisie
  // formularza. Bez tego kroku picker nigdy nie dostaje zaznaczenia.
  await expect(page.getByTestId('recipe-create-drawer')).toBeVisible()
  await page.getByTestId('recipe-create-submit').click()
  await expect(page.getByTestId('recipe-picker-selected')).toContainText(recipeName)
  await page.getByTestId('item-submit').click()
  await expect(page.locator('[data-testid^="plan-item-servings-"]').first()).toBeVisible()

  // --- druga pozycja: produkt luzem z seedu (dzień musi mieć realne kcal) ------------
  await page.locator('[data-testid^="meal-add-item-"]').first().click()
  await page.getByTestId('item-mode-product').click()
  await page.getByTestId('picker-input').fill(SEED_PRODUCT)
  await page.locator('[data-testid^="picker-option-"]').first().click()
  await expect(page.getByTestId('picker-selected')).toContainText(SEED_PRODUCT)
  await page.getByTestId('item-amount').fill('100')
  await page.getByTestId('item-submit').click()
  await expect(page.getByTestId('plan-tile-kcal')).toContainText('353')

  // --- widok tygodnia widzi ten dzień -----------------------------------------------
  await page.goto(`/tydzien/${WEEK_START}`)
  await expect(page.getByTestId('plan-tygodnia-page')).toBeVisible()
  await expect(page.getByTestId(`week-day-${WEEK_START}`)).toContainText('Obiad E2E')

  // --- zapisz dzień jako szablon ------------------------------------------------------
  await page.getByTestId(`week-day-select-${WEEK_START}`).click()
  await page.getByTestId('action-template-save').click()
  await expect(page.getByTestId('template-save-dialog')).toBeVisible()
  await page.getByTestId('template-kind-day').check()
  await page.getByTestId('template-source-day').selectOption(WEEK_START)
  await page.getByTestId('template-name').fill(dayTemplateName)
  await page.getByTestId('template-save-dialog-submit').click()
  await expect(page.getByTestId('template-save-dialog')).toBeHidden()

  // --- zastosuj szablon dnia na 2 inne dni --------------------------------------------
  await page.getByTestId('action-template-apply').click()
  await expect(page.getByTestId('template-apply-dialog')).toBeVisible()
  await page.getByTestId('apply-kind-day').check()
  await selectByText(page.getByTestId('apply-day-template'), dayTemplateName)
  await page.getByTestId('apply-dates').fill(`${TUESDAY}\n${WEDNESDAY}`)
  await page.getByTestId('template-apply-dialog-submit').click()
  await expect(page.getByTestId('template-apply-dialog')).toBeHidden()

  await expect(page.getByTestId(`week-day-${TUESDAY}`)).toContainText('Obiad E2E')
  await expect(page.getByTestId(`week-day-${WEDNESDAY}`)).toContainText('Obiad E2E')

  // --- zapisz cały tydzień jako szablon -----------------------------------------------
  await page.getByTestId('action-template-save').click()
  await page.getByTestId('template-kind-week').check()
  await page.getByTestId('template-name').fill(weekTemplateName)
  await page.getByTestId('template-save-dialog-submit').click()
  await expect(page.getByTestId('template-save-dialog')).toBeHidden()

  // --- utwórz cykl z tego szablonu ----------------------------------------------------
  await page.getByTestId('action-cycle').click()
  await expect(page.getByTestId('cycle-editor-dialog')).toBeVisible()
  await page.getByTestId('cycle-mode-create').check()
  await page.getByTestId('cycle-name').fill(cycleName)
  await selectByText(page.getByTestId('cycle-template-to-add'), weekTemplateName)
  await page.getByTestId('cycle-add-template').click()
  await expect(page.getByTestId('cycle-template-list')).toContainText(weekTemplateName)
  await page.getByTestId('cycle-editor-dialog-submit').click()
  await expect(page.getByTestId('cycle-editor-dialog')).toBeHidden()

  // --- zastosuj cykl na NASTĘPNY tydzień ----------------------------------------------
  await page.getByTestId('action-cycle').click()
  await page.getByTestId('cycle-mode-apply').check()
  await selectByText(page.getByTestId('cycle-pick'), cycleName)
  await page.getByTestId('cycle-date-from').fill(NEXT_WEEK_START)
  await page.getByTestId('cycle-date-to').fill('2032-03-14')
  await page.getByTestId('cycle-editor-dialog-submit').click()
  await expect(page.getByTestId('cycle-editor-dialog')).toBeHidden()

  // --- siatka następnego tygodnia pokazuje skopiowane posiłki -------------------------
  await page.goto(`/tydzien/${NEXT_WEEK_START}`)
  await expect(page.getByTestId('plan-tygodnia-page')).toBeVisible()
  await expect(page.getByTestId(`week-day-${NEXT_WEEK_START}`)).toContainText('Obiad E2E')

  // BarChart jest niezerowy: przynajmniej jeden słupek ma wysokość > 0.
  //
  // NIE asercjonujemy `toBeVisible()` na słupku: `<rect>` o `height=0` (dzień
  // bez posiłków) ma zerowy bounding box, więc Playwright uznaje go za
  // niewidoczny — a pierwszy słupek w DOM to poniedziałek, który wcale nie musi
  // być dniem z danymi. Liczy się to, co wykres RAPORTUJE, czyli `data-height`.
  const bars = page.locator('[data-testid^="week-bar-chart-bar-"]')
  await expect(bars.first()).toBeAttached()
  const heights = await bars.evaluateAll((nodes) =>
    nodes.map((node) => Number(node.getAttribute('data-height') ?? '0')),
  )
  expect(Math.max(...heights)).toBeGreaterThan(0)

  // --- przeniesienie posiłku między dniami (WARIANT PRZYCISKOWY) ----------------------
  await page.goto(`/tydzien/${WEEK_START}`)
  const sourceDay = page.getByTestId(`week-day-${WEEK_START}`)
  const targetDay = page.getByTestId(`week-day-${THURSDAY}`)
  await expect(targetDay).toContainText('Brak posiłków')

  await sourceDay.locator('[data-testid^="week-meal-move-"]').first().click()
  await expect(page.getByTestId('move-meal-dialog')).toBeVisible()
  await page.getByTestId('move-meal-target').selectOption(THURSDAY)
  await page.getByTestId('move-meal-dialog-submit').click()
  await expect(page.getByTestId('move-meal-dialog')).toBeHidden()

  await expect(targetDay).toContainText('Obiad E2E')
  await expect(sourceDay).toContainText('Brak posiłków')
})
