import { randomBytes } from 'node:crypto'
import { expect, test, type BrowserContext } from '@playwright/test'
import type { components } from '../src/api/generated.js'
import { EMPTY_STATE } from './auth-state.js'
import { csrfHeaders } from './cleanup.js'
import { reserveLoginAttempt } from './login-budget.js'
import { fillSecretPassword } from './secret-password.js'

test.use({ trace: 'off' })
const API = '/api/v1'
const PREFIX = 'E2E UX10 ustawienia'
const LONG_NAME = `${PREFIX} Aleksandra z bardzo długim nazwiskiem dwuczłonowym i opisem osoby przy wspólnym stole`

test('ustawienia: wszystkie sekcje, błąd z zachowaniem szkicu, historia i klawiatura 390/1024', async ({
  browser,
  request: admin,
  baseURL,
}, testInfo) => {
  test.setTimeout(120_000)
  const adminHeaders = await csrfHeaders(admin)
  const email = `e2e-ux10-${randomBytes(10).toString('hex')}@example.com`
  const password = `${randomBytes(24).toString('base64url')}aA1`
  let context: BrowserContext | undefined
  let userId: number | undefined
  let householdId: number | undefined
  let authenticated = false
  let shoppingOpened = false
  try {
    const account = await admin.post(`${API}/admin/users`, {
      headers: adminHeaders,
      data: { email, password, display_name: PREFIX, role: 'user' },
    })
    expect(account.status(), 'utworzenie własnego konta USER').toBe(201)
    userId = ((await account.json()) as components['schemas']['UserRead']).id
    const family = await admin.post(`${API}/admin/households`, {
      headers: adminHeaders,
      data: { name: `${PREFIX} rodzina z długą nazwą do kontroli zawijania tekstu` },
    })
    expect(family.status()).toBe(201)
    householdId = ((await family.json()) as components['schemas']['HouseholdDetail']).id
    const assigned = await admin.put(`${API}/admin/households/${householdId}/members`, {
      headers: adminHeaders,
      data: { user_ids: [userId] },
    })
    expect(assigned.status()).toBe(200)

    context = await browser.newContext({
      baseURL,
      storageState: EMPTY_STATE,
      viewport: { width: 390, height: 844 },
    })
    const page = await context.newPage()
    let roundReads = 0
    page.on('request', (request) => {
      if (
        request.method() === 'GET' &&
        new URL(request.url()).pathname === `${API}/shopping/round-configs`
      )
        roundReads += 1
    })
    await page.goto('/ustawienia')
    await expect(page.getByTestId('login-card')).toBeVisible()
    await page.getByTestId('login-email').fill(email)
    await fillSecretPassword(page.getByTestId('login-password'), password)
    await reserveLoginAttempt(baseURL, testInfo)
    await page.getByTestId('login-submit').click()
    await expect(page).toHaveURL(/\/ustawienia$/)
    authenticated = true
    await expect(page.getByTestId('household-members')).toContainText(email)
    await expect(page.getByRole('heading', { name: 'Osoby, dla których gotujemy' })).toBeVisible()
    await expect(page.getByText('Konta z dostępem do rodziny', { exact: true })).toBeVisible()
    expect(roundReads).toBe(0)
    expect((await context.request.get(`${API}/admin/users`)).status()).toBe(403)
    page.on('dialog', (dialog) => dialog.accept())

    // One genuine failed save, then a real server save. No synthetic success.
    let rejectFirst = true
    await page.route('**/api/v1/households/my/profiles', async (route) => {
      if (route.request().method() === 'POST' && rejectFirst) {
        rejectFirst = false
        await route.fulfill({
          status: 422,
          contentType: 'application/json',
          body: JSON.stringify({
            error: {
              code: 'validation',
              message: 'Nie udało się zapisać profilu. Spróbuj ponownie.',
              details: {},
            },
          }),
        })
      } else await route.continue()
    })
    await page.getByTestId('profile-add').click()
    await page.getByTestId('profile-name').fill(LONG_NAME)
    await page.getByTestId('profile-multiplier').fill('0,8')
    await page.getByTestId('profile-kcal').fill('1400')
    await page.getByTestId('profile-submit').click()
    await expect(page.getByTestId('profiles-error')).toBeVisible()
    await expect(page.getByTestId('profile-name')).toHaveValue(LONG_NAME)
    await expect(page.getByTestId('profile-multiplier')).toHaveValue('0,8')
    await expect(page.getByTestId('profile-kcal')).toHaveValue('1400')
    await page.getByTestId('settings-tab-family').focus()
    await page.keyboard.press('End')
    await expect(page.getByTestId('settings-tab-data')).toBeFocused()
    await expect(page.getByTestId('transfer-scope')).toBeVisible()
    await expect(page.getByTestId('transfer-ownership')).toContainText('Twojego konta')
    await page.keyboard.press('Home')
    await expect(page.getByTestId('profile-name')).toHaveValue(LONG_NAME)
    await page.getByTestId('profile-submit').click()
    const row = page.getByTestId(/^profile-row-/).filter({ hasText: LONG_NAME })
    await expect(row).toBeVisible()
    await row.getByTestId(/^profile-active-/).click()
    await expect(row).toContainText('Nieaktywny')
    await row.getByTestId(/^profile-active-/).click()
    await expect(row).toContainText('Aktywny')

    await page.getByTestId('settings-tab-family').focus()
    await page.keyboard.press('ArrowRight')
    await expect(page.getByTestId('settings-tab-goals')).toBeFocused()
    await expect(page.getByTestId('thresholds-form')).toBeVisible()
    await page.getByTestId('goal-valid-from').fill('2039-04-01')
    await page.getByTestId('goal-kcal').fill('2100')
    await page.getByTestId('goal-protein').fill('100,5')
    await page.getByTestId('goal-submit').click()
    await expect(page.getByTestId('goal-saved')).toBeVisible()
    await expect(page.getByTestId('goals-list')).toContainText('2039-04-01')
    await page.getByTestId('threshold-low').fill('85')
    await page.getByTestId('threshold-high').fill('115')
    await page.getByTestId('thresholds-submit').click()
    await expect(page.getByTestId('thresholds-saved')).toBeVisible()
    await page.reload()
    await page.getByTestId('settings-tab-goals').click()
    await expect(page.getByTestId('threshold-low')).toHaveValue('85')
    await expect(page.getByTestId('threshold-high')).toHaveValue('115')
    await expect(page.getByTestId('goals-list')).toContainText('2100')

    for (const width of [390, 1024]) {
      await page.setViewportSize({ width, height: 900 })
      for (const section of ['family', 'goals', 'shopping', 'data']) {
        if (section === 'shopping') shoppingOpened = true
        await page.getByTestId(`settings-tab-${section}`).click()
        if (section === 'shopping') {
          await expect(page.getByTestId('round-configs-list')).toBeVisible()
          await expect(page.getByTestId('stores-section')).toBeVisible()
        }
        const geometry = await page.locator('html').evaluate((element) => {
          const html = element as unknown as { scrollWidth: number; clientWidth: number }
          return { content: html.scrollWidth, viewport: html.clientWidth }
        })
        expect(geometry.content).toBeLessThanOrEqual(geometry.viewport + 1)
        await page.screenshot({
          path: testInfo.outputPath(`ux10-settings-${section}-${width}.png`),
          fullPage: true,
        })
      }
    }
    expect(roundReads).toBeGreaterThan(0)
    await page.getByTestId('settings-tab-family').click()
    await row.getByTestId(/^profile-delete-/).click()
    await expect(row).toHaveCount(0)
    await page.getByTestId('settings-tab-goals').click()
    await page.getByTestId(/^goal-delete-/).click()
    await expect(page.getByTestId('goals-list')).toHaveCount(0)
  } finally {
    try {
      if (context && authenticated) {
        const headers = await csrfHeaders(context.request)
        // Only this fresh household/account can be affected by this cleanup.
        const profiles = await context.request.get(`${API}/households/my/profiles`)
        if (profiles.ok())
          for (const profile of (
            (await profiles.json()) as components['schemas']['MemberProfileListResponse']
          ).items) {
            expect(profile.household_id).toBe(householdId)
            expect
              .soft(
                (
                  await context.request.delete(`${API}/households/my/profiles/${profile.id}`, {
                    headers,
                  })
                ).status(),
              )
              .toBe(204)
          }
        const goals = await context.request.get(`${API}/goals`)
        if (goals.ok())
          for (const goal of ((await goals.json()) as components['schemas']['GoalListResponse'])
            .items)
            expect
              .soft((await context.request.delete(`${API}/goals/${goal.id}`, { headers })).status())
              .toBe(204)
        // First GET in Shopping creates defaults; never query it for cleanup if
        // Shopping was not reached, because that would itself create data.
        const rounds = shoppingOpened
          ? await context.request.get(`${API}/shopping/round-configs`)
          : null
        if (rounds?.ok())
          for (const round of (
            (await rounds.json()) as components['schemas']['RoundConfigListResponse']
          ).items) {
            expect(round.household_id).toBe(householdId)
            expect
              .soft(
                (
                  await context.request.delete(`${API}/shopping/round-configs/${round.id}`, {
                    headers,
                  })
                ).status(),
              )
              .toBe(204)
          }
      }
    } finally {
      await context?.close()
      if (householdId !== undefined) {
        expect
          .soft(
            (
              await admin.put(`${API}/admin/households/${householdId}/members`, {
                headers: adminHeaders,
                data: { user_ids: [] },
              })
            ).status(),
          )
          .toBe(200)
        expect
          .soft(
            (
              await admin.delete(`${API}/admin/households/${householdId}`, {
                headers: adminHeaders,
              })
            ).status(),
          )
          .toBe(204)
      }
      if (userId !== undefined)
        expect
          .soft(
            (
              await admin.delete(`${API}/admin/users/${userId}`, { headers: adminHeaders })
            ).status(),
          )
          .toBe(204)
    }
  }
})
