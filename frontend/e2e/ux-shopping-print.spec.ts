import { randomBytes } from 'node:crypto'
import { writeFile } from 'node:fs/promises'
import {
  expect,
  test,
  type BrowserContext,
  type Page,
  type Response,
  type TestInfo,
} from '@playwright/test'
import type { components } from '../src/api/generated.js'
import { EMPTY_STATE } from './auth-state.js'
import { reserveLoginAttempt } from './login-budget.js'

type Schema<K extends keyof components['schemas']> = components['schemas'][K]
const API = '/api/v1'
const MARKER = 'E2E UX06 PRINT A4 v1'
const EMAIL = 'e2e-ux06-print-a4-v1@example.com'
const ACTOR = `${MARKER} actor`
const ROUND = `${MARKER} tura`
const MEAL = `${MARKER} posilek`
const DATE = '2039-04-11'
const PRODUCT_NAMES = Array.from({ length: 50 }, (_, index) => {
  const row = `R${String(index + 1).padStart(2, '0')}`
  return `${row} - ${MARKER} - Płatki pełnoziarniste z pestkami dyni, suszoną żurawiną i orzechami laskowymi - duże rodzinne opakowanie do zapiekanek i domowego śniadania - KONIEC_${row}`
})
const OWN_NAMES = new Set(PRODUCT_NAMES)
const QUANTITIES = [
  { amount: '1234', display: '1,234 kg' },
  { amount: '987', display: '987 g' },
  { amount: '2500', display: '2,5 kg' },
  { amount: '10000', display: '10 kg' },
  { amount: '125.5', display: '125,5 g' },
] as const
let actorId: number | undefined
let actor: BrowserContext | undefined
let actorApi: NativeApi | undefined
let adminContext: BrowserContext | undefined
let adminApi: NativeApi | undefined
let authenticated = false
let list: Schema<'ShoppingListDetailRead'>

// Ten opt-in tworzy prawdziwe dane i PDF-y. Domyślna suita nie uruchamia
// hooków ani nie zmienia żadnych danych, gdy UX_PRINT nie jest równe 1.
test.skip(process.env.UX_PRINT !== '1', 'Rzeczywisty wydruk A4 wymaga UX_PRINT=1.')
test.use({ trace: 'off', video: 'off', screenshot: 'off' })

// Node fetch nie tworzy kroków Playwright APIRequestContext. Przy błędzie
// transportu nie powstaje zagnieżdżony krok z Cookie/CSRF/hasłem w call logu.
// Sam catch wokół APIRequestContext nie zapewniłby tej własności.
class NativeApi {
  private context: BrowserContext
  private baseURL: string

  constructor(context: BrowserContext, baseURL: string) {
    this.context = context
    this.baseURL = baseURL
  }

  get(path: string, options?: { params?: Record<string, string | number | boolean> }) {
    return this.send('GET', path, options)
  }

  post(path: string, options?: { data?: unknown }) {
    return this.send('POST', path, options)
  }

  patch(path: string, options?: { data?: unknown }) {
    return this.send('PATCH', path, options)
  }

  delete(path: string) {
    return this.send('DELETE', path)
  }

  private async send(
    method: string,
    path: string,
    options?: { params?: Record<string, string | number | boolean>; data?: unknown },
  ): Promise<Pick<Response, 'status' | 'json'>> {
    let status: number | undefined
    try {
      const url = new URL(path, this.baseURL)
      if (url.origin !== new URL(this.baseURL).origin || !url.pathname.startsWith(`${API}/`))
        throw new Error('Niedozwolony cel HTTP.')
      for (const [key, value] of Object.entries(options?.params ?? {}))
        url.searchParams.set(key, String(value))
      const cookies = await this.context.cookies(url.href)
      const headers: Record<string, string> = { Accept: 'application/json' }
      if (cookies.length)
        headers.Cookie = cookies.map((cookie) => `${cookie.name}=${cookie.value}`).join('; ')
      if (method !== 'GET' && url.pathname !== `${API}/auth/login`) {
        const csrf = cookies.find((cookie) =>
          ['__Host-csrf_token', 'csrf_token'].includes(cookie.name),
        )
        if (!csrf) throw new Error('Brak CSRF.')
        headers['X-CSRF-Token'] = csrf.value
      }
      if (options?.data !== undefined) headers['Content-Type'] = 'application/json'
      const response = await fetch(url, {
        method,
        headers,
        body: options?.data === undefined ? undefined : JSON.stringify(options.data),
        redirect: 'error',
        signal: AbortSignal.timeout(30_000),
      })
      status = response.status
      await this.applyCookies(response.headers.getSetCookie(), url)
      // Odczyt ciała także wewnątrz bezpiecznej granicy: reset w trakcie
      // pobierania JSON-a nie może ujawnić przyczyny ani surowego payloadu.
      const payload: unknown = response.status === 204 ? null : await response.json()
      return { status: () => response.status, json: async () => payload }
    } catch {
      // Bez cause, URL-a, nagłówków i treści żądania/odpowiedzi.
      throw new Error(`Niepowodzenie HTTP testu wydruku (status ${status ?? 'brak'}).`)
    }
  }

  private async applyCookies(values: string[], url: URL): Promise<void> {
    for (const value of values) {
      const [pair = '', ...attributes] = value.split(';')
      const separator = pair.indexOf('=')
      if (separator < 1) throw new Error('Nieprawidłowe Set-Cookie.')
      const cookie: Parameters<BrowserContext['addCookies']>[0][number] = {
        name: pair.slice(0, separator).trim(),
        value: pair.slice(separator + 1).trim(),
        domain: url.hostname,
        path: url.pathname.slice(0, url.pathname.lastIndexOf('/')) || '/',
      }
      let maxAge: number | undefined
      for (const attribute of attributes) {
        const [key = '', ...rest] = attribute.trim().split('=')
        const content = rest.join('=')
        switch (key.toLowerCase()) {
          case 'domain':
            cookie.domain = content
            break
          case 'path':
            cookie.path = content
            break
          case 'httponly':
            cookie.httpOnly = true
            break
          case 'secure':
            cookie.secure = true
            break
          case 'samesite': {
            const sameSite = content.toLowerCase()
            if (!['strict', 'lax', 'none'].includes(sameSite))
              throw new Error('Nieprawidłowe SameSite.')
            cookie.sameSite = sameSite === 'strict' ? 'Strict' : sameSite === 'lax' ? 'Lax' : 'None'
            break
          }
          case 'expires': {
            const expires = Date.parse(content)
            if (!Number.isFinite(expires)) throw new Error('Nieprawidłowe Expires.')
            cookie.expires = Math.floor(expires / 1000)
            break
          }
          case 'max-age': {
            if (!/^-?\d+$/.test(content)) throw new Error('Nieprawidłowe Max-Age.')
            maxAge = Number(content)
            if (!Number.isSafeInteger(maxAge)) throw new Error('Nieprawidłowe Max-Age.')
            break
          }
        }
      }
      // Max-Age ma pierwszeństwo nad Expires, niezależnie od kolejności.
      if (maxAge !== undefined)
        cookie.expires = maxAge <= 0 ? 1 : Math.floor(Date.now() / 1000) + maxAge
      await this.context.addCookies([cookie])
    }
  }
}

async function body<T>(response: Pick<Response, 'status' | 'json'>, status = 200): Promise<T> {
  // Bez URL-a i raw body: odpowiedzi share i auth zawierają sekrety.
  expect(response.status(), 'Oczekiwany status odpowiedzi API').toBe(status)
  return response.json() as Promise<T>
}

async function paged<T>(request: NativeApi, path: string): Promise<T[]> {
  const rows: T[] = []
  for (let offset = 0; ; offset += 200) {
    const result = await body<{ items: T[]; total: number }>(
      await request.get(`${API}${path}`, {
        params: { include_archived: true, limit: 200, offset },
      }),
    )
    rows.push(...result.items)
    if (offset + result.items.length >= result.total) return rows
    expect(result.items.length, 'Paginacja musi postępować').toBeGreaterThan(0)
  }
}

async function remove(request: NativeApi, path: string): Promise<void> {
  expect((await request.delete(`${API}${path}`)).status(), 'Usunięcie własnego zasobu').toBe(204)
}

async function cleanupOwn(request: NativeApi, admin: NativeApi): Promise<void> {
  // Wyłącznie dokładne znaczniki tego speca, także po przerwanym przebiegu.
  // Nigdy cleanupE2eData/purgeE2eLeftovers ani cudza rodzina/historia ADMIN-a.
  const lists = await paged<Schema<'ShoppingListSummaryRead'>>(request, '/shopping/lists')
  for (const row of lists.filter((row) => row.round_name === ROUND))
    await remove(request, `/shopping/lists/${row.id}`)

  const day = await body<Schema<'DayRead'>>(await request.get(`${API}/plan/days/${DATE}`))
  for (const meal of day.meals.filter((meal) => meal.name === MEAL)) {
    await body(await request.delete(`${API}/plan/meals/${meal.id}`))
  }
  // Plan zawiera tylko produkty luzem, więc nie powstaje żaden przepis.
  const pantry = await paged<Schema<'PantryItemRead'>>(request, '/pantry')
  for (const row of pantry.filter((row) => row.product_name && OWN_NAMES.has(row.product_name)))
    await remove(request, `/pantry/${row.id}`)

  const rounds = await body<Schema<'RoundConfigListResponse'>>(
    await request.get(`${API}/shopping/round-configs`),
  )
  for (const round of rounds.items.filter((round) => round.name === ROUND))
    await remove(request, `/shopping/round-configs/${round.id}`)

  const products = (await paged<Schema<'ProductRead'>>(admin, '/products')).filter((row) =>
    OWN_NAMES.has(row.name),
  )
  const ownProductIds = new Set(products.map((row) => row.id))
  const retail = await paged<Schema<'RetailProductRead'>>(admin, '/retail-products')
  for (const row of retail.filter(
    (row) => ownProductIds.has(row.canonical_product_id) && OWN_NAMES.has(row.name),
  ))
    await remove(admin, `/retail-products/${row.id}`)
  for (const product of products) await remove(admin, `/products/${product.id}`)
}

test.beforeAll(async ({ request: adminSession, browser, baseURL }, testInfo) => {
  test.setTimeout(180_000)
  if (!baseURL || !['localhost', '127.0.0.1', '[::1]', '::1'].includes(new URL(baseURL).hostname))
    throw new Error('Test wydruku z własnymi danymi jest dozwolony wyłącznie na localhost.')
  // Standardowy fixture setup/storageState dostarcza sesję ADMIN-a. Samo
  // storageState nie wykonuje HTTP; wszystkie żądania niżej to Node fetch.
  adminContext = await browser.newContext({
    baseURL,
    storageState: await adminSession.storageState(),
  })
  const admin = new NativeApi(adminContext, baseURL)
  adminApi = admin
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
        data: { password, is_active: true },
      }),
    )
  } else {
    const user = await body<Schema<'UserRead'>>(
      await admin.post(`${API}/admin/users`, {
        data: { email: EMAIL, display_name: ACTOR, role: 'user', password },
      }),
      201,
    )
    actorId = user.id
  }

  // Persistent USER, bez rodziny; historia generacji zachowuje FK aktora.
  // Losowe hasło żyje wyłącznie w pamięci, nie w storageState ani artefaktach.
  actor = await browser.newContext({ baseURL, storageState: EMPTY_STATE })
  const request = new NativeApi(actor, baseURL)
  actorApi = request
  await reserveLoginAttempt(baseURL, testInfo, 180_000)
  await body<Schema<'CurrentUser'>>(
    await request.post(`${API}/auth/login`, { data: { email: EMAIL, password } }),
  )
  const current = await body<Schema<'CurrentUser'>>(await request.get(`${API}/auth/me`))
  expect(current.id).toBe(actorId)
  expect(current.role).toBe('user')
  expect(current.household).toBeNull()
  expect((await request.get(`${API}/admin/users`)).status()).toBe(403)
  authenticated = true
  await cleanupOwn(request, admin)
  const categories = await body<Schema<'CategoryListResponse'>>(
    await request.get(`${API}/categories`),
  )
  expect(categories.items.length).toBeGreaterThanOrEqual(2)
  const products: Schema<'ProductDetail'>[] = []
  for (const [index, name] of PRODUCT_NAMES.entries()) {
    expect(name.length).toBeLessThanOrEqual(200)
    products.push(
      await body<Schema<'ProductDetail'>>(
        await request.post(`${API}/products`, {
          data: {
            name,
            category_id: categories.items[index % 2]!.id,
            measure_kind: 'mass',
            perishability_override: 'durable',
          },
        }),
        201,
      ),
    )
  }
  const round = await body<Schema<'RoundConfigRead'>>(
    await request.post(`${API}/shopping/round-configs`, {
      data: { name: ROUND, mode: 'all', covers_days: 7 },
    }),
    201,
  )
  const day = await body<Schema<'DayRead'>>(
    await request.post(`${API}/plan/days/${DATE}/meals`, {
      data: { name: MEAL },
    }),
    201,
  )
  const meal = day.meals.find((meal) => meal.name === MEAL)!
  for (const [index, product] of products.entries()) {
    await body(
      await request.post(`${API}/plan/meals/${meal.id}/items`, {
        data: {
          product_id: product.id,
          quantity: QUANTITIES[index % QUANTITIES.length]!.amount,
          unit: 'g',
        },
      }),
      201,
    )
  }
  // Brak wariantów sklepowych jest poprawnym wejściem silnika, bez atrap.
  const generation = await body<Schema<'GenerationRead'>>(
    await request.post(`${API}/shopping/generate`, {
      data: { date_from: DATE, date_to: DATE, use_pantry: false, round_config_ids: [round.id] },
    }),
    201,
  )
  expect(generation.has_blockers).toBe(false)
  const finalized = await body<Schema<'FinalizeResponse'>>(
    await request.post(`${API}/shopping/generations/${generation.id}/finalize`),
    201,
  )
  expect(finalized.items).toHaveLength(1)
  const listId = finalized.items[0]!.id
  const initial = await body<Schema<'ShoppingListDetailRead'>>(
    await request.get(`${API}/shopping/lists/${listId}`),
  )
  const items = initial.sections.flatMap((section) => section.items)
  expect(items).toHaveLength(PRODUCT_NAMES.length)
  for (const [index, item] of items.entries()) {
    if (index % 2 !== 0) continue
    await body(
      await request.patch(`${API}/shopping/lists/${listId}/items/${item.id}`, {
        data: { checked: true, ...(index === 0 ? { already_have: true } : {}) },
      }),
    )
  }
  // Źródłem oczekiwanej kolejności jest końcowy GET serwera, po already_have.
  list = await body<Schema<'ShoppingListDetailRead'>>(
    await request.get(`${API}/shopping/lists/${listId}`),
  )
  expect(list.sections).toHaveLength(2)
  expect(
    list.sections
      .flatMap((section) => section.items)
      .map((item) => item.label)
      .sort(),
  ).toEqual([...PRODUCT_NAMES].sort())
  expect(
    list.sections.flatMap((section) => section.items).filter((item) => item.checked),
  ).toHaveLength(25)
  for (const item of list.sections.flatMap((section) => section.items)) {
    const quantity = QUANTITIES[PRODUCT_NAMES.indexOf(item.label) % QUANTITIES.length]!
    expect(item.amount_unit).toBe('g')
    expect(item.needed_amount.replace(/(\.[0-9]*?)0+$/, '$1').replace(/\.$/, '')).toBe(
      quantity.amount,
    )
  }
})

test.afterAll(async () => {
  test.setTimeout(120_000)
  try {
    if (actorApi && adminApi && authenticated) await cleanupOwn(actorApi, adminApi)
  } finally {
    try {
      // Dezaktywacja także po FAIL w setupie/sprzątaniu; nie usuwamy aktora,
      // którego zachowuje historia generacji (FK RESTRICT).
      if (actorId && adminApi)
        await body(
          await adminApi.patch(`${API}/admin/users/${actorId}`, {
            data: { is_active: false },
          }),
        )
    } finally {
      await Promise.all([actor?.close(), adminContext?.close()])
    }
  }
})

function expectedRows() {
  return list.sections
    .flatMap((section, sectionIndex) =>
      section.items.map((item) => ({
        order: 0,
        section_order: sectionIndex,
        category_name: section.category_name,
        item_id: item.id,
        label: item.label,
        amount: item.needed_amount,
        unit: item.amount_unit,
        display_amount: QUANTITIES[PRODUCT_NAMES.indexOf(item.label) % QUANTITIES.length]!.display,
        packages_count: item.packages_count,
        package_size: item.package_size,
        leftover_amount: item.leftover_amount,
        checked: item.checked,
        already_have: item.already_have,
      })),
    )
    .map((row, order) => ({ ...row, order }))
}

async function assertPrintedRows(page: Page): Promise<void> {
  const expected = expectedRows()
  await expect(page.locator('[data-testid^="shopping-item-"]')).toHaveCount(expected.length)
  await expect(page.locator('.shopping-category > header h2')).toHaveText(
    list.sections.map((section) => section.category_name),
  )
  expect(
    await page
      .locator('[data-testid^="shopping-item-"]')
      .evaluateAll((elements) => elements.map((element) => element.getAttribute('data-testid'))),
  ).toEqual(expected.map((row) => `shopping-item-${row.item_id}`))
  await page.locator('html').evaluate(async (element) => {
    await element.ownerDocument.fonts.ready
  })
  for (const row of expected) {
    await expect(page.getByTestId(`shopping-item-${row.item_id}`)).toBeVisible()
    const label = page.getByTestId(`shopping-label-${row.item_id}`)
    await expect(label).toHaveText(row.label)
    await expect(page.getByTestId(`shopping-amount-${row.item_id}`)).toHaveText(row.display_amount)
    await expect(page.getByTestId(`shopping-check-${row.item_id}`)).toBeHidden()
    expect(
      await label.evaluate((element) => {
        const style = element.ownerDocument.defaultView!.getComputedStyle(element)
        return {
          color: style.color,
          decoration: style.textDecorationLine,
          fits: element.scrollWidth <= element.clientWidth,
        }
      }),
    ).toEqual({ color: 'rgb(0, 0, 0)', decoration: 'none', fits: true })
  }
  for (const toggle of await page.getByTestId('shopping-purchased-toggle').all())
    await expect(toggle).toBeHidden()
  for (const navigation of await page.locator('nav, aside').all())
    await expect(navigation).toBeHidden()
}

async function saveA4(page: Page, testInfo: TestInfo, name: string): Promise<void> {
  const path = testInfo.outputPath(name)
  const pdf = await page.pdf({
    format: 'A4',
    printBackground: false,
    preferCSSPageSize: true,
    displayHeaderFooter: false,
    path,
  })
  await testInfo.attach(name, { path, contentType: 'application/pdf' })
  // Chromium zapisuje osobny /Type /Page dla każdej fizycznej strony.
  // Root dodatkowo sprawdza tekst, A4, bbox i render PNG narzędziami PDF.
  expect(pdf.subarray(0, 5).toString('ascii')).toBe('%PDF-')
  expect(pdf.toString('latin1').match(/\/Type\s*\/Page\b/g)?.length ?? 0).toBeGreaterThanOrEqual(2)
}

test('rzeczywista długa lista: prywatny i anonimowy wydruk A4 obejmuje wszystkie wiersze', async ({
  browser,
  baseURL,
}, testInfo) => {
  test.setTimeout(180_000)
  const context = actor!
  const page = await context.newPage()
  const privateResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`${API}/shopping/lists/${list.id}`) &&
      response.request().method() === 'GET',
  )
  await page.goto(`/zakupy/listy/${list.id}`)
  await body<Schema<'ShoppingListDetailRead'>>(await privateResponse)
  await expect(page.getByTestId('lista-nazwa')).toHaveText(list.name)
  const rows = expectedRows()
  const expectedPath = testInfo.outputPath('shopping-print-expected-rows.json')
  await writeFile(
    expectedPath,
    JSON.stringify(
      {
        schema_version: 1,
        paper: 'A4',
        minimum_pages: 2,
        private_pdf: 'shopping-private-a4.pdf',
        public_pdf: 'shopping-public-a4.pdf',
        title: list.name,
        rows,
      },
      null,
      2,
    ),
  )
  await testInfo.attach('shopping-print-expected-rows.json', {
    path: expectedPath,
    contentType: 'application/json',
  })
  for (const row of rows.filter((row) => row.checked && !row.already_have))
    await expect(page.getByTestId(`shopping-item-${row.item_id}`)).toBeHidden()
  await expect(page.getByTestId('shopping-purchased-toggle').first()).toHaveAttribute(
    'aria-expanded',
    'false',
  )
  await page.emulateMedia({ media: 'print' })
  await assertPrintedRows(page)
  for (const id of [
    'lista-akcje',
    'lista-sklep',
    'lista-share-open',
    'lista-print',
    'lista-progress',
    'nav-sidebar',
    'nav-bottom',
  ])
    await expect(page.getByTestId(id)).toBeHidden()
  await saveA4(page, testInfo, 'shopping-private-a4.pdf')

  const share = await body<Schema<'ShareRead'>>(
    await actorApi!.post(`${API}/shopping/lists/${list.id}/share`, {
      data: { expires_in_days: 7 },
    }),
    201,
  )
  const anonymous = await browser.newContext({ baseURL, storageState: EMPTY_STATE })
  try {
    const publicPage = await anonymous.newPage()
    let authRequests = 0
    publicPage.on('request', (request) => {
      if (new URL(request.url()).pathname === `${API}/auth/me`) authRequests++
    })
    const publicResponse = publicPage.waitForResponse(
      (response) =>
        response.url().includes(`${API}/public/lists/`) && response.request().method() === 'GET',
    )
    // page.goto(token) pokazuje token w kroku reportera. location.assign
    // z about:blank nie otwiera po drodze guardowanej strony ani /auth/me.
    await publicPage
      .locator('html')
      .evaluate(
        (element, url) => element.ownerDocument.defaultView!.location.assign(url),
        new URL(share.url, baseURL).href,
      )
    const response = await publicResponse
    const publicHeaders = await response.request().allHeaders()
    expect(publicHeaders.cookie === undefined, 'Publiczny GET bez Cookie').toBe(true)
    expect(publicHeaders['x-csrf-token'] === undefined, 'Publiczny GET bez CSRF').toBe(true)
    const publicList = await body<Schema<'PublicListRead'>>(response)
    expect(Object.keys(publicList).sort()).toEqual(['expires_at', 'items', 'name'])
    for (const item of publicList.items)
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
    expect(
      publicList.items.map((item) => ({
        id: item.id,
        label: item.label,
        amount: item.amount,
        unit: item.unit,
        category_name: item.category_name,
        checked: item.checked,
        already_have: item.already_have,
      })),
    ).toEqual(
      rows.map((row) => ({
        id: row.item_id,
        label: row.label,
        amount: row.amount,
        unit: row.unit,
        category_name: row.category_name,
        checked: row.checked,
        already_have: row.already_have,
      })),
    )
    await expect(publicPage.getByTestId('public-list-title')).toHaveText(list.name)
    for (const row of rows.filter((row) => row.checked && !row.already_have))
      await expect(publicPage.getByTestId(`shopping-item-${row.item_id}`)).toBeHidden()
    await publicPage.emulateMedia({ media: 'print' })
    await assertPrintedRows(publicPage)
    for (const id of ['public-list-meta', 'public-list-print'])
      await expect(publicPage.getByTestId(id)).toBeHidden()
    for (const id of ['nav-sidebar', 'nav-bottom', 'lista-akcje', 'lista-accept-open'])
      await expect(publicPage.getByTestId(id)).toHaveCount(0)
    await expect(publicPage.locator('[data-testid^="shopping-received-"]')).toHaveCount(0)
    expect(authRequests).toBe(0)
    await saveA4(publicPage, testInfo, 'shopping-public-a4.pdf')
  } finally {
    await anonymous.close()
  }
})
