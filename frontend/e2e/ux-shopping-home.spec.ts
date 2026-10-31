import { randomBytes } from 'node:crypto'
import { reserveLoginAttempt } from './login-budget.js'

import {
  expect,
  test,
  type APIRequestContext,
  type APIResponse,
  type BrowserContext,
  type Page,
} from '@playwright/test'

import type { components } from '../src/api/generated.js'
import { csrfHeaders } from './cleanup.js'
import { EMPTY_STATE } from './auth-state.js'

type ListSummary = components['schemas']['ShoppingListSummaryRead']
type Lists = components['schemas']['ShoppingListsResponse']
type Day = components['schemas']['DayRead']
type Rounds = components['schemas']['RoundConfigListResponse']
type Round = components['schemas']['RoundConfigRead']
type Generation = components['schemas']['GenerationRead']
type Finalized = components['schemas']['FinalizeResponse']
type Products = components['schemas']['ProductListResponse']
type Product = components['schemas']['ProductDetail']
type Categories = components['schemas']['CategoryListResponse']
type User = components['schemas']['UserRead']
type Users = components['schemas']['UserListResponse']
type CurrentUser = components['schemas']['CurrentUser']

const API = '/api/v1'
const PREFIX = 'E2E UX05'
const ACTOR_EMAIL = 'e2e-ux05-shopping-home@example.com'
const ACTOR_NAME = 'E2E UX05 shopping-home actor'
const PRODUCT_NAME = `${PREFIX} produkt katalogu`
const FROM = '2038-11-01'
const TO = '2038-11-07'
const PAGE_SIZE = 50
const knownListIds = new Set<number>()
let headers: Record<string, string>
let ownRounds: Round[] = []
let actorId: number | null = null
let actorContext: BrowserContext | undefined
let actorAuthenticated = false

// Ten aktor jest celowo trwały: historia generacji/plan_days ma owner FK RESTRICT.
// Każdy przebieg ustawia losowe hasło tylko w pamięci, potem dezaktywuje konto.
// Dokładny email + marker nazwy + rola chronią przed przejęciem obcego konta.
async function prepareActor(admin: APIRequestContext): Promise<string> {
  const adminHeaders = await csrfHeaders(admin)
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
  if (existing) {
    expect(
      existing.display_name,
      'Istniejące konto musi mieć dokładny marker własności UX05.',
    ).toBe(ACTOR_NAME)
    expect(existing.role, 'Spec nie zmienia roli istniejącego konta.').toBe('user')
    actorId = existing.id
    await body<User>(
      await admin.patch(`${API}/admin/users/${actorId}`, {
        headers: adminHeaders,
        data: { is_active: true, password },
      }),
    )
  } else {
    const created = await body<User>(
      await admin.post(`${API}/admin/users`, {
        headers: adminHeaders,
        data: {
          email: ACTOR_EMAIL,
          display_name: ACTOR_NAME,
          role: 'user',
          is_active: true,
          password,
        },
      }),
    )
    actorId = created.id
  }
  return password
}

async function cleanupProduct(admin: APIRequestContext): Promise<void> {
  const adminHeaders = await csrfHeaders(admin)
  const own: number[] = []
  for (let offset = 0; ; offset += 200) {
    const products = await body<Products>(
      await admin.get(`${API}/products`, {
        params: { q: PRODUCT_NAME, include_archived: true, limit: 200, offset },
      }),
    )
    own.push(
      ...products.items
        .filter((product) => product.name === PRODUCT_NAME)
        .map((product) => product.id),
    )
    if (products.items.length === 0 || offset + products.items.length >= products.total) break
  }
  for (const id of own) {
    const response = await admin.delete(`${API}/products/${id}`, { headers: adminHeaders })
    expect(
      response.ok() || response.status() === 404,
      'Usuwamy wyłącznie własny produkt po własnych listach i posiłkach.',
    ).toBe(true)
  }
}

async function body<T>(response: APIResponse): Promise<T> {
  expect(response.ok(), `${response.url()} → ${response.status()} ${await response.text()}`).toBe(
    true,
  )
  return response.json() as Promise<T>
}
async function allLists(request: APIRequestContext): Promise<ListSummary[]> {
  const rows: ListSummary[] = []
  for (let offset = 0; ; offset += 200) {
    const page = await body<Lists>(
      await request.get(`${API}/shopping/lists?limit=200&offset=${offset}`),
    )
    rows.push(...page.items)
    if (page.items.length === 0 || rows.length >= page.total) return rows
  }
}
async function cleanupOwn(request: APIRequestContext): Promise<void> {
  headers = await csrfHeaders(request)
  // Najpierw zbieramy wszystkie strony, dopiero później usuwamy: offset nie przesuwa się pod nami.
  const lists = (await allLists(request)).filter(
    (list) =>
      knownListIds.has(list.id) ||
      list.name.startsWith(PREFIX) ||
      list.round_name?.startsWith(PREFIX),
  )
  for (const list of lists) {
    const response = await request.delete(`${API}/shopping/lists/${list.id}`, { headers })
    expect(response.ok() || response.status() === 404).toBe(true)
  }
  knownListIds.clear()
  for (const date of [FROM, TO]) {
    const day = await body<Day>(await request.get(`${API}/plan/days/${date}`))
    for (const meal of day.meals.filter((meal) => meal.name.startsWith(PREFIX))) {
      await body<Day>(await request.delete(`${API}/plan/meals/${meal.id}`, { headers }))
    }
  }
  const rounds = await body<Rounds>(await request.get(`${API}/shopping/round-configs`))
  for (const round of rounds.items.filter((round) => round.name.startsWith(PREFIX))) {
    const response = await request.delete(`${API}/shopping/round-configs/${round.id}`, { headers })
    expect(response.ok() || response.status() === 404).toBe(true)
  }
}
async function markLists(request: APIRequestContext, lists: Finalized): Promise<void> {
  for (const list of lists.items) {
    knownListIds.add(list.id)
    // round_name już nosi prefix, więc przerwany PATCH też jest sprzątany przy następnym starcie.
    await body(
      await request.patch(`${API}/shopping/lists/${list.id}`, {
        headers,
        data: { name: `${PREFIX} lista ${list.id}` },
      }),
    )
  }
}
async function chooseRounds(page: Page, selected: number[]): Promise<void> {
  const details = page.getByTestId('zakupy-round-settings')
  await details.locator('summary').click()
  await page.getByTestId('round-selection-all').uncheck()
  for (const checkbox of await details.locator('[data-testid^="round-selection-"]').all()) {
    if ((await checkbox.getAttribute('data-testid')) === 'round-selection-all') continue
    const id = Number((await checkbox.getAttribute('data-testid'))?.replace('round-selection-', ''))
    await checkbox.setChecked(selected.includes(id))
  }
  await details.locator('summary').click()
}
async function finalizeInUi(
  page: Page,
  request: APIRequestContext,
  count: number,
): Promise<Finalized> {
  await page.getByTestId('zakupy-generate').click()
  await expect(page.getByTestId('zakupy-preview')).toBeVisible()
  await expect(page.getByTestId('preview-title')).toBeFocused()
  await expect(page.getByTestId('preview-finalize')).toBeEnabled()
  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      /\/generations\/\d+\/finalize$/.test(new URL(response.url()).pathname),
  )
  await page.getByTestId('preview-finalize').click()
  const response = await responsePromise
  expect(response.ok()).toBe(true)
  const lists = (await response.json()) as Finalized
  expect(lists.items).toHaveLength(count)
  lists.items.forEach((list) => knownListIds.add(list.id))
  await expect(page.getByTestId('zakupy-created-lists')).toBeVisible()
  await expect(page.getByTestId('zakupy-created-lists')).toBeFocused()
  await expect(
    page.getByTestId('zakupy-created-lists').locator('[data-testid^="created-list-link-"]'),
  ).toHaveCount(count)
  for (const list of lists.items)
    await expect(page.getByTestId(`created-list-link-${list.id}`)).toBeVisible()
  await markLists(request, lists)
  return lists
}

test.beforeAll(async ({ request: admin, browser, baseURL }, testInfo) => {
  test.setTimeout(180_000)
  const password = await prepareActor(admin)
  actorContext = await browser.newContext({ baseURL, storageState: EMPTY_STATE })
  const request = actorContext.request
  await reserveLoginAttempt(baseURL, testInfo, 180_000)
  const logged = await body<CurrentUser>(
    await request.post(`${API}/auth/login`, {
      data: { email: ACTOR_EMAIL, password },
    }),
  )
  expect(logged.id).toBe(actorId)
  expect(logged.role).toBe('user')
  expect(logged.household).toBeNull()
  expect((await request.get(`${API}/admin/users`)).status()).toBe(403)
  actorAuthenticated = true
  await cleanupOwn(request)
  await cleanupProduct(admin)
  ownRounds = []
  for (const [index, covers] of [4, 3].entries()) {
    ownRounds.push(
      await body<Round>(
        await request.post(`${API}/shopping/round-configs`, {
          headers,
          data: {
            name: `${PREFIX} tura ${index + 1}`,
            mode: 'all',
            covers_days: covers,
            fresh_days: null,
            shopping_weekday: null,
          },
        }),
      ),
    )
  }
  const categories = await body<Categories>(await request.get(`${API}/categories`))
  expect(
    categories.items.length,
    'Słownik kategorii pochodzi z migracji aplikacji, nie fixture UX00.',
  ).toBeGreaterThan(0)
  const fresh = await body<Product>(
    await request.post(`${API}/products`, {
      headers,
      data: {
        name: PRODUCT_NAME,
        category_id: categories.items[0]!.id,
        measure_kind: 'mass',
        perishability_override: 'fresh',
      },
    }),
  )
  for (const date of [FROM, TO]) {
    const day = await body<Day>(
      await request.post(`${API}/plan/days/${date}/meals`, {
        headers,
        data: { name: `${PREFIX} posiłek ${date}` },
      }),
    )
    const meal = day.meals.find((meal) => meal.name === `${PREFIX} posiłek ${date}`)
    expect(meal).toBeDefined()
    await body<Day>(
      await request.post(`${API}/plan/meals/${meal!.id}/items`, {
        headers,
        data: { product_id: fresh.id, quantity: '400', unit: 'g' },
      }),
    )
  }
  // Prawdziwe 50 list, każda para z NOWEJ generacji. Żadnego mocka indeksu ani finalize.
  for (let index = 0; index < 25; index++) {
    const generation = await body<Generation>(
      await request.post(`${API}/shopping/generate`, {
        headers,
        data: {
          date_from: FROM,
          date_to: TO,
          use_pantry: false,
          round_config_ids: ownRounds.map((round) => round.id),
        },
      }),
    )
    expect(generation.has_blockers).toBe(false)
    const lists = await body<Finalized>(
      await request.post(`${API}/shopping/generations/${generation.id}/finalize`, { headers }),
    )
    expect(lists.items).toHaveLength(2)
    lists.items.forEach((list) => knownListIds.add(list.id))
    await markLists(request, lists)
  }
})
test.afterAll(async ({ request: admin }) => {
  test.setTimeout(90_000)
  try {
    if (actorContext && actorAuthenticated) {
      await cleanupOwn(actorContext.request)
      await cleanupProduct(admin)
    }
  } finally {
    try {
      if (actorId !== null) {
        const deactivated = await body<User>(
          await admin.patch(`${API}/admin/users/${actorId}`, {
            headers: await csrfHeaders(admin),
            data: { is_active: false },
          }),
        )
        expect(deactivated.is_active).toBe(false)
      }
    } finally {
      await actorContext?.close()
    }
  }
})

test('trwały katalog: jedna i dwie tury, reload, wszystkie rzeczywiste strony i klawiatura', async () => {
  test.setTimeout(180_000)
  const request = actorContext!.request
  const page = await actorContext!.newPage()
  const initial = (await allLists(request)).filter((list) => list.round_name?.startsWith(PREFIX))
  expect(initial).toHaveLength(50)
  const oldestOwnId = initial.at(-1)!.id
  await page.goto(`/zakupy?from=${FROM}&to=${TO}&selectedDate=2038-11-03`)
  await expect(page.getByTestId('shopping-catalog-list')).toBeVisible()
  await expect(page.getByTestId('zakupy-date-from')).toHaveValue(FROM)
  await expect(page.getByTestId('zakupy-date-to')).toHaveValue(TO)
  await expect(page.getByTestId('zakupy-use-pantry')).not.toBeChecked()

  await chooseRounds(page, [ownRounds[0]!.id])
  const single = await finalizeInUi(page, request, 1)
  await page.reload()
  await expect(page.getByTestId(`shopping-list-${single.items[0]!.id}`)).toContainText(PREFIX)

  // Jawny przycisk kieruje klawiaturę do generatora; Enter rozwija konfigurację.
  await page.getByTestId('zakupy-new-list').focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('#generator-title')).toBeFocused()
  const summary = page.getByTestId('zakupy-round-settings').locator('summary')
  await summary.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByTestId('round-selection-all')).toBeVisible()
  await page.keyboard.press('Enter')
  await chooseRounds(
    page,
    ownRounds.map((round) => round.id),
  )
  const multiple = await finalizeInUi(page, request, 2)
  await page.reload()
  for (const list of multiple.items)
    await expect(page.getByTestId(`shopping-list-${list.id}`)).toContainText(PREFIX)
  const serverLists = await allLists(request)
  expect(serverLists.filter((list) => list.round_name?.startsWith(PREFIX))).toHaveLength(53)
  await expect(page.getByTestId('shopping-catalog-count')).toHaveText(
    `${PAGE_SIZE} z ${serverLists.length}`,
  )
  await expect(page.getByTestId(`shopping-list-${oldestOwnId}`)).toHaveCount(0)
  for (let loaded = PAGE_SIZE; loaded < serverLists.length; loaded += PAGE_SIZE) {
    await page.getByTestId('shopping-catalog-more').click()
    await expect(page.getByTestId('shopping-catalog-count')).toHaveText(
      `${Math.min(loaded + PAGE_SIZE, serverLists.length)} z ${serverLists.length}`,
    )
  }
  await expect(page.getByTestId(`shopping-list-${oldestOwnId}`)).toBeVisible()
  await expect(page.getByTestId('shopping-catalog-more')).toHaveCount(0)
  await page.getByTestId(`shopping-list-link-${oldestOwnId}`).click()
  await expect(page).toHaveURL(new RegExp(`/zakupy/listy/${oldestOwnId}$`))
  await page.goto('/zakupy')
  await expect(page.getByTestId(`shopping-list-${multiple.items[0]!.id}`)).toBeVisible()
})
