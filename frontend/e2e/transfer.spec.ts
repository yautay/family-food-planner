import { randomBytes } from 'node:crypto'

import { expect, test } from '@playwright/test'
import type { APIRequestContext, BrowserContext } from '@playwright/test'

import type { components } from '../src/api/generated.js'

import { EMPTY_STATE } from './auth-state.js'
import { csrfHeaders } from './cleanup.js'
import { reserveLoginAttempt } from './login-budget.js'

/**
 * Smoke transferu (karta B14 §Tests): Ustawienia → eksport (plik pobrany) →
 * import TEGO SAMEGO pliku → raport kolizji → apply → podsumowanie.
 *
 * Plik wraca na to samo konto, więc kolizje są GWARANTOWANE: przepis nosi tę
 * samą nazwę, a produkt ten sam `normalized_name`. To najostrzejszy wariant
 * scenariusza i jednocześnie ten, który użytkownik wykona pierwszy („czy mój
 * backup w ogóle się wczytuje?").
 *
 * Dla przepisu wybieramy „Utwórz kopię": domyślne „użyj istniejącego" nie
 * stworzyłoby niczego, więc podsumowanie nie miałoby czego pokazać.
 *
 * Każdy przebieg ma świeżego USER-a bez rodziny. Eksport współdzielonego
 * ADMIN-a niósłby całą jego historię zakupów, którą apply kopiuje ponownie.
 * Nie odwiedzamy Zakupów ani GET round-configs: ten odczyt zasiewa domyślne tury.
 */
const PREFIX = 'E2E transfer'
const RECIPE_NAME = `${PREFIX} Zupa`
const COPY_NAME = `${RECIPE_NAME} (import)`
/** Produkt z seedu demo (`task db-seed-demo`) — trwały, z kompletem wartości. */
const SEED_PRODUCT = 'Mąka pszenna typ 500'

const API = '/api/v1'

async function seedRecipe(request: APIRequestContext): Promise<void> {
  const headers = await csrfHeaders(request)
  const products = await request.get(
    `${API}/products?q=${encodeURIComponent(SEED_PRODUCT)}&limit=1`,
  )
  expect(products.ok(), await products.text()).toBe(true)
  const items = ((await products.json()) as components['schemas']['ProductListResponse']).items
  expect(
    items.length,
    `Seed demo musi zawierać „${SEED_PRODUCT}" (task db-seed-demo)`,
  ).toBeGreaterThan(0)

  const response = await request.post(`${API}/recipes`, {
    headers,
    data: {
      name: RECIPE_NAME,
      scope: 'private',
      instructions: 'Gotować.',
      base_servings: 2,
      ingredients: [{ product_id: items[0]!.id, quantity: '300', unit: 'g' }],
      tag_ids: [],
    },
  })
  expect(response.status(), await response.text()).toBe(201)
}

/** Wyłącznie dwa własne przepisy; bez globalnych słowników i danych ADMIN-a. */
async function cleanupOwnRecipes(request: APIRequestContext, userId: number): Promise<void> {
  const response = await request.get(`${API}/recipes`, {
    params: { scope: 'private', include_archived: true, limit: 200, offset: 0 },
  })
  expect(response.status(), await response.text()).toBe(200)
  const recipes = (await response.json()) as components['schemas']['RecipeListResponse']
  const headers = await csrfHeaders(request)
  for (const recipe of recipes.items) {
    if (
      recipe.owner_user_id === userId &&
      recipe.scope === 'private' &&
      (recipe.name === RECIPE_NAME || recipe.name === COPY_NAME)
    ) {
      const deleted = await request.delete(`${API}/recipes/${recipe.id}`, { headers })
      expect.soft(deleted.status(), await deleted.text()).toBe(204)
    }
  }
}

test('transfer: eksport moich danych, import tego pliku, kolizje i podsumowanie', async ({
  browser,
  request: admin,
  baseURL,
}, testInfo) => {
  const email = `e2e-transfer-${randomBytes(12).toString('hex')}@example.com`
  const password = `${randomBytes(24).toString('base64url')}aA1`
  const adminHeaders = await csrfHeaders(admin)
  const account = await admin.post(`${API}/admin/users`, {
    headers: adminHeaders,
    data: { email, password, display_name: PREFIX, role: 'user' },
  })
  expect(account.status(), 'ADMIN tworzy świeże konto transferu').toBe(201)
  const user = (await account.json()) as components['schemas']['UserRead']
  let context: BrowserContext | undefined
  let authenticated = false
  try {
    context = await browser.newContext({ baseURL, storageState: EMPTY_STATE })
    const request = context.request
    await reserveLoginAttempt(baseURL, testInfo)
    const login = await request.post(`${API}/auth/login`, { data: { email, password } })
    expect(login.status(), 'jedno logowanie własnego USER-a').toBe(200)
    authenticated = true
    const current = await request.get(`${API}/auth/me`)
    expect(current.status()).toBe(200)
    const actualCurrentUser = (await current.json()) as components['schemas']['CurrentUser']
    expect(actualCurrentUser.id).toBe(user.id)
    expect(actualCurrentUser.email).toBe(email)
    expect(actualCurrentUser.role).toBe('user')
    expect(actualCurrentUser.household).toBeNull()
    expect((await request.get(`${API}/admin/users`)).status()).toBe(403)

    await seedRecipe(request)
    const page = await context.newPage()
    await page.goto('/ustawienia')
    await expect(page.getByTestId('ustawienia-page')).toBeVisible()
    await page.getByTestId('settings-tab-data').click()
    await expect(page.getByTestId('transfer-scope')).toContainText('Nie zawiera prywatnych danych')

    // --- eksport: plik faktycznie się pobiera ---------------------------------------
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByTestId('transfer-export').click(),
    ])
    expect(download.suggestedFilename()).toContain('pasnik-export-')
    const archivePath = await download.path()
    expect(archivePath, 'Playwright musi mieć plik na dysku, żeby go odesłać').toBeTruthy()
    const savedArchivePath = testInfo.outputPath('transfer-roundtrip.zip')
    await download.saveAs(savedArchivePath)
    await expect(page.getByTestId('transfer-export-done')).toBeVisible()

    // --- import: krok 1 (plik) → krok 2 (raport dry-run) -----------------------------
    await page.getByTestId('transfer-import-open').click()
    await expect(page.getByTestId('transfer-import-dialog')).toBeVisible()
    await page.getByTestId('transfer-file').setInputFiles(savedArchivePath)

    const [dryRun] = await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().endsWith('/transfer/import') && response.request().method() === 'POST',
      ),
      page.getByTestId('transfer-analyze').click(),
    ])
    expect(dryRun.status(), await dryRun.text()).toBe(200)
    await expect(page.getByTestId('transfer-step-report')).toBeVisible()

    // Raport kolizji MUSI pokazać przepis o tej samej nazwie — plik wraca na to
    // samo konto, więc kolizja jest pewna.
    const collision = page
      .getByTestId('transfer-collisions')
      .locator('li')
      .filter({ hasText: RECIPE_NAME })
    await expect(collision).toHaveCount(1)
    await collision.getByRole('button', { name: 'Utwórz kopię' }).click()

    // --- apply: krok 3 (podsumowanie) ------------------------------------------------
    const [applied] = await Promise.all([
      page.waitForResponse((response) => response.url().includes('/transfer/import/')),
      page.getByTestId('transfer-confirm').click(),
    ])
    expect(applied.status(), await applied.text()).toBe(200)

    await expect(page.getByTestId('transfer-step-summary')).toBeVisible()
    await expect(page.getByTestId('transfer-summary-created')).toContainText('Przepisy: 1')

    // Kopia jest realna: widać ją na liście przepisów pod nazwą z sufiksem.
    await page.goto(`/przepisy?q=${encodeURIComponent(RECIPE_NAME)}`)
    await expect(page.getByText(COPY_NAME)).toBeVisible()
  } finally {
    try {
      if (context && authenticated) await cleanupOwnRecipes(context.request, user.id)
    } finally {
      try {
        const deleted = await admin.delete(`${API}/admin/users/${user.id}`, {
          headers: adminHeaders,
        })
        expect(deleted.status(), 'usunięcie wyłącznie własnego konta transferu').toBe(204)
      } finally {
        await context?.close()
      }
    }
  }
})
