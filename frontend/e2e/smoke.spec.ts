import { expect, test } from '@playwright/test'

/**
 * Smoke E2E (08_TESTING §3): logowanie → plan dnia → wylogowanie.
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

test('błędne hasło pokazuje neutralny komunikat', async ({ page }) => {
  await page.goto('/login')

  await page.getByTestId('login-email').fill(email)
  await page.getByTestId('login-password').fill('na-pewno-zle-haslo-2026')
  await page.getByTestId('login-submit').click()

  await expect(page.getByTestId('login-error')).toHaveText('Nieprawidłowy email lub hasło.')
  await expect(page).toHaveURL(/\/login/)
})

test('logowanie → plan dnia → wylogowanie', async ({ page }) => {
  await page.goto('/login')

  await page.getByTestId('login-email').fill(email)
  await page.getByTestId('login-password').fill(password)
  await page.getByTestId('login-submit').click()

  await expect(page).toHaveURL(/\/plan-dnia/)
  await expect(page.getByTestId('placeholder-page')).toBeVisible()
  await expect(page.getByTestId('nav-sidebar')).toBeVisible()

  await page.getByTestId('logout-button').click()

  await expect(page).toHaveURL(/\/login/)
  await expect(page.getByTestId('login-card')).toBeVisible()

  // Sesja jest unieważniona po stronie serwera — powrót „wstecz" nie wskrzesza jej.
  await page.goto('/plan-dnia')
  await expect(page).toHaveURL(/\/login/)
})
