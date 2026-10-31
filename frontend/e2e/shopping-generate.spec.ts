import { randomBytes } from 'node:crypto'

import {
  expect,
  test,
  type APIRequestContext,
  type APIResponse,
  type BrowserContext,
} from '@playwright/test'

import type { components } from '../src/api/generated.js'
import { EMPTY_STATE } from './auth-state.js'
import { csrfHeaders } from './cleanup.js'
import { reserveLoginAttempt } from './login-budget.js'

type User = components['schemas']['UserRead']
type Users = components['schemas']['UserListResponse']
type CurrentUser = components['schemas']['CurrentUser']
type Rounds = components['schemas']['RoundConfigListResponse']
type Round = components['schemas']['RoundConfigRead']
type RoundInput = components['schemas']['RoundConfigCreateRequest']
type Day = components['schemas']['DayRead']
type Lists = components['schemas']['ShoppingListsResponse']
type ListSummary = components['schemas']['ShoppingListSummaryRead']
type Generation = components['schemas']['GenerationRead']
type Finalized = components['schemas']['FinalizeResponse']

/**
 * Core flow 3 (08_TESTING §3.2): zakupy od planu do list.
 *
 * Ścieżka: plan dnia (dwie pozycje z produktów seedu) → `/zakupy` → jawne
 * zaznaczenie „Uwzględnić stan domowy?" → podgląd z opakowaniami i resztkami →
 * toggle „mam już w domu" → finalizacja → listy utworzone per tura.
 *
 * Produkty globalnego seedu demo (`task db-seed-demo`, 08_TESTING §5) mają
 * warianty sklepowe i opakowania. Spec tylko je czyta.
 *
 * Własny USER bez rodziny izoluje plan i dokładnie dwa presety od historii
 * współdzielonego ADMIN-a. Konto jest trwałe (historia generacji ma FK RESTRICT),
 * jak w UX05, ale z osobnym markerem i emailem. Hasło losujemy tylko w pamięci,
 * a finally dezaktywuje konto także po błędzie. Daty są w oknie E2E (2030+).
 */

/** Poniedziałek–niedziela w oknie E2E (2033-03-07 to poniedziałek). */
const WEEK_START = '2033-03-07'
const WEEK_END = '2033-03-13'
const TOUCHED_DATES = Array.from(
  { length: 7 },
  (_, offset) => `2033-03-${String(offset + 7).padStart(2, '0')}`,
)

const API = '/api/v1'
const PREFIX = 'E2E zakupy generator'
const ACTOR_EMAIL = 'e2e-shopping-generate@example.com'
const ACTOR_NAME = `${PREFIX} actor`
const MEAL_NAME = `Obiad ${PREFIX}`
const LIST_NAME = 'Zakupy 07.03-13.03.2033'
const PRESETS: RoundInput[] = [
  {
    name: 'Niedziela',
    mode: 'durable_plus_fresh_window',
    covers_days: 7,
    fresh_days: 4,
    shopping_weekday: 6,
    position: 0,
  },
  {
    name: 'Środa',
    mode: 'fresh_only',
    covers_days: 3,
    fresh_days: null,
    shopping_weekday: 2,
    position: 1,
  },
]
const ROUND_NAMES = PRESETS.map((preset) => `${PREFIX} ${preset.name}`)

async function body<T>(response: APIResponse): Promise<T> {
  // Bez treści odpowiedzi: również błędy auth nie mogą drukować danych sesji.
  expect(response.ok(), `${new URL(response.url()).pathname} → ${response.status()}`).toBe(true)
  return response.json() as Promise<T>
}

async function prepareActor(admin: APIRequestContext): Promise<{ user: User; password: string }> {
  let existing: User | undefined
  for (let offset = 0; ; offset += 200) {
    const users = await body<Users>(
      await admin.get(`${API}/admin/users`, {
        params: { q: ACTOR_EMAIL, limit: 200, offset },
      }),
    )
    existing = users.items.find((user) => user.email === ACTOR_EMAIL)
    if (existing || users.items.length === 0 || offset + users.items.length >= users.total) break
  }
  const password = `${randomBytes(24).toString('base64url')}aA1`
  const headers = await csrfHeaders(admin)
  if (existing) {
    expect(existing.display_name, 'Dokładny marker własności konta generatora.').toBe(ACTOR_NAME)
    expect(existing.role, 'Nigdy nie przejmujemy ani nie zmieniamy roli obcego konta.').toBe('user')
    const user = await body<User>(
      await admin.patch(`${API}/admin/users/${existing.id}`, {
        headers,
        data: { is_active: true, password },
      }),
    )
    return { user, password }
  }
  const user = await body<User>(
    await admin.post(`${API}/admin/users`, {
      headers,
      data: { email: ACTOR_EMAIL, display_name: ACTOR_NAME, role: 'user', password },
    }),
  )
  return { user, password }
}

async function allLists(request: APIRequestContext): Promise<ListSummary[]> {
  const rows: ListSummary[] = []
  for (let offset = 0; ; offset += 200) {
    const page = await body<Lists>(
      await request.get(`${API}/shopping/lists`, { params: { limit: 200, offset } }),
    )
    rows.push(...page.items)
    if (page.items.length === 0 || rows.length >= page.total) return rows
  }
}

async function cleanupOwn(
  request: APIRequestContext,
  userId: number,
  knownListIds: Set<number>,
  removeRounds: boolean,
): Promise<void> {
  const headers = await csrfHeaders(request)
  // Zbieramy wszystkie strony przed usuwaniem; tylko exact marker + daty lub znane IDs.
  const lists = (await allLists(request)).filter(
    (list) =>
      knownListIds.has(list.id) ||
      (list.name === LIST_NAME && ROUND_NAMES.includes(list.round_name ?? '')),
  )
  for (const list of lists) {
    const deleted = await request.delete(`${API}/shopping/lists/${list.id}`, { headers })
    expect(deleted.status()).toBe(204)
  }
  for (const date of TOUCHED_DATES) {
    const day = await body<Day>(await request.get(`${API}/plan/days/${date}`))
    for (const meal of day.meals.filter((meal) => meal.name === MEAL_NAME)) {
      await body<Day>(await request.delete(`${API}/plan/meals/${meal.id}`, { headers }))
    }
  }
  if (removeRounds) {
    const rounds = await body<Rounds>(await request.get(`${API}/shopping/round-configs`))
    for (const round of rounds.items.filter((round) => ROUND_NAMES.includes(round.name))) {
      expect(round.owner_user_id).toBe(userId)
      expect(round.household_id).toBeNull()
      const deleted = await request.delete(`${API}/shopping/round-configs/${round.id}`, { headers })
      expect(deleted.status()).toBe(204)
    }
  }
}

async function prepareRounds(request: APIRequestContext, userId: number): Promise<void> {
  const headers = await csrfHeaders(request)
  const rounds = await body<Rounds>(await request.get(`${API}/shopping/round-configs`))
  expect(rounds.items.length).toBeLessThanOrEqual(2)
  for (const round of rounds.items) {
    expect(round.owner_user_id).toBe(userId)
    expect(round.household_id).toBeNull()
    expect(round.scope).toBe('private')
    expect([...ROUND_NAMES, ...PRESETS.map((preset) => preset.name)]).toContain(round.name)
  }
  for (const [index, preset] of PRESETS.entries()) {
    const matches = rounds.items.filter(
      (round) => round.name === preset.name || round.name === ROUND_NAMES[index],
    )
    expect(matches.length).toBeLessThanOrEqual(1)
    const existing = matches[0]
    const data = { ...preset, name: ROUND_NAMES[index]! }
    if (existing) {
      expect(existing).toMatchObject({ ...preset, name: existing.name })
      await body<Round>(
        await request.patch(`${API}/shopping/round-configs/${existing.id}`, { headers, data }),
      )
    } else {
      // Odtworzenie tylko brakującego własnego presetu po przerwanym finally.
      await body<Round>(await request.post(`${API}/shopping/round-configs`, { headers, data }))
    }
  }
  const own = await body<Rounds>(await request.get(`${API}/shopping/round-configs`))
  expect(own.total).toBe(2)
  expect(own.items.map((round) => round.name)).toEqual(ROUND_NAMES)
}

/**
 * Produkty z seedu demo: pierwszy TRWAŁY (ma opakowania 1 kg i 2 kg — widać
 * wybór wariantu i resztkę), drugi ŚWIEŻY (trafia do obu tur, bo okno świeżych
 * presetu ma 4 dni z 7).
 */
const DURABLE_PRODUCT = 'Mąka pszenna typ 500'
const FRESH_PRODUCT = 'Pomidor'

test('zakupy: plan → podgląd ze spiżarnią → „mam w domu" → listy per tura', async ({
  browser,
  request: admin,
  baseURL,
}, testInfo) => {
  const { user, password } = await prepareActor(admin)
  let context: BrowserContext | undefined
  let authenticated = false
  const knownListIds = new Set<number>()
  try {
    context = await browser.newContext({ baseURL, storageState: EMPTY_STATE })
    const request = context.request
    await reserveLoginAttempt(baseURL, testInfo)
    const login = await request.post(`${API}/auth/login`, {
      data: { email: ACTOR_EMAIL, password },
    })
    expect(login.status()).toBe(200)
    const current = await body<CurrentUser>(await request.get(`${API}/auth/me`))
    expect(current.id).toBe(user.id)
    expect(current.email).toBe(ACTOR_EMAIL)
    expect(current.role).toBe('user')
    expect(current.household).toBeNull()
    expect((await request.get(`${API}/admin/users`)).status()).toBe(403)
    authenticated = true
    await cleanupOwn(request, user.id, knownListIds, false)
    await prepareRounds(request, user.id)
    const page = await context.newPage()
    page.on('dialog', (dialog) => dialog.accept())

    const productIds = new Map<string, number>()
    // --- plan: dwie pozycje z produktów seedu w dwóch różnych dniach -------------------
    for (const [index, day] of [WEEK_START, WEEK_END].entries()) {
      await page.goto(`/plan-dnia/${day}`)
      await expect(page.getByTestId('plan-dnia-page')).toBeVisible()

      await page.getByTestId('plan-add-meal').click()
      await page.getByTestId('meal-name-input').fill(MEAL_NAME)
      await page.getByTestId('meal-submit').click()

      for (const product of [DURABLE_PRODUCT, FRESH_PRODUCT]) {
        const addProduct = page.locator('[data-testid^="meal-add-product-"]').first()
        if (!(await addProduct.isVisible()))
          await page.locator('[data-testid^="meal-menu-"]').first().click()
        await addProduct.click()
        await page.getByTestId('picker-input').fill(product)
        const option = page.locator('[data-testid^="picker-option-"]').first()
        const productId = Number(
          (await option.getAttribute('data-testid'))?.replace('picker-option-', ''),
        )
        expect(Number.isSafeInteger(productId) && productId > 0).toBe(true)
        productIds.set(product, productId)
        await option.click()
        await expect(page.getByTestId('picker-selected')).toContainText(product)
        await page.getByTestId('item-amount').fill(index === 0 ? '400' : '300')
        await page.getByTestId('item-submit').click()
        await expect(page.locator('[data-testid^="plan-item-servings-"]').first()).toBeVisible()
      }
    }

    // --- zakupy: tury z presetu + jawna zgoda na spiżarnię -----------------------------
    await page.goto('/zakupy')
    await expect(page.getByTestId('zakupy-page')).toBeVisible()
    // Własne presety niedziela/środa z pierwszego GET (02_DOMAIN §9.2).
    await expect(page.getByTestId('round-configs-list')).toContainText('Niedziela')
    await expect(page.getByTestId('round-configs-list')).toContainText('Środa')

    const pantryCheckbox = page.getByTestId('zakupy-use-pantry')
    // Kluczowa asercja karty B10: checkbox jest ODZNACZONY, dopóki człowiek go
    // nie zaznaczy (02_DOMAIN §8).
    await expect(pantryCheckbox).not.toBeChecked()
    await page.getByTestId('zakupy-date-from').fill(WEEK_START)
    await page.getByTestId('zakupy-date-to').fill(WEEK_END)
    await pantryCheckbox.check()

    const generationResponse = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        new URL(response.url()).pathname === `${API}/shopping/generate`,
    )
    await page.getByTestId('zakupy-generate').click()
    const generated = await generationResponse
    expect(generated.status()).toBe(201)
    const generation = (await generated.json()) as Generation
    expect(generation).toMatchObject({
      date_from: WEEK_START,
      date_to: WEEK_END,
      use_pantry: true,
      status: 'preview',
      owner_user_id: user.id,
      household_id: null,
      has_blockers: false,
    })
    expect(generation.rounds.map((round) => round.name)).toEqual(ROUND_NAMES)
    const lines = generation.rounds.flatMap((round) => round.items)
    // Etykieta może być nazwą wariantu sklepowego; tożsamość produktu jest w ID.
    expect(lines.some((line) => line.product_id === productIds.get(DURABLE_PRODUCT))).toBe(true)
    expect(lines.some((line) => line.product_id === productIds.get(FRESH_PRODUCT))).toBe(true)
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
    const resolveResponse = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        new URL(response.url()).pathname === `${API}/shopping/generations/${generation.id}/resolve`,
    )
    await firstToggle.check()
    const resolved = await resolveResponse
    expect(resolved.status()).toBe(200)
    const updated = (await resolved.json()) as Generation
    const selectedLines = updated.rounds
      .flatMap((round) => round.items)
      .filter((line) => line.product_id === Number(productId))
    expect(selectedLines.length).toBeGreaterThan(0)
    expect(selectedLines.every((line) => line.already_have)).toBe(true)
    // `already_have` jest decyzją o PRODUKCIE, więc produkt świeży oznacza się
    // w obu turach naraz — dlatego `first()`, a nie pojedynczy element.
    await expect(page.getByTestId(`preview-already-have-${productId}`).first()).toBeVisible()

    // --- finalizacja: listy per tura --------------------------------------------------
    const finalize = page.getByTestId('preview-finalize')
    await expect(finalize).toBeEnabled()
    const finalizeResponse = page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        new URL(response.url()).pathname ===
          `${API}/shopping/generations/${generation.id}/finalize`,
    )
    await finalize.click()
    const finalized = await finalizeResponse
    expect(finalized.status()).toBe(201)
    const lists = (await finalized.json()) as Finalized
    lists.items.forEach((list) => knownListIds.add(list.id))
    expect(lists.items).toHaveLength(2)
    expect(lists.items.map((list) => list.round_name)).toEqual(ROUND_NAMES)

    const created = page.getByTestId('zakupy-created-lists')
    await expect(created).toBeVisible()
    await expect(created).toContainText('Niedziela')
    await expect(created.locator('[data-testid^="created-list-"]').first()).toBeVisible()
  } finally {
    try {
      if (context && authenticated) await cleanupOwn(context.request, user.id, knownListIds, true)
    } finally {
      try {
        const deactivated = await body<User>(
          await admin.patch(`${API}/admin/users/${user.id}`, {
            headers: await csrfHeaders(admin),
            data: { is_active: false },
          }),
        )
        expect(deactivated.is_active).toBe(false)
      } finally {
        await context?.close()
      }
    }
  }
})
