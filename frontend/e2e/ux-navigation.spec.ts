import { randomBytes } from 'node:crypto'

import { expect, test } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'
import type { components } from '../src/api/generated.js'
import { EMPTY_STATE } from './auth-state.js'
import { csrfHeaders } from './cleanup.js'

/** Pięć scenariuszy tylko odczytu; granicę ADMIN sprawdza osobne, tymczasowe konto USER. */
test('stare linki, konkretny dzień, tydzień, podsumowanie i zakres zakupów', async ({ page }) => {
  await page.goto('/plan-dnia/2031-03-05')
  await expect(page.getByTestId('plan-dnia-page')).toBeVisible()
  await page.getByTestId('plan-view-tydzien').click()
  await expect(page).toHaveURL(/\/tydzien\/2031-03-03\?/)
  await expect(page.getByTestId('week-day-2031-03-05')).toHaveClass(/ring-2/)
  await expect(page.locator('#main-content')).toBeFocused()
  await page.getByTestId('week-day-select-2031-03-07').click()
  await expect(page).toHaveURL(/selectedDate=2031-03-07/)
  await expect(page.getByTestId('week-day-select-2031-03-07')).toBeFocused()
  await page.getByTestId('week-next').click()
  await expect(page).toHaveURL(/selectedDate=2031-03-14/)
  await page.getByTestId('plan-view-plan-dnia').click()
  await expect(page).toHaveURL(/\/plan-dnia\/2031-03-14\?/)
  await page.getByTestId('plan-view-statystyki').click()
  await expect(page.getByTestId('stats-range')).toContainText('10.03.2031')
  await expect(page.getByTestId('stats-range')).toContainText('16.03.2031')
  await page.reload()
  await expect(page.getByTestId('stats-range')).toContainText('10.03.2031')
  await page.getByTestId('plan-shopping-link').click()
  const query = new URL(page.url()).searchParams
  expect(query.get('from')).toBe('2031-03-10')
  expect(query.get('to')).toBe('2031-03-16')
  expect(query.get('selectedDate')).toBe('2031-03-14')
})

test('telefon 360px: cztery wejścia, konto dotykiem i klawiaturą, scroll i skiplink', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 360, height: 780 })
  await page.goto('/plan-dnia/2031-03-05')
  const bottom = page.getByTestId('nav-bottom')
  await expect(bottom).toBeVisible()
  const links = bottom.getByRole('link')
  await expect(links).toHaveCount(4)
  expect(await links.allTextContents()).toEqual(['Plan', 'Przepisy', 'Zakupy', 'Spiżarnia'])
  for (const link of await links.all()) {
    const box = (await link.boundingBox())!
    expect(box.width).toBeGreaterThanOrEqual(44)
    expect(box.height).toBeGreaterThanOrEqual(44)
    expect(box.x).toBeGreaterThanOrEqual(0)
    expect(box.x + box.width).toBeLessThanOrEqual(360)
  }
  await page.getByTestId('account-toggle-mobile').click()
  await expect(page.getByTestId('account-item-ustawienia-mobile')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('account-admin-mobile-360.png') })
  await page.emulateMedia({ media: 'print' })
  await expect(page.getByTestId('account-menu-mobile')).toBeHidden()
  await expect(page.locator('#main-content')).toBeVisible()
  await expect(page.getByTestId('plan-date')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('account-admin-mobile-360-print.png') })
  await page.emulateMedia({ media: 'screen' })
  await expect(page.getByTestId('account-menu-mobile')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('account-toggle-mobile')).toBeFocused()
  await page.keyboard.press('Enter')
  await page.getByTestId('account-item-ustawienia-mobile').click()
  await expect(page).toHaveURL(/\/ustawienia$/)
  await expect(page.locator('#main-content')).toBeFocused()
  await expect(page.getByTestId('account-menu-mobile')).toHaveCount(0)
  await page.getByTestId('account-toggle-mobile').click()
  await page.getByTestId('account-item-produkty-mobile').click()
  await expect(page).toHaveURL(/\/produkty$/)
  await page.getByTestId('nav-bottom-spizarnia').click()
  await expect(page).toHaveURL(/\/spizarnia$/)
  await expect(page.locator('main')).toHaveCSS('padding-bottom', '96px')
  const navHeight = await bottom.evaluate((element) => element.getBoundingClientRect().height)
  expect(navHeight).toBeLessThan(96)
  // `load` kończy się przed asynchronicznym montażem SPA; Tab wymaga gotowego shella.
  await page.reload()
  await expect(page.getByTestId('app-shell')).toBeVisible()
  await expect(page.getByTestId('skip-link')).toBeAttached()
  await page.keyboard.press('Tab')
  await expect(page.getByTestId('skip-link')).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.locator('#main-content')).toBeFocused()
})

test('query filtra nie zabiera fokusu, a nawigacja aktywuje szczegóły i edytory', async ({
  page,
}) => {
  await page.goto('/przepisy')
  const search = page.getByTestId('recipes-search')
  await search.fill('E2E nawigacja brak wyniku')
  await expect(search).toBeFocused()
  await page.goto('/przepisy/nowy')
  await expect(page.getByTestId('nav-item-przepisy')).toHaveAttribute('aria-current', 'page')
  await page.goto('/produkty/nowy')
  await expect(page.getByTestId('nav-item-produkty')).toHaveAttribute('aria-current', 'page')
})

const ACCOUNT_PREFIX = 'e2e-navigation-'
const API = '/api/v1'

/** Zbiera ID przed usuwaniem, żeby paginacja nie pomijała kont po przesunięciu offsetu. */
async function purgeNavigationAccounts(request: APIRequestContext): Promise<void> {
  const headers = await csrfHeaders(request)
  const ids: number[] = []
  let offset = 0
  let total: number
  do {
    const response = await request.get(`${API}/admin/users`, {
      params: { q: ACCOUNT_PREFIX, limit: 200, offset },
    })
    expect(response.status(), 'odczyt własnych kont nawigacji do sprzątania').toBe(200)
    const users = (await response.json()) as components['schemas']['UserListResponse']
    ids.push(
      ...users.items.filter((user) => user.email.startsWith(ACCOUNT_PREFIX)).map((user) => user.id),
    )
    total = users.total
    offset += users.items.length
    if (users.items.length === 0) break
  } while (offset < total)
  for (const id of ids) {
    const response = await request.delete(`${API}/admin/users/${id}`, { headers })
    expect(response.status(), 'usunięcie wyłącznie własnego konta nawigacji bez zasobów').toBe(204)
  }
}

test.describe('rzeczywista sesja USER i granica administracji', () => {
  test.beforeAll(async ({ request }) => {
    await purgeNavigationAccounts(request)
  })

  test.afterAll(async ({ request }) => {
    await purgeNavigationAccounts(request)
  })

  test('USER nie widzi administracji, guard przekierowuje, a API odmawia dostępu', async ({
    browser,
    request,
    baseURL,
  }, testInfo) => {
    const email = `${ACCOUNT_PREFIX}${randomBytes(8).toString('hex')}@example.com`
    const password = `${randomBytes(18).toString('base64url')}aA1`
    const account = await request.post(`${API}/admin/users`, {
      headers: await csrfHeaders(request),
      data: {
        email,
        password,
        display_name: 'E2E Nawigacja — Aleksandra Katarzyna Żółkiewicz-Woźniak',
        role: 'user',
      },
    })
    expect(account.status(), 'ADMIN tworzy własne tymczasowe konto USER').toBe(201)

    const context = await browser.newContext({ baseURL, storageState: EMPTY_STATE })
    try {
      const userPage = await context.newPage()
      await userPage.goto('/login')
      await userPage.getByTestId('login-email').fill(email)
      await userPage.getByTestId('login-password').fill(password)
      await userPage.getByTestId('login-submit').click()
      await expect(userPage).toHaveURL(/\/plan-dnia$/)

      const current = await context.request.get(`${API}/auth/me`)
      expect(current.status()).toBe(200)
      const user = (await current.json()) as components['schemas']['CurrentUser']
      expect(user.role).toBe('user')
      expect(user.email).toBe(email)
      expect(user.household).toBeNull()

      await userPage.goto('/admin/uzytkownicy')
      await expect(userPage).toHaveURL(/\/plan-dnia$/)
      await userPage.getByTestId('account-toggle').click()
      await expect(userPage.getByTestId('account-item-ustawienia')).toBeVisible()
      await expect(userPage.locator('[data-testid^="account-item-admin-"]')).toHaveCount(0)
      await userPage.screenshot({ path: testInfo.outputPath('account-user-desktop.png') })
      await userPage.emulateMedia({ media: 'print' })
      await expect(userPage.getByTestId('account-menu')).toBeHidden()
      await expect(userPage.locator('#main-content')).toBeVisible()
      await expect(userPage.getByTestId('plan-date')).toBeVisible()
      await userPage.screenshot({ path: testInfo.outputPath('account-user-desktop-print.png') })
      await userPage.emulateMedia({ media: 'screen' })
      await expect(userPage.getByTestId('account-menu')).toBeVisible()

      const forbidden = await context.request.get(`${API}/admin/users`)
      expect(forbidden.status(), 'sesja USER nie czyta administracyjnego API').toBe(403)
    } finally {
      await context.close()
    }
  })
})

for (const authenticated of [false, true]) {
  test(`publiczny URL poza shellem i bez auth/me, sesja=${authenticated}`, async ({
    browser,
    page,
  }) => {
    const context = authenticated ? null : await browser.newContext({ storageState: EMPTY_STATE })
    const target = context ? await context.newPage() : page
    const authRequests: string[] = []
    target.on('request', (request) => {
      if (request.url().includes('/api/v1/auth/')) authRequests.push(request.url())
    })
    // Nieznany, poprawny składniowo token nie wymaga tworzenia ani ujawniania listy.
    await target.goto(`/l/${'a'.repeat(43)}`)
    await expect(target.getByTestId('public-list-unavailable')).toBeVisible()
    await expect(target.getByTestId('app-shell')).toHaveCount(0)
    expect(authRequests).toEqual([])
    await context?.close()
  })
}
