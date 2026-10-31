import { expect, test } from '@playwright/test'

import { EMPTY_STATE } from './auth-state.js'
import { cleanupE2eData } from './cleanup.js'
import { reserveLoginAttempt } from './login-budget.js'

/**
 * Smoke E2E (08_TESTING §3): logowanie → plan dnia → dodanie posiłku i pozycji
 * → przeliczenie wartości po zmianie mnożnika → wylogowanie.
 *
 * Zakres rozszerzony w BATCH_06: od tego batcha `/plan-dnia` to prawdziwy widok
 * (wcześniej placeholder), więc smoke sprawdza realny przepływ planowania.
 *
 * Konto testowe zakłada `task create-admin` (nigdy seed z hasłem w repo,
 * 07_SECURITY §2); dane logowania przychodzą ze zmiennych środowiskowych.
 * Brak zmiennych = błąd testu, nie pominięcie (08_TESTING §6).
 */
const email = process.env.E2E_ADMIN_EMAIL ?? ''
const password = process.env.E2E_ADMIN_PASSWORD ?? ''

test.beforeAll(() => {
  if (!email || !password) {
    throw new Error(
      'Brak E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD w .env. Utwórz konto komendą ' +
        '`task create-admin` i wpisz te same dane do .env (patrz .env.example).',
    )
  }
})

test.describe('uwierzytelnianie (bez współdzielonej sesji)', () => {
  // Te cztery testy sprawdzają SAMO logowanie, więc nie mogą startować
  // z sesją z `auth.setup.ts` — zerujemy `storageState` dla całej grupy.
  test.use({ storageState: EMPTY_STATE })

  test('strona /login renderuje aktywny formularz logowania', async ({ page }) => {
    await page.goto('/login')

    await expect(page.getByTestId('login-card')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Zaloguj się' })).toBeVisible()
    await expect(page.getByTestId('login-submit')).toBeEnabled()
  })

  test('nieznana sesja odsyła z sekcji chronionej na /login', async ({ page }) => {
    await page.goto('/plan-dnia')

    await expect(page).toHaveURL(/\/login/)
  })

  test('błędne hasło pokazuje neutralny komunikat', async ({ page, baseURL }, testInfo) => {
    await page.goto('/login')

    await page.getByTestId('login-email').fill(email)
    await page.getByTestId('login-password').fill('na-pewno-zle-haslo-2026')
    await reserveLoginAttempt(baseURL, testInfo)
    await page.getByTestId('login-submit').click()

    await expect(page.getByTestId('login-error')).toHaveText('Nieprawidłowy email lub hasło.')
    await expect(page).toHaveURL(/\/login/)
  })

  test('logowanie → plan dnia → wylogowanie', async ({ page, baseURL }, testInfo) => {
    await page.goto('/login')

    await page.getByTestId('login-email').fill(email)
    await page.getByTestId('login-password').fill(password)
    await reserveLoginAttempt(baseURL, testInfo)
    await page.getByTestId('login-submit').click()

    await expect(page).toHaveURL(/\/plan-dnia/)
    await expect(page.getByTestId('plan-dnia-page')).toBeVisible()
    await expect(page.getByTestId('nav-sidebar')).toBeVisible()

    await page.getByTestId('account-toggle').click()
    await page.getByTestId('logout-button').click()

    await expect(page).toHaveURL(/\/login/)
    await expect(page.getByTestId('login-card')).toBeVisible()

    // Sesja jest unieważniona po stronie serwera — powrót „wstecz" nie wskrzesza jej.
    await page.goto('/plan-dnia')
    await expect(page).toHaveURL(/\/login/)
  })
})

/**
 * Prefiks i data planu są STAŁE, a sprzątanie jest po obu stronach testu:
 * `beforeAll` leczy stan po przebiegu przerwanym w połowie, `afterAll` wykonuje
 * się także po nieudanym teście. Bez tego drugi przebieg padał na `plan-empty`
 * (posiłek z poprzedniego) i na ukrytej opcji „+ Dodaj" (szukajka trigramowa
 * znajdowała starą „Owsiankę E2E") — ustalenie R2, dług U15.
 */
const PREFIX = 'E2E smoke'
const DAY = '2031-03-05'

test.describe('plan dnia (własne dane, sprzątane po obu stronach)', () => {
  test.beforeAll(async ({ request }) => {
    await cleanupE2eData(request, { namePrefix: PREFIX, dates: [DAY] })
  })

  test.afterAll(async ({ request }) => {
    await cleanupE2eData(request, { namePrefix: PREFIX, dates: [DAY] })
  })

  test('plan dnia: posiłek → pozycja z przepisu → zmiana mnożnika przelicza wszystko', async ({
    page,
  }) => {
    const stamp = Date.now()
    const recipeName = `${PREFIX} Owsianka ${stamp}`
    const day = DAY

    page.on('dialog', (dialog) => dialog.accept())

    // Sesja pochodzi z `auth.setup.ts` (storageState) — bez tego suita
    // przekraczała limit 5 logowań/min na `/auth/login`.

    await page.goto(`/plan-dnia/${day}`)
    await expect(page.getByTestId('plan-dnia-page')).toBeVisible()
    await expect(page.getByTestId('plan-empty')).toBeVisible()

    // --- posiłek o własnej nazwie (dzień powstaje implicite) -------------------------
    await page.getByTestId('plan-add-meal').click()
    await page.getByTestId('meal-name-input').fill('II śniadanie')
    await page.getByTestId('meal-target-input').fill('300')
    await page.getByTestId('meal-submit').click()

    const mealCard = page.locator('[data-testid^="meal-card-"]').first()
    await expect(mealCard).toBeVisible()
    await expect(mealCard).toContainText('II śniadanie')

    // --- pozycja z przepisu (inline create w RecipePickerze) ---------------------------
    await page.locator('[data-testid^="meal-add-item-"]').first().click()
    await page.getByTestId('recipe-picker-input').fill(recipeName)
    await expect(page.getByTestId('recipe-picker-create')).toBeVisible()
    await page.getByTestId('recipe-picker-create').click()
    // `recipe-picker-create` tylko OTWIERA drawer — przepis powstaje po zapisie
    // formularza. Bez tego kroku picker nigdy nie dostaje zaznaczenia.
    await expect(page.getByTestId('recipe-create-drawer')).toBeVisible()
    await page.getByTestId('recipe-create-submit').click()
    await expect(page.getByTestId('recipe-picker-selected')).toContainText(recipeName)
    await page.getByTestId('recipe-planning-submit').click()

    const item = page.locator('[data-testid^="plan-item-servings-"]').first()
    await expect(item).toHaveText('1')

    // --- zmiana mnożnika przelicza pozycję, posiłek i dzień w jednym kroku -------------
    await page.locator('[data-testid^="plan-item-plus-"]').first().click()
    await expect(item).toHaveText('1,5')

    // Jedzenie i zwięzłe podsumowanie Cały plan pochodzą z tego samego planu
    // (spójność 02_DOMAIN §13.3), bez porównania z indywidualnym celem.
    await expect(page.getByTestId('plan-summary')).toBeVisible()
    await expect(page.getByTestId('plan-tile-kcal')).toBeVisible()

    // --- sprzątanie: usuwamy posiłek (kaskada zabiera pozycję) i przepis ---------------
    await page.locator('[data-testid^="meal-menu-"]').first().click()
    await page.locator('[data-testid^="meal-remove-"]').first().click()
    await expect(page.getByTestId('plan-empty')).toBeVisible()

    await page.goto('/przepisy')
    await page.getByTestId('recipes-search').fill(recipeName)
    await expect(page).toHaveURL((url) => url.searchParams.get('q') === recipeName)
    const card = page.locator('[data-testid^="recipe-card-"]').filter({
      has: page.getByRole('heading', { name: recipeName, exact: true }),
    })
    await expect(card).toHaveCount(1)
    await expect(card).toBeVisible()
    await card.getByTestId(/^recipe-open-/).click()
    await expect(page.getByTestId('recipe-name')).toHaveText(recipeName)
    await page.getByTestId('recipe-delete').click()
    await expect(page).toHaveURL(
      (url) => url.pathname === '/przepisy' && url.searchParams.get('q') === recipeName,
    )
  })
})
