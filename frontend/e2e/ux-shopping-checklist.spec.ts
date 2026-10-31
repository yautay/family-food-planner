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

type Schema<K extends keyof components['schemas']> = components['schemas'][K]
const API = '/api/v1'
const PREFIX = 'E2E UX06'
const EMAIL = 'e2e-ux06-checklist@example.com'
const ACTOR = 'E2E UX06 checklist actor'
const DATE = '2039-03-07'
const LONG_NAME = `${PREFIX} Płatki owsiane pełnoziarniste z otrębami, pestkami dyni i suszoną żurawiną`
let actorId: number | undefined
let actor: BrowserContext | undefined
let authenticated = false
let headers: Record<string, string>
let listId: number
let productId: number
let itemId: number
let homeId: number
let receivedId: number

async function body<T>(response: APIResponse): Promise<T> {
  expect(response.ok(), `HTTP ${response.status()} ${await response.text()}`).toBe(true)
  return response.json() as Promise<T>
}

async function cleanupOwn(request: APIRequestContext, admin: APIRequestContext): Promise<void> {
  headers = await csrfHeaders(request)
  const ownLists: Schema<'ShoppingListSummaryRead'>[] = []
  for (let offset = 0; ; offset += 200) {
    const result = await body<Schema<'ShoppingListsResponse'>>(
      await request.get(`${API}/shopping/lists`, { params: { limit: 200, offset } }),
    )
    ownLists.push(...result.items.filter((list) => list.round_name?.startsWith(PREFIX)))
    if (offset + result.items.length >= result.total) break
  }
  for (const list of ownLists)
    expect((await request.delete(`${API}/shopping/lists/${list.id}`, { headers })).status()).toBe(
      204,
    )
  const day = await body<Schema<'DayRead'>>(await request.get(`${API}/plan/days/${DATE}`))
  for (const meal of day.meals.filter((meal) => meal.name.startsWith(PREFIX))) {
    await body(await request.delete(`${API}/plan/meals/${meal.id}`, { headers }))
  }
  const pantry = await body<Schema<'PantryListResponse'>>(
    await request.get(`${API}/pantry`, { params: { q: PREFIX, limit: 200, offset: 0 } }),
  )
  for (const item of pantry.items.filter((item) => item.product_name?.startsWith(PREFIX))) {
    expect((await request.delete(`${API}/pantry/${item.id}`, { headers })).status()).toBe(204)
  }
  const rounds = await body<Schema<'RoundConfigListResponse'>>(
    await request.get(`${API}/shopping/round-configs`),
  )
  for (const round of rounds.items.filter((round) => round.name.startsWith(PREFIX))) {
    expect(
      (await request.delete(`${API}/shopping/round-configs/${round.id}`, { headers })).status(),
    ).toBe(204)
  }
  const adminHeaders = await csrfHeaders(admin)
  const retail = await body<Schema<'RetailProductListResponse'>>(
    await admin.get(`${API}/retail-products`, {
      params: { q: PREFIX, include_archived: true, limit: 200, offset: 0 },
    }),
  )
  for (const row of retail.items.filter((row) => row.name.startsWith(PREFIX))) {
    expect(
      (await admin.delete(`${API}/retail-products/${row.id}`, { headers: adminHeaders })).status(),
    ).toBe(204)
  }
  const products = await body<Schema<'ProductListResponse'>>(
    await admin.get(`${API}/products`, {
      params: { q: PREFIX, include_archived: true, limit: 200, offset: 0 },
    }),
  )
  for (const row of products.items.filter((row) => row.name.startsWith(PREFIX))) {
    expect(
      (await admin.delete(`${API}/products/${row.id}`, { headers: adminHeaders })).status(),
    ).toBe(204)
  }
}

test.beforeAll(async ({ request: admin, browser, baseURL }, testInfo) => {
  test.setTimeout(120_000)
  const adminHeaders = await csrfHeaders(admin)
  const users = await body<Schema<'UserListResponse'>>(
    await admin.get(`${API}/admin/users`, { params: { q: EMAIL, limit: 200, offset: 0 } }),
  )
  const existing = users.items.find((user) => user.email === EMAIL)
  const password = `${randomBytes(24).toString('base64url')}aA1`
  if (existing) {
    expect(existing.display_name).toBe(ACTOR)
    expect(existing.role).toBe('user')
    actorId = existing.id
    await body(
      await admin.patch(`${API}/admin/users/${actorId}`, {
        headers: adminHeaders,
        data: { password, is_active: true },
      }),
    )
  } else {
    const user = await body<Schema<'UserRead'>>(
      await admin.post(`${API}/admin/users`, {
        headers: adminHeaders,
        data: { email: EMAIL, display_name: ACTOR, role: 'user', password },
      }),
    )
    actorId = user.id
  }
  // Trwały własny aktor: historia generacji ma FK RESTRICT. Nigdy nie
  // eksportujemy, nie importujemy i nie sprzątamy historii wspólnego ADMIN-a.
  actor = await browser.newContext({ baseURL, storageState: EMPTY_STATE })
  const request = actor.request
  await reserveLoginAttempt(baseURL, testInfo, 120_000)
  const current = await body<Schema<'CurrentUser'>>(
    await request.post(`${API}/auth/login`, { data: { email: EMAIL, password } }),
  )
  expect(current.id).toBe(actorId)
  expect(current.role).toBe('user')
  expect(current.household).toBeNull()
  authenticated = true
  await cleanupOwn(request, admin)
  const categories = await body<Schema<'CategoryListResponse'>>(
    await request.get(`${API}/categories`),
  )
  expect(categories.items.length).toBeGreaterThan(0)
  const products: Schema<'ProductDetail'>[] = []
  for (const name of [LONG_NAME, `${PREFIX} Mam już w domu`, `${PREFIX} Wcześniej przyjęte`]) {
    products.push(
      await body<Schema<'ProductDetail'>>(
        await request.post(`${API}/products`, {
          headers,
          data: {
            name,
            category_id: categories.items[0]!.id,
            measure_kind: 'mass',
            perishability_override: 'durable',
          },
        }),
      ),
    )
  }
  productId = products[0]!.id
  await body(
    await request.post(`${API}/retail-products`, {
      headers,
      data: {
        canonical_product_id: productId,
        name: LONG_NAME,
        package_amount: '1000',
        package_unit: 'g',
      },
    }),
  )
  const round = await body<Schema<'RoundConfigRead'>>(
    await request.post(`${API}/shopping/round-configs`, {
      headers,
      data: { name: `${PREFIX} tura`, mode: 'all', covers_days: 7 },
    }),
  )
  const day = await body<Schema<'DayRead'>>(
    await request.post(`${API}/plan/days/${DATE}/meals`, {
      headers,
      data: { name: `${PREFIX} posiłek` },
    }),
  )
  const meal = day.meals.find((meal) => meal.name === `${PREFIX} posiłek`)!
  for (const product of products) {
    await body(
      await request.post(`${API}/plan/meals/${meal.id}/items`, {
        headers,
        data: { product_id: product.id, quantity: '1400', unit: 'g' },
      }),
    )
  }
  const generation = await body<Schema<'GenerationRead'>>(
    await request.post(`${API}/shopping/generate`, {
      headers,
      data: { date_from: DATE, date_to: DATE, use_pantry: false, round_config_ids: [round.id] },
    }),
  )
  expect(generation.has_blockers).toBe(false)
  const finalized = await body<Schema<'FinalizeResponse'>>(
    await request.post(`${API}/shopping/generations/${generation.id}/finalize`, { headers }),
  )
  expect(finalized.items).toHaveLength(1)
  listId = finalized.items[0]!.id
  const list = await body<Schema<'ShoppingListDetailRead'>>(
    await request.get(`${API}/shopping/lists/${listId}`),
  )
  const items = list.sections.flatMap((section) => section.items)
  itemId = items.find((item) => item.product_id === productId)!.id
  homeId = items.find((item) => item.product_id === products[1]!.id)!.id
  receivedId = items.find((item) => item.product_id === products[2]!.id)!.id
  await body(
    await request.patch(`${API}/shopping/lists/${listId}/items/${receivedId}`, {
      headers,
      data: { checked: true },
    }),
  )
  await body(await request.post(`${API}/shopping/lists/${listId}/accept-to-pantry`, { headers }))
  await body(
    await request.patch(`${API}/shopping/lists/${listId}/items/${homeId}`, {
      headers,
      data: { checked: true, already_have: true },
    }),
  )
})

test.afterAll(async ({ request: admin }) => {
  try {
    if (actor && actorId && authenticated) await cleanupOwn(actor.request, admin)
  } finally {
    try {
      if (actorId)
        await body(
          await admin.patch(`${API}/admin/users/${actorId}`, {
            headers: await csrfHeaders(admin),
            data: { is_active: false },
          }),
        )
    } finally {
      await actor?.close()
    }
  }
})

test('checklista: zwijanie, cofnięcie, offline, cały wydruk, publiczny zakres i idempotentne przyjęcie', async ({
  browser,
  baseURL,
}) => {
  test.setTimeout(120_000)
  const context = actor!
  const request = context.request
  const page = await context.newPage()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/zakupy')
  await expect(page.getByTestId(`shopping-list-count-${listId}`)).toContainText('Odhaczone 2 z 3')
  await page.getByTestId(`shopping-list-link-${listId}`).click()
  const checkbox = page.getByTestId(`shopping-check-${itemId}`)
  await expect(checkbox).toBeVisible()
  expect((await checkbox.boundingBox())!.width).toBeGreaterThanOrEqual(48)
  const name = page.getByTestId(`shopping-label-${itemId}`)
  await expect(name).toHaveText(LONG_NAME)
  expect(await name.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
  expect(
    await page.locator('html').evaluate((element) => element.scrollWidth <= element.clientWidth),
  ).toBe(true)
  await expect(page.getByTestId(`shopping-check-${homeId}`)).toBeVisible()
  await expect(page.getByTestId(`shopping-check-${receivedId}`)).toBeHidden()

  const endpoint = `**/api/v1/shopping/lists/${listId}/items/${itemId}`
  let releasePatch!: () => void
  const finishPatch = new Promise<void>((resolve) => {
    releasePatch = resolve
  })
  await page.route(endpoint, async (route) => {
    await finishPatch
    await route.fulfill({
      status: 409,
      json: { error: { code: 'conflict', message: 'Odmowa zapisu testowego.', details: {} } },
    })
  })
  await checkbox.focus()
  await page.keyboard.press('Space')
  const purchasedToggle = page.getByTestId('shopping-purchased-toggle')
  try {
    await expect(checkbox).toBeDisabled()
    await expect(checkbox).toBeHidden()
    await expect(purchasedToggle).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(checkbox).toBeVisible()
    await expect(checkbox).toBeDisabled()
  } finally {
    releasePatch()
  }
  await expect(page.getByTestId('lista-error')).toContainText('Odmowa')
  await expect(checkbox).not.toBeChecked()
  await page.unroute(endpoint)
  if ((await purchasedToggle.getAttribute('aria-expanded')) === 'true')
    await purchasedToggle.click()

  // Rzeczywiste odcięcie sieci, nie mock navigator.onLine. Reload bez
  // sieci jest osobno w preflight O na zbudowanym PWA.
  await context.setOffline(true)
  await checkbox.check()
  await expect(page.getByTestId('offline-pending')).toContainText('1')
  await expect(page.getByTestId('lista-accept-open')).toBeDisabled()
  await page.getByTestId('shopping-purchased-toggle').click()
  await checkbox.uncheck()
  await expect(checkbox).not.toBeChecked()
  await checkbox.check()
  await expect(page.getByTestId('offline-pending')).toContainText('1')
  // Odmowa dotyczy rzeczywistego PATCH-a kolejki po odzyskaniu sieci.
  // Nie podstawiamy sukcesu: serwerowy GET nadal zwraca nieodhaczony produkt.
  await page.route(endpoint, (route) =>
    route.fulfill({
      status: 422,
      json: { error: { code: 'validation_error', message: 'Odhaczenie odrzucone.', details: {} } },
    }),
  )
  await context.setOffline(false)
  await expect(page.getByTestId('offline-banner')).toHaveAttribute('role', 'alert')
  await expect(page.getByTestId('offline-banner')).toContainText('Nie udało się zapisać')
  await expect(checkbox).not.toBeChecked()
  await expect(page.getByTestId('lista-accept-open')).toBeDisabled()
  await page.unroute(endpoint)
  // Jawna ponowna decyzja tej pozycji zapisuje się online i zamyka jej błąd.
  await checkbox.check()
  await expect(page.getByTestId('offline-banner')).toHaveCount(0)
  const stored = await body<Schema<'ShoppingListDetailRead'>>(
    await request.get(`${API}/shopping/lists/${listId}`),
  )
  expect(
    stored.sections.flatMap((section) => section.items).find((item) => item.id === itemId)!.checked,
  ).toBe(true)
  await page.reload()
  await expect(checkbox).toBeHidden()
  await page.emulateMedia({ media: 'print' })
  for (const id of [itemId, homeId, receivedId])
    await expect(page.getByTestId(`shopping-item-${id}`)).toBeVisible()
  await expect(page.getByTestId('lista-akcje')).toBeHidden()
  await expect(page.getByTestId('lista-sklep')).toBeHidden()
  expect(
    await name.evaluate(
      (element) => element.ownerDocument.defaultView!.getComputedStyle(element).color,
    ),
  ).toBe('rgb(0, 0, 0)')
  await page.emulateMedia({ media: 'screen' })

  await page.getByTestId('lista-back').click()
  await expect(page.getByTestId(`shopping-list-count-${listId}`)).toContainText('Odhaczone 3 z 3')
  await page.getByTestId(`shopping-list-link-${listId}`).click()
  await page.getByTestId('lista-accept-open').click()
  await expect(page.getByTestId('accept-items')).toContainText(LONG_NAME)
  await expect(page.getByTestId('accept-items')).toContainText('2 x 1 kg')
  await expect(page.getByTestId('accept-items')).not.toContainText('Wcześniej przyjęte')
  await expect(page.getByTestId('accept-items')).not.toContainText('Mam już w domu')
  await page.getByTestId('accept-confirm').click()
  await expect(page.getByTestId('lista-info')).toContainText('Dodano do spiżarni')
  await expect(page.getByTestId('lista-accept-open')).toBeDisabled()
  const pantryBefore = await body<Schema<'PantryListResponse'>>(
    await request.get(`${API}/pantry`, { params: { q: PREFIX, limit: 200, offset: 0 } }),
  )
  const purchased = pantryBefore.items.find((item) => item.product_id === productId)!
  expect(purchased.amount).toMatch(/^2000(?:\.0+)?$/)
  const repeated = await request.post(`${API}/shopping/lists/${listId}/accept-to-pantry`, {
    headers,
  })
  expect(repeated.status()).toBe(409)
  const pantryAfter = await body<Schema<'PantryListResponse'>>(
    await request.get(`${API}/pantry`, { params: { q: PREFIX, limit: 200, offset: 0 } }),
  )
  expect(pantryAfter.items).toEqual(pantryBefore.items)

  const share = await body<Schema<'ShareRead'>>(
    await request.post(`${API}/shopping/lists/${listId}/share`, {
      headers,
      data: { expires_in_days: 7 },
    }),
  )
  // Nowa strona w ZALOGOWANYM kontekście sprawdza omit, mimo realnych cookies.
  const publicPage = await context.newPage()
  let authRequests = 0
  publicPage.on('request', (request) => {
    if (request.url().includes('/auth/me')) authRequests++
  })
  const publicResponsePromise = publicPage.waitForResponse(
    (response) =>
      response.url().includes('/api/v1/public/lists/') && response.request().method() === 'GET',
  )
  await publicPage.goto(share.url)
  const publicResponse = await publicResponsePromise
  const publicHeaders = await publicResponse.request().allHeaders()
  expect(publicHeaders.cookie).toBeUndefined()
  expect(publicHeaders['x-csrf-token']).toBeUndefined()
  const publicBody = (await publicResponse.json()) as Schema<'PublicListRead'>
  expect(Object.keys(publicBody).sort()).toEqual(['expires_at', 'items', 'name'])
  for (const item of publicBody.items) {
    expect(Object.keys(item).sort()).toEqual([
      'already_have',
      'amount',
      'category_name',
      'checked',
      'id',
      'label',
      'leftover_amount',
      'package_size',
      'packages_count',
      'unit',
    ])
  }
  await expect(publicPage.getByTestId('nav-sidebar')).toHaveCount(0)
  await expect(publicPage.locator('[data-testid^="shopping-received-"]')).toHaveCount(0)
  await expect(publicPage.getByTestId('lista-accept-open')).toHaveCount(0)
  expect(authRequests).toBe(0)
  await publicPage.close()

  // Oddzielny anonimowy kontekst oraz prawdziwe odwołanie → HTTP 410.
  const anonymous = await browser.newContext({ baseURL, storageState: EMPTY_STATE })
  try {
    const anonPage = await anonymous.newPage()
    await anonPage.goto(share.url)
    await expect(anonPage.getByTestId('public-list-title')).toHaveText(stored.name)
    expect(
      (await request.delete(`${API}/shopping/lists/${listId}/share`, { headers })).status(),
    ).toBe(204)
    const unavailable = anonPage.waitForResponse(
      (response) => response.url().includes('/api/v1/public/lists/') && response.status() === 410,
    )
    await anonPage.reload()
    await unavailable
    await expect(anonPage.getByTestId('public-list-unavailable')).toBeVisible()
    await expect(anonPage.getByTestId('public-list-title')).not.toHaveText(stored.name)
    await expect(anonPage.locator('[data-testid^="shopping-item-"]')).toHaveCount(0)
  } finally {
    await anonymous.close()
  }
})
