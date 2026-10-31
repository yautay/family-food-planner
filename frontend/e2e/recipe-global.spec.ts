import { randomBytes } from 'node:crypto'
import { reserveLoginAttempt } from './login-budget.js'
import { fillSecretPassword } from './secret-password.js'

import { expect, test } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'

import { cleanupE2eData, csrfHeaders } from './cleanup.js'

test.use({ trace: 'off' })

/**
 * Core flow BATCH_21 (D32): przepis `global`.
 *
 * ADMIN (konto z `.env`) publikuje przepis „dla wszystkich" → zwykły użytkownik
 * z INNEJ rodziny go widzi, dodaje do swojego planu, kopiuje do swojej rodziny
 * i edytuje kopię, a oryginał zostaje nietknięty.
 *
 * Drugie konto E2E nie istnieje w repozytorium (07_SECURITY §2: żadnego hasła
 * w plikach śledzonych), więc spec zakłada je przez API ADMIN-a z hasłem
 * LOSOWYM, wygenerowanym w trakcie przebiegu — nigdzie nie zapisywanym ani nie
 * logowanym — i usuwa je razem z rodziną w `afterAll`. Loguje się raz (limit
 * `/auth/login` to 5/min/IP).
 *
 * Sprzątanie idzie od najbardziej zależnych encji: pozycje planu (FK RESTRICT
 * do przepisu) → przepisy (globalny i kopia) → konto → rodzina.
 */

const PREFIX = 'E2E przepis-global'
const ACCOUNT_PREFIX = 'e2e-global-'
/** Dzień w oknie zarezerwowanym dla E2E (lata 2030+, 08_TESTING §3.1). */
const DAY = '2034-04-10'
const API = '/api/v1'

interface Row {
  id: number
}

async function purge(request: APIRequestContext): Promise<void> {
  await cleanupE2eData(request, { namePrefix: PREFIX, dates: [DAY] })
  const headers = await csrfHeaders(request)

  const users = await request.get(`${API}/admin/users?q=${ACCOUNT_PREFIX}&limit=200&offset=0`)
  if (users.ok()) {
    const body = (await users.json()) as { items: (Row & { email: string })[] }
    for (const user of body.items.filter((item) => item.email.startsWith(ACCOUNT_PREFIX))) {
      await request.delete(`${API}/admin/users/${user.id}`, { headers })
    }
  }

  const households = await request.get(`${API}/admin/households?limit=200&offset=0`)
  if (households.ok()) {
    const body = (await households.json()) as { items: (Row & { name: string })[] }
    for (const household of body.items.filter((item) => item.name.startsWith(PREFIX))) {
      await request.delete(`${API}/admin/households/${household.id}`, { headers })
    }
  }
}

test.beforeAll(async ({ request }) => {
  await purge(request)
})

test.afterAll(async ({ request }) => {
  await purge(request)
})

test('ADMIN publikuje przepis, USER innej rodziny go widzi, planuje, kopiuje i edytuje kopię', async ({
  page,
  request,
  browser,
  baseURL,
}, testInfo) => {
  // Pełny flow dwóch sesji (publikacja, plan, kopia, edycja) nie mieści się w 30 s.
  test.setTimeout(90_000)

  const stamp = Date.now()
  const recipeName = `${PREFIX} Zupa ${stamp}`
  const copyName = `${PREFIX} Moja zupa ${stamp}`
  const email = `${ACCOUNT_PREFIX}${stamp}@example.com`
  const password = `${randomBytes(18).toString('base64url')}aA1`

  page.on('dialog', (dialog) => dialog.accept())

  // --- ADMIN: obca rodzina i konto użytkownika (przez API) ------------------------
  const headers = await csrfHeaders(request)
  const household = await request.post(`${API}/admin/households`, {
    headers,
    data: { name: `${PREFIX} rodzina ${stamp}` },
  })
  expect(household.status(), await household.text()).toBe(201)
  const householdId = ((await household.json()) as Row).id
  const account = await request.post(`${API}/admin/users`, {
    headers,
    data: { email, password, display_name: 'E2E Global', role: 'user' },
  })
  expect(account.status(), 'konto E2E musi się założyć').toBe(201)
  const members = await request.put(`${API}/admin/households/${householdId}/members`, {
    headers,
    data: { user_ids: [((await account.json()) as Row).id] },
  })
  expect(members.status()).toBe(200)

  // --- ADMIN: publikuje przepis „Wszyscy" w edytorze -----------------------------
  await page.goto('/przepisy/nowy')
  await expect(page.getByTestId('przepis-edytor-page')).toBeVisible()
  await page.getByTestId('recipe-name').fill(recipeName)
  await page.getByTestId('recipe-scope').selectOption('global')
  await expect(page.getByTestId('recipe-scope-hint')).toBeVisible()
  await page.getByTestId('recipe-submit').click()

  await expect(page.getByTestId('recipe-name')).toHaveText(recipeName)
  await expect(page.getByTestId('recipe-scope-badge')).toContainText('Dla wszystkich')
  await expect(page.getByTestId('recipe-edit')).toBeVisible()
  await expect(page.getByTestId('recipe-archive')).toBeVisible()
  const recipeId = Number(/\/przepisy\/(\d+)/.exec(page.url())?.[1])
  expect(recipeId).toBeGreaterThan(0)

  // --- USER innej rodziny: osobna sesja przeglądarki -----------------------------
  // `browser.newContext()` dziedziczy `storageState` projektu (sesja ADMIN-a), więc
  // BEZ jawnego zerowania przeglądarka USER-a byłaby zalogowana jako administrator.
  const context = await browser.newContext({
    baseURL,
    storageState: { cookies: [], origins: [] },
  })
  const userPage = await context.newPage()
  try {
    userPage.on('dialog', (dialog) => dialog.accept())
    await userPage.goto('/login')
    await userPage.getByTestId('login-email').fill(email)
    await fillSecretPassword(userPage.getByTestId('login-password'), password)
    await reserveLoginAttempt(baseURL, testInfo)
    await userPage.getByTestId('login-submit').click()
    await expect(userPage).toHaveURL(/\/plan-dnia/)

    // Widzi przepis na liście (filtr „Dla wszystkich") z odznaką zakresu.
    await userPage.goto(`/przepisy?selectedDate=${DAY}`)
    await userPage.getByTestId('recipes-filters-toggle').click()
    await userPage.getByTestId('recipes-scope-global').click()
    const card = userPage.getByTestId(`recipe-open-${recipeId}`)
    await expect(card).toBeVisible()
    await expect(userPage.getByTestId(`recipe-scope-badge-${recipeId}`)).toHaveText(
      'Dla wszystkich',
    )

    // Szczegół: żadnych akcji zarządzania, ale jest „Kopiuj do mojej rodziny".
    await card.click()
    await expect(userPage.getByTestId('recipe-name')).toHaveText(recipeName)
    await expect(userPage.getByTestId('recipe-edit')).toHaveCount(0)
    await expect(userPage.getByTestId('recipe-delete')).toHaveCount(0)
    await expect(userPage.getByTestId('recipe-archive')).toHaveCount(0)
    await expect(userPage.getByTestId('recipe-copy')).toBeVisible()

    // Szczegół planuje globalny przepis bez edycji i zachowuje datę katalogu.
    await userPage.getByTestId('recipe-plan').click()
    await expect(userPage.getByTestId('planning-date')).toHaveValue(DAY)
    await userPage.getByTestId('planning-meal-name').fill('Obiad E2E')
    const scheduled = userPage.waitForResponse(
      (response) =>
        response.url().includes(`/plan/days/${DAY}/recipe-items`) &&
        response.request().method() === 'POST',
    )
    await userPage.getByTestId('recipe-planning-submit').click()
    expect((await scheduled).status()).toBe(201)
    await expect(userPage).toHaveURL(new RegExp(`/plan-dnia/${DAY}`))
    await expect(userPage.locator('[data-testid^="plan-item-servings-"]').first()).toBeVisible()

    // Kopiuje do swojej rodziny i dostaje WŁASNY, edytowalny przepis.
    await userPage.goto(`/przepisy/${recipeId}`)
    await userPage.getByTestId('recipe-copy').click()
    await expect(userPage.getByTestId('recipe-scope-badge')).toContainText('Rodzinny')
    await expect(userPage.getByTestId('recipe-name')).toHaveText(recipeName)
    expect(Number(/\/przepisy\/(\d+)/.exec(userPage.url())?.[1])).not.toBe(recipeId)
    await expect(userPage.getByTestId('recipe-edit')).toBeVisible()
    await expect(userPage.getByTestId('recipe-delete')).toBeVisible()

    await userPage.getByTestId('recipe-edit').click()
    // `recipe-name` to testid i nagłówka szczegółu, i pola edytora — czekamy na edytor.
    await expect(userPage.getByTestId('przepis-edytor-page')).toBeVisible()
    await userPage.getByTestId('recipe-name').fill(copyName)
    await userPage.getByTestId('recipe-submit').click()
    await expect(userPage.getByTestId('recipe-name')).toHaveText(copyName)
  } finally {
    await context.close()
  }

  // --- ADMIN: oryginał nietknięty edycją kopii -------------------------------------
  await page.goto(`/przepisy/${recipeId}`)
  await expect(page.getByTestId('recipe-name')).toHaveText(recipeName)
  await expect(page.getByTestId('recipe-scope-badge')).toContainText('Dla wszystkich')
})
