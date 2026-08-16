import { expect, test } from '@playwright/test'

test('strona /login renderuje formularz logowania', async ({ page }) => {
  await page.goto('/login')

  await expect(page.getByTestId('login-card')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Zaloguj się' })).toBeVisible()
  // Logika logowania powstaje w BATCH_02 — tu sprawdzamy wyłącznie render.
  await expect(page.getByTestId('login-submit')).toBeDisabled()
})
