import { setTimeout as delay } from 'node:timers/promises'

import { expect, test, type BrowserContext } from '@playwright/test'

import type { components } from '../src/api/generated.js'
import { EMPTY_STATE } from './auth-state.js'
import { reserveLoginAttempt } from './login-budget.js'
import { PwaApi, type PwaResponse } from './ux-pwa-native-api.js'
import {
  actualList,
  actualUser,
  closeOnline,
  controlled,
  credentialFingerprint,
  fixture,
  fixtureDay,
  hydrationBarrier,
  listContents,
  listMarkers,
  login,
  logout,
  offlineReload,
  prefix,
  privateObserver,
  safeFailure,
  spaList,
  unavailable,
  warmPrivate,
  type Fixture,
  type Household,
} from './ux-pwa-advanced-helpers.js'

// Dedicated sequential invocation after preview, with --project chromium --no-deps.
// UX_PWA alone (including the existing test-pwa task) never opts into these tests.
test.use({ storageState: EMPTY_STATE, trace: 'off', video: 'off', screenshot: 'off' })
test.describe.configure({ timeout: 300_000, retries: 0 })
test.skip(
  process.env.UX_PWA_ADVANCED !== '1',
  'Wymaga UX_PWA_ADVANCED=1 i rezerwacji runtime UX00.',
)

for (const view of ['list', 'plan'] as const) {
  test(`UX06 PWA: dwie karty, otwarty ${view}, logout A → B i spóźniony prawdziwy GET A`, async ({
    browser,
    baseURL,
  }, testInfo) => {
    const data = await fixture(baseURL)
    const context = await browser.newContext({ baseURL: data.baseURL, storageState: EMPTY_STATE })
    const api = new PwaApi(context, data.baseURL)
    let release = () => {}
    let stage = 'login-a1'
    try {
      const stalePage = await context.newPage()
      await login(stalePage, 'a1', data, testInfo)
      const list = await actualList(context, data)
      let markers = listMarkers(list)
      let apiPath = `/api/v1/shopping/lists/${list.id}`
      let validateLate = async (response: PwaResponse) => {
        const payload: components['schemas']['ShoppingListDetailRead'] = await response.json()
        expect(payload.id === list.id && payload.name === list.name, 'Oryginalny payload A').toBe(
          true,
        )
      }
      if (view === 'list') {
        await warmPrivate(stalePage, list)
      } else {
        stage = 'plan-fixture-preconditions'
        const response = await api.get(`/api/v1/plan/days/${fixtureDay}`)
        expect(response.status()).toBe(200)
        const day: components['schemas']['DayRead'] = await response.json()
        expect(day.id === data.dayId, 'Plan: ID dnia zgadza się z manifestem UX00').toBe(true)
        expect(
          day.title === `${prefix} — bez podziału`,
          'Plan: tytuł ma dokładny marker fixture UX00',
        ).toBe(true)
        expect(day.owner_user_id === data.a1, 'Plan: właścicielem jest A1 z manifestu').toBe(true)
        expect(day.scope === 'household', 'Plan: zakres pozostaje rodzinny').toBe(true)
        expect(
          day.meals.some((meal) => meal.id === data.mealId),
          'Plan: ID posiłku zgadza się z manifestem UX00',
        ).toBe(true)
        markers = [
          { selector: '[data-testid="plan-dnia-page"] p', text: day.title ?? '' },
          ...day.meals.map((meal) => ({ selector: `[data-testid="meal-card-${meal.id}"]` })),
        ]
        apiPath = '/api/v1/plan/days'
        validateLate = async (late) => {
          const payload: components['schemas']['DaysResponse'] = await late.json()
          expect(
            payload.items.some((item) => item.id === day.id && item.title === day.title),
            'Opóźniona odpowiedź rzeczywiście pochodzi z planu A',
          ).toBe(true)
        }
        await stalePage.goto(`/plan-dnia/${fixtureDay}`)
        await expect(stalePage.getByTestId(`meal-card-${data.mealId}`)).toBeVisible()
        await stalePage.reload()
        await controlled(stalePage)
        await expect(stalePage.getByTestId(`meal-card-${data.mealId}`)).toBeVisible()
      }

      const controlPage = await context.newPage()
      await controlPage.goto('/plan-dnia')
      await expect(controlPage.getByTestId('plan-dnia-page')).toBeVisible()
      const audit = await privateObserver(stalePage, markers)
      stage = 'real-a-refetch-in-flight'
      let fetched: (error?: unknown) => void = () => {}
      const fetchedResponse = new Promise<unknown>((resolve) => {
        fetched = resolve
      })
      const gate = new Promise<void>((resolve) => {
        release = resolve
      })
      let delivered: (error?: unknown) => void = () => {}
      const deliveredResponse = new Promise<unknown>((resolve) => {
        delivered = resolve
      })
      await stalePage.route(
        (url) => url.pathname === apiPath,
        async (route) => {
          try {
            expect(route.request().method(), 'Odkładamy rzeczywisty odczyt A').toBe('GET')
            // Native HTTP has the context's actual cookies and no credential-
            // bearing route.fetch step. Hold the real status/headers/body bytes.
            const response = await api.get(route.request().url(), { timeout: 15_000 })
            expect(response.status(), 'Opóźniamy wyłącznie prawdziwy udany GET A').toBe(200)
            await validateLate(response)
            fetched()
            await gate
            await route.fulfill(response.fulfillOptions())
            delivered()
          } catch (error) {
            fetched(error)
            delivered(error)
          }
        },
        { times: 1 },
      )
      // With networkMode:'always', reconnect does not refetch by default.
      // Let the real 30s staleTime expire, then remount through UI/history in
      // the same SPA document. The existing client/cache must retain A while
      // refetchOnMount sends its real second GET. No query internals or mocks.
      await delay(31_000)
      const previousPath = new URL(stalePage.url()).pathname
      const documentMarker = await stalePage.evaluate(
        'window.__uxAdvancedSpaDocument = crypto.randomUUID()',
      )
      const recipesNavigation = stalePage
        .locator(
          '[data-testid="nav-item-przepisy"]:visible, [data-testid="nav-bottom-przepisy"]:visible',
        )
        .first()
      await expect(recipesNavigation).toBeVisible()
      await recipesNavigation.click()
      await expect(stalePage.getByTestId('przepisy-page')).toBeVisible()
      await expect(
        stalePage.getByTestId(view === 'list' ? 'lista-zakupowa-page' : 'plan-dnia-page'),
        'Pomocnicza nawigacja odmontowała poprzedni widok A',
      ).toHaveCount(0)
      await stalePage.goBack()
      expect(
        await stalePage.evaluate(`window.__uxAdvancedSpaDocument === ${JSON.stringify(documentMarker)} &&
          location.pathname === ${JSON.stringify(previousPath)}`),
        'Powrót do A zachował dokument SPA i istniejący cache klienta',
      ).toBe(true)
      expect(
        await Promise.race([
          fetchedResponse,
          delay(30_000).then(() => new Error('Brak rzeczywistego refetchu otwartego widoku A.')),
        ]),
        'Zarejestrowany prawdziwy GET A przed zmianą sesji',
      ).toBeUndefined()
      if (view === 'list') await listContents(stalePage, list)
      else await expect(stalePage.getByTestId(`meal-card-${data.mealId}`)).toBeVisible()

      stage = 'logout-other-tab'
      await logout(controlPage)
      await audit.arm()
      await audit.assertClean()
      await expect(
        stalePage.getByTestId(view === 'list' ? 'lista-zakupowa-page' : 'plan-dnia-page'),
        'Zamknięty chroniony widok starej karty, nie tylko wyczyszczony QueryClient',
      ).toHaveCount(0)
      stage = 'login-b1-other-tab'
      await login(controlPage, 'b1', data, testInfo)
      await actualUser(context, 'b1', data)
      const denied = await api.get(`/api/v1/shopping/lists/${data.listId}`)
      expect(denied.status(), 'Backend odmawia B1 listy A').toBe(404)
      stage = 'late-a-delivery'
      const receivedLate = stalePage.waitForResponse(
        (response) =>
          new URL(response.url()).pathname === apiPath &&
          response.request().method() === 'GET' &&
          response.status() === 200,
      )
      release()
      expect(
        await deliveredResponse,
        'Dostarczono oryginalną odpowiedź A po actual /me B',
      ).toBeUndefined()
      expect(
        await (await receivedLate).finished(),
        'Przeglądarka odebrała całe stare body A',
      ).toBeNull()
      await audit.assertClean()
      await hydrationBarrier(stalePage)
      await audit.assertClean()

      // The old tab must stay clean even after its own cold bootstrap as B.
      stage = 'old-tab-cold-b'
      await stalePage.goto('/plan-dnia')
      await controlled(stalePage)
      await expect(stalePage.getByTestId('plan-dnia-page')).toBeVisible()
      await actualUser(context, 'b1', data)
      await audit.assertClean()
      stage = 'old-tab-offline-private'
      await context.setOffline(true)
      await spaList(stalePage, list.id)
      await unavailable(stalePage)
      await audit.assertClean()
      await offlineReload(stalePage)
      await controlled(stalePage)
      await unavailable(stalePage)
      await audit.assertClean()
    } catch (error) {
      // eslint-disable-next-line preserve-caught-error
      throw new Error(`Dwie karty ${view}, etap ${stage}: ${safeFailure(error, [data.password])}`)
    } finally {
      release()
      await closeOnline(context)
    }
  })
}

function memberIds(household: Household): number[] {
  return household.members.map((member) => member.id).sort((left, right) => left - right)
}

async function readHousehold(admin: PwaApi, id: number): Promise<Household> {
  const response = await admin.get(`/api/v1/admin/households/${id}`)
  if (response.status() !== 200) {
    throw new Error(`API nie pozwala odczytać składu rodziny fixture: HTTP ${response.status()}.`)
  }
  return response.json()
}

function validateHousehold(household: Household, data: Fixture, side: 'A' | 'B'): void {
  const id = side === 'A' ? data.householdA : data.householdB
  if (household.id !== id || household.name !== `${prefix} — Dom ${side}`) {
    throw new Error('Nie zgadza się ID lub marker nazwy rodziny UX00; bez mutacji.')
  }
  const allowed = new Set([data.a1, data.a2, data.b1])
  if (household.members.some((member) => !allowed.has(member.id))) {
    throw new Error('Rodzina zawiera konto spoza trzech dozwolonych kont UX00; bez mutacji.')
  }
}

async function putMembers(admin: PwaApi, id: number, ids: number[]): Promise<void> {
  const response = await admin.put(`/api/v1/admin/households/${id}/members`, {
    data: { user_ids: ids },
  })
  if (response.status() !== 200) {
    throw new Error(
      `API nie pozwala bezpiecznie zmienić składu fixture: HTTP ${response.status()}.`,
    )
  }
}

async function restoreMembers(
  admin: PwaApi,
  data: Fixture,
  original: { a: Household; b: Household },
  secrets: string[],
): Promise<void> {
  // Recheck IDs/names and the allowlist before restoring the exact sets.
  // No broad cleanup, account edits, or household creation/deletion.
  const currentA = await readHousehold(admin, data.householdA)
  const currentB = await readHousehold(admin, data.householdB)
  validateHousehold(currentA, data, 'A')
  validateHousehold(currentB, data, 'B')
  const failures: string[] = []
  for (const household of [original.b, original.a]) {
    try {
      await putMembers(admin, household.id, memberIds(household))
    } catch (error) {
      failures.push(safeFailure(error, secrets))
    }
  }
  // Check both households even if one restore or verification fails.
  for (const household of [original.a, original.b]) {
    try {
      const restored = await readHousehold(admin, household.id)
      validateHousehold(restored, data, household.id === data.householdA ? 'A' : 'B')
      expect(memberIds(restored), 'Przywrócono dokładny skład rodziny fixture').toEqual(
        memberIds(household),
      )
    } catch (error) {
      failures.push(safeFailure(error, secrets))
    }
  }
  if (failures.length) throw new Error(`Przywrócenie fixture nieudane: ${failures.join(' ')}`)
}

test('UX06 PWA: potwierdzona zmiana rodziny A2 przy niezmienionych cookies izoluje snapshot', async ({
  browser,
  baseURL,
}, testInfo) => {
  const data = await fixture(baseURL)
  const email = process.env.E2E_ADMIN_EMAIL
  const password = process.env.E2E_ADMIN_PASSWORD
  if (!email || !password)
    throw new Error('Brak E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD z auth.setup.ts.')
  const context = await browser.newContext({ baseURL: data.baseURL, storageState: EMPTY_STATE })
  const api = new PwaApi(context, data.baseURL)
  let admin: BrowserContext | undefined
  let adminApi: PwaApi | undefined
  let original: { a: Household; b: Household } | undefined
  let mutationAttempted = false
  let stage = 'fixture-preconditions'
  const failures: string[] = []
  try {
    admin = await browser.newContext({ baseURL: data.baseURL, storageState: EMPTY_STATE })
    adminApi = new PwaApi(admin, data.baseURL)
    await reserveLoginAttempt(data.baseURL, testInfo)
    const logged = await adminApi.post('/api/v1/auth/login', { data: { email, password } })
    expect(logged.status(), 'Jedna rzeczywista próba logowania administratora').toBe(200)
    const meResponse = await adminApi.get('/api/v1/auth/me')
    expect(meResponse.status()).toBe(200)
    const me: components['schemas']['CurrentUser'] = await meResponse.json()
    expect(me.role === 'admin' && me.email === email, 'Potwierdzony ADMIN z env').toBe(true)
    const a = await readHousehold(adminApi, data.householdA)
    const b = await readHousehold(adminApi, data.householdB)
    validateHousehold(a, data, 'A')
    validateHousehold(b, data, 'B')
    expect(memberIds(a), 'Dokładny początkowy skład DomA fixture').toEqual(
      [data.a1, data.a2].sort((x, y) => x - y),
    )
    expect(memberIds(b), 'Dokładny początkowy skład DomB fixture').toEqual([data.b1])
    for (const account of ['a1', 'a2', 'b1'] as const) {
      const response = await adminApi.get(`/api/v1/admin/users/${data[account]}`)
      expect(response.status()).toBe(200)
      const user: components['schemas']['UserRead'] = await response.json()
      expect(
        user.id === data[account] &&
          user.display_name === `${prefix} — konto ${account.toUpperCase()}` &&
          user.email === `ux00-${account}@example.com` &&
          user.role === 'user' &&
          user.is_active,
        'Marker, ID i aktywność dozwolonego konta fixture',
      ).toBe(true)
    }
    original = { a, b }
    const page = await context.newPage()
    await login(page, 'a2', data, testInfo)
    const list = await actualList(context, data)
    const generationResponse = await api.get(`/api/v1/shopping/generations/${data.generationId}`)
    expect(generationResponse.status()).toBe(200)
    const generation: components['schemas']['GenerationRead'] = await generationResponse.json()
    expect(
      generation.id === data.generationId &&
        generation.scope === 'household' &&
        generation.household_id === data.householdA &&
        generation.owner_user_id === data.a1,
      'Lista pochodzi z rodzinnej generacji A1, A2 jest tylko członkiem DomA',
    ).toBe(true)
    await warmPrivate(page, list)
    const fingerprint = await credentialFingerprint(context)
    const audit = await privateObserver(page, listMarkers(list))
    stage = 'move-only-a2-to-dom-b'
    // Flag BEFORE sending: even a lost response may have committed the move.
    mutationAttempted = true
    await putMembers(adminApi, data.householdB, [...memberIds(b), data.a2])
    expect(memberIds(await readHousehold(adminApi, data.householdA))).toEqual([data.a1])
    expect(memberIds(await readHousehold(adminApi, data.householdB))).toEqual(
      [data.b1, data.a2].sort((x, y) => x - y),
    )
    expect(
      (await credentialFingerprint(context)) === fingerprint,
      'Przeniesienie nie zmienia cookie A2',
    ).toBe(true)

    stage = 'cold-online-me-a2-dom-b'
    // Observe the new document from its first DOM mutation; the old document
    // may legitimately show its last-confirmed family until it checks /me.
    await audit.arm(false)
    const confirmed = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === '/api/v1/auth/me' &&
        response.request().method() === 'GET',
    )
    await page.goto('/plan-dnia')
    const coldResponse = await confirmed
    expect(coldResponse.status()).toBe(200)
    const coldMe: components['schemas']['CurrentUser'] = await coldResponse.json()
    expect(
      coldMe.id === data.a2 && coldMe.household?.id === data.householdB,
      'Cold bootstrap potwierdził tego samego A2 w DomB',
    ).toBe(true)
    await expect(page.getByTestId('plan-dnia-page')).toBeVisible()
    await controlled(page)
    await actualUser(context, 'a2', data, data.householdB)
    expect(
      (await credentialFingerprint(context)) === fingerprint,
      'Cookie nadal niezmienione po cold /me',
    ).toBe(true)
    const denied = await api.get(`/api/v1/shopping/lists/${data.listId}`)
    expect(denied.status(), 'Backend odmawia A2 starej listy DomA').toBe(404)
    await audit.assertClean()
    stage = 'new-family-offline-old-list'
    await context.setOffline(true)
    await spaList(page, list.id)
    await unavailable(page)
    await audit.assertClean()
    await offlineReload(page)
    await controlled(page)
    await unavailable(page)
    await audit.assertClean()
  } catch (error) {
    failures.push(
      `Zmiana rodziny, etap ${stage}: ${safeFailure(error, [data.password, password, email])}`,
    )
  } finally {
    try {
      if (adminApi && original && mutationAttempted) {
        await restoreMembers(adminApi, data, original, [data.password, password, email])
      }
    } catch (error) {
      failures.push(
        `Przywrócenie rodzin fixture: ${safeFailure(error, [data.password, password, email])}`,
      )
    } finally {
      try {
        if (admin) await closeOnline(admin)
      } finally {
        await closeOnline(context)
      }
    }
  }
  if (failures.length) throw new Error(failures.join(' '))
})
