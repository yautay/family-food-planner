import { expect, test } from '@playwright/test'

/**
 * Core flow BATCH_03 (08_TESTING §3): ADMIN tworzy rodzinę i przypisuje do niej
 * konto → użytkownik widzi rodzinę w Ustawieniach i dodaje profil członka.
 *
 * Test używa konta administratora z `.env` także w roli „użytkownika przypisanego
 * do rodziny" — E2E ma jedno konto o znanym haśle (07_SECURITY §2: żadnego
 * działającego hasła w repozytorium), a przypisanie samego siebie sprawdza
 * dokładnie tę samą ścieżkę serwera co przypisanie kogokolwiek innego.
 *
 * Test sprząta po sobie (profil → odpięcie konta → rodzina), więc kolejne
 * uruchomienia nie zostawiają śmieci w bazie dev.
 */

/** Konto z sesji `auth.setup.ts` — spec przypisuje je do rodziny, więc zna jego email. */
const email = process.env.E2E_ADMIN_EMAIL ?? ''

test('admin tworzy rodzinę, przypisuje konto, użytkownik dodaje profil', async ({ page }) => {
  // Nazwa unikalna per przebieg — test ma być powtarzalny bez czyszczenia bazy.
  const householdName = `E2E Rodzina ${Date.now()}`
  const profileName = 'Zosia E2E'

  page.on('dialog', (dialog) => dialog.accept())

  // Sesja pochodzi z `auth.setup.ts` (storageState) — patrz
  // `playwright.config.ts`. Logowanie per spec przekraczało limit 5/min.

  // --- ADMIN: tworzy rodzinę ------------------------------------------------
  await page.goto('/admin/rodziny')
  await expect(page.getByTestId('admin-households-page')).toBeVisible()

  await page.getByTestId('new-household-name').fill(householdName)
  await page.getByTestId('new-household-submit').click()

  const row = page.locator('[data-testid^="household-row-"]', { hasText: householdName })
  await expect(row).toBeVisible()
  const householdId = (await row.getAttribute('data-testid'))!.replace('household-row-', '')

  // --- ADMIN: przypisuje konto ----------------------------------------------
  const select = page.getByTestId('household-assign-select')
  await expect(select).toBeVisible()
  // Vue wiąże `:value` jako WŁAŚCIWOŚĆ elementu, nie atrybut — `getAttribute('value')`
  // zwróciłoby tu `null` i selectOption po cichu wyczyściłby wybór.
  const optionValue = await select
    .locator('option', { hasText: email })
    .evaluate((option) => (option as unknown as { value: string }).value)
  expect(optionValue, `Konto ${email} musi być na liście kont do przypisania`).toBeTruthy()
  await select.selectOption(optionValue)
  // Status odpowiedzi sprawdzamy jawnie: gdy serwer odmówi, komunikat błędu jest
  // znacznie bardziej wymowny niż „nie znaleziono elementu" pięć sekund później.
  const [assignResponse] = await Promise.all([
    page.waitForResponse((response) => response.url().includes('/members')),
    page.getByTestId('household-assign-submit').click(),
  ])
  expect(assignResponse.status(), await assignResponse.text()).toBe(200)

  await expect(row.locator('[data-testid^="household-member-"]')).toContainText(email)

  // --- UŻYTKOWNIK: widzi rodzinę i dodaje profil ------------------------------
  await page.goto('/ustawienia')
  await expect(page.getByTestId('household-name')).toHaveText(householdName)
  await expect(page.getByTestId('household-members')).toContainText(email)

  await page.getByTestId('profile-add').click()
  await page.getByTestId('profile-name').fill(profileName)
  await page.getByTestId('profile-multiplier').fill('0,8')
  await page.getByTestId('profile-kcal').fill('1400')
  await page.getByTestId('profile-submit').click()

  const profileRow = page.locator('[data-testid^="profile-row-"]', { hasText: profileName })
  await expect(profileRow).toBeVisible()
  await expect(profileRow).toContainText('0,80')

  // --- sprzątanie -------------------------------------------------------------
  await profileRow.locator('[data-testid^="profile-delete-"]').click()
  await expect(profileRow).toHaveCount(0)

  await page.goto('/admin/rodziny')
  await page.getByTestId(`household-select-${householdId}`).click()
  await row.locator('[data-testid^="household-detach-"]').first().click()
  await expect(row.locator('[data-testid^="household-member-"]')).toHaveCount(0)

  await page.getByTestId(`household-delete-${householdId}`).click()
  await expect(row).toHaveCount(0)
})
