import { createHash } from 'node:crypto'
import fs from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

import { expect, type BrowserContext, type Page, type TestInfo } from '@playwright/test'

import type { components } from '../src/api/generated.js'
import { reserveLoginAttempt } from './login-budget.js'
import { fillSecretPassword } from './secret-password.js'
import { PwaApi } from './ux-pwa-native-api.js'

export const prefix = 'UX00 kontrakty v1'
export const fixtureDay = '2029-06-04'
export type ListDetail = components['schemas']['ShoppingListDetailRead']
export type Household = components['schemas']['HouseholdDetail']

export async function fixture(baseURL: string | undefined) {
  const url = baseURL ? new URL(baseURL) : null
  if (
    !url ||
    !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) ||
    url.protocol !== 'http:' ||
    url.port !== '5173' ||
    url.pathname !== '/' ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  ) {
    throw new Error('Zaawansowany PWA wymaga lokalnego preview na porcie 5173.')
  }
  const password = process.env.UX_BASELINE_PASSWORD
  if (!password) throw new Error('Brak UX_BASELINE_PASSWORD.')
  const manifestPath =
    process.env.UX_BASELINE_MANIFEST ??
    fileURLToPath(new URL('../../backend/data/ux-baseline/manifest.json', import.meta.url))
  // Lokalny format fixture; odpowiedzi API niżej mają wyłącznie generowane typy.
  const manifest: {
    version: number
    prefix: string
    complete: boolean
    ids: Record<string, number>
  } = JSON.parse(await fs.readFile(manifestPath, 'utf8'))
  if (manifest.version !== 1 || manifest.prefix !== prefix || manifest.complete !== true) {
    throw new Error('Wymagany istniejący, ukończony fixture UX00 v1; test nie tworzy danych.')
  }
  const id = (key: string): number => {
    const value = manifest.ids[key]
    if (!Number.isSafeInteger(value) || value <= 0) throw new Error(`Brak ID UX00: ${key}.`)
    return value
  }
  const data = {
    baseURL: url.origin,
    password,
    a1: id('user-a1'),
    a2: id('user-a2'),
    b1: id('user-b1'),
    householdA: id('household-a'),
    householdB: id('household-b'),
    listId: id('list-plain'),
    generationId: id('generation-plain'),
    dayId: id('day-0'),
    mealId: id('meal-0'),
  }
  if (new Set([data.a1, data.a2, data.b1]).size !== 3 || data.householdA === data.householdB) {
    throw new Error('Kolizja identyfikatorów fixture UX00.')
  }
  return data
}

export type Fixture = Awaited<ReturnType<typeof fixture>>

export async function actualUser(
  context: BrowserContext,
  account: 'a1' | 'a2' | 'b1',
  data: Fixture,
  householdId = account === 'b1' ? data.householdB : data.householdA,
): Promise<void> {
  // Native transport bypasses SW/cache without a credential-bearing HTTP step.
  const response = await new PwaApi(context, data.baseURL).get('/api/v1/auth/me')
  expect(response.status(), 'Backend potwierdza rzeczywistą sesję').toBe(200)
  const me: components['schemas']['CurrentUser'] = await response.json()
  expect(
    me.id === data[account] &&
      me.email === `ux00-${account}@example.com` &&
      me.display_name === `${prefix} — konto ${account.toUpperCase()}` &&
      me.role === 'user' &&
      me.household?.id === householdId,
    'Konto i rodzina zgadzają się z markerami fixture',
  ).toBe(true)
}

export async function login(
  page: Page,
  account: 'a1' | 'a2' | 'b1',
  data: Fixture,
  testInfo: TestInfo,
): Promise<void> {
  await page.goto('/login')
  await page.getByTestId('login-email').fill(`ux00-${account}@example.com`)
  await fillSecretPassword(page.getByTestId('login-password'), data.password)
  await reserveLoginAttempt(data.baseURL, testInfo)
  const response = page.waitForResponse(
    (entry) =>
      new URL(entry.url()).pathname === '/api/v1/auth/login' && entry.request().method() === 'POST',
  )
  await page.getByTestId('login-submit').click()
  expect((await response).status(), 'Logowanie bez ponawiania prób').toBe(200)
  await expect(page).toHaveURL(/\/plan-dnia/)
  await expect(page.getByTestId('plan-dnia-page')).toBeVisible()
  await actualUser(page.context(), account, data)
}

export async function logout(page: Page): Promise<void> {
  await page.getByTestId('account-toggle').click()
  const response = page.waitForResponse(
    (entry) =>
      new URL(entry.url()).pathname === '/api/v1/auth/logout' &&
      entry.request().method() === 'POST',
  )
  await page.getByTestId('logout-button').click()
  expect((await response).status(), 'Backend kończy sesję A').toBe(204)
  await expect(page.getByTestId('login-submit')).toBeVisible()
}

export async function actualList(context: BrowserContext, data: Fixture): Promise<ListDetail> {
  const response = await new PwaApi(context, data.baseURL).get(
    `/api/v1/shopping/lists/${data.listId}`,
  )
  expect(response.status(), 'Prawdziwa lista fixture dostępna dla A').toBe(200)
  const list: ListDetail = await response.json()
  expect(
    list.id === data.listId &&
      list.generation_id === data.generationId &&
      list.name === `${prefix} — lista offline` &&
      list.sections.flatMap((section) => section.items).length > 0,
    'Lista odpowiada manifestowi UX00',
  ).toBe(true)
  return list
}

export async function listContents(page: Page, list: ListDetail): Promise<void> {
  await expect(page.getByTestId('lista-zakupowa-page')).toBeVisible()
  await expect(page.getByTestId('lista-nazwa')).toHaveText(list.name)
  const items = list.sections.flatMap((section) => section.items)
  await expect(page.locator('[data-testid^="shopping-item-"]')).toHaveCount(items.length)
  for (const item of items) {
    await expect(page.getByTestId(`shopping-label-${item.id}`)).toHaveText(item.label)
  }
}

export async function controlled(page: Page, script = '/sw-private-v1.js'): Promise<void> {
  await page.waitForFunction(
    `navigator.serviceWorker.controller?.state === 'activated' &&
      new URL(navigator.serviceWorker.controller.scriptURL).pathname === ${JSON.stringify(script)}`,
    undefined,
    { timeout: 30_000 },
  )
  expect(
    await page.evaluate(`Array.from(document.scripts, script => script.src)
      .some(url => url.includes('/@vite/client'))`),
    'Wymagany rzeczywisty build bez klienta Vite',
  ).toBe(false)
}

export async function warmPrivate(page: Page, list: ListDetail, worker?: string): Promise<void> {
  const loaded = () =>
    page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === `/api/v1/shopping/lists/${list.id}` &&
        response.request().method() === 'GET',
    )
  const opened = loaded()
  await page.goto(`/zakupy/listy/${list.id}`)
  expect((await opened).status()).toBe(200)
  await listContents(page, list)
  await page.waitForFunction('navigator.serviceWorker.ready.then(r => r.active !== null)')
  const reloaded = loaded()
  await page.reload()
  expect((await reloaded).status()).toBe(200)
  await controlled(page, worker)
  await listContents(page, list)
  await hydrationBarrier(page)
}

/** Read-only data; the empty transaction waits behind any earlier hydration writes. */
export async function hydrationBarrier(page: Page): Promise<void> {
  await page.evaluate(`(async () => {
    await new Promise((resolve, reject) => {
      const opening = indexedDB.open('pasnik-offline');
      opening.onupgradeneeded = () => {
        opening.transaction.abort();
        reject(new Error('Brak istniejącej bazy offline.'));
      };
      opening.onerror = () => reject(new Error('Odczyt IDB nie powiódł się.'));
      opening.onsuccess = () => {
        const database = opening.result;
        const stores = Array.from(database.objectStoreNames);
        if (!stores.length) { database.close(); reject(new Error('Brak magazynów IDB.')); return; }
        const barrier = database.transaction(stores, 'readwrite');
        barrier.oncomplete = () => { database.close(); resolve(); };
        barrier.onerror = barrier.onabort = () => {
          database.close(); reject(new Error('Bariera IDB nie powiodła się.'));
        };
      };
    });
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  })()`)
}

export function listMarkers(list: ListDetail) {
  return [
    { selector: '[data-testid="lista-nazwa"]', text: list.name },
    ...list.sections.flatMap((section) =>
      section.items.map((item) => ({ selector: `[data-testid="shopping-item-${item.id}"]` })),
    ),
  ]
}

/** Never reports a payload, token, cookie, URL, or even the observed text. */
export async function privateObserver(page: Page, markers: { selector: string; text?: string }[]) {
  let presentations = 0
  await page.exposeBinding('__uxAdvancedPresented', () => {
    presentations += 1
  })
  const observation = (armed: boolean) => `(() => {
    const markers = ${JSON.stringify(markers)};
    const state = window.__uxAdvancedAudit = { armed: ${armed}, seen: false, checks: 0 };
    const inspect = () => {
      if (!state.armed) return;
      state.checks += 1;
      if (state.seen) return;
      const shown = markers.some(marker => Array.from(document.querySelectorAll(marker.selector))
        .some(node => node.getClientRects().length > 0 &&
          getComputedStyle(node).visibility !== 'hidden' &&
          getComputedStyle(node).display !== 'none' &&
          (marker.text === undefined || node.textContent.trim() === marker.text)));
      if (shown) { state.seen = true; void window.__uxAdvancedPresented(); }
    };
    state.inspect = inspect;
    new MutationObserver(inspect).observe(document,
      { subtree: true, childList: true, attributes: true, characterData: true });
    const frame = () => { inspect(); requestAnimationFrame(frame); };
    requestAnimationFrame(frame);
    inspect();
  })()`
  await page.evaluate(observation(false))
  return {
    async arm(inspectCurrent = true) {
      // Caller first confirms logout + login UI in the OTHER tab, or cold /me.
      // Do not inspect synchronously inside the application's storage event:
      // Vue must finish its legitimate DOM patch before this boundary.
      await page.addInitScript(observation(true))
      if (!inspectCurrent) return
      await page.evaluate(`(() => {
        window.__uxAdvancedAudit.armed = true;
        window.__uxAdvancedAudit.inspect();
      })()`)
    },
    async assertClean() {
      await page.evaluate(`new Promise(resolve =>
        requestAnimationFrame(() => requestAnimationFrame(resolve)))`)
      expect(
        await page.evaluate(`(() => {
          const state = window.__uxAdvancedAudit;
          state.inspect();
          return state.armed && state.checks > 0 && state.seen === false;
        })()`),
        'Observer obejmuje granicę sesji i nie wykrył nawet chwilowego renderu A',
      ).toBe(true)
      expect(presentations, 'Liczba prezentacji prywatnych danych A po zamknięciu sesji').toBe(0)
    },
  }
}

export async function unavailable(page: Page): Promise<void> {
  const terminal = page.getByTestId('lista-zakupowa-brak').or(page.getByRole('alert')).first()
  await expect(terminal).toBeVisible({ timeout: 30_000 })
  await hydrationBarrier(page)
  await expect(terminal).toBeVisible()
  await expect(page.getByTestId('lista-nazwa')).toHaveCount(0)
  await expect(page.locator('[data-testid^="shopping-item-"]')).toHaveCount(0)
  await expect(page.getByTestId('login-submit')).toHaveCount(0)
}

export async function spaList(page: Page, id: number): Promise<void> {
  await page.evaluate(`(() => {
    history.pushState(null, '', ${JSON.stringify(`/zakupy/listy/${id}`)});
    dispatchEvent(new PopStateEvent('popstate', { state: history.state }));
  })()`)
}

/** A real failed /me, independent of Chromium's sometimes-stale navigator.onLine. */
export async function offlineReload(page: Page): Promise<void> {
  const failed = page.waitForEvent('requestfailed', {
    predicate: (request) => new URL(request.url()).pathname === '/api/v1/auth/me',
    timeout: 30_000,
  })
  await page.reload()
  expect((await failed).failure() !== null, 'Cold /me kończy rzeczywisty błąd transportu').toBe(
    true,
  )
}

export async function credentialFingerprint(context: BrowserContext): Promise<string> {
  const cookies = (await context.cookies()).filter((cookie) =>
    ['pasnik_session', '__Host-pasnik_session', 'csrf_token', '__Host-csrf_token'].includes(
      cookie.name,
    ),
  )
  expect(cookies.length, 'Sesja ma cookie sesyjne i CSRF').toBe(2)
  return createHash('sha256')
    .update(JSON.stringify(cookies.map(({ name, value }) => [name, value]).sort()))
    .digest('hex')
}

export async function closeOnline(context: BrowserContext): Promise<void> {
  try {
    await context.setOffline(false)
  } finally {
    await context.close()
  }
}

export function safeFailure(error: unknown, secrets: string[]): string {
  let message = error instanceof Error ? error.message : 'Nieznany błąd.'
  for (const secret of secrets.filter(Boolean))
    message = message.replaceAll(secret, '[local-secret]')
  return message
    .replace(/(?:https?:\/\/|\/api\/v1\/public\/lists\/|\/l\/)[^\s"'<>]+/g, '[redacted-url]')
    .replace(/(?:__Host-)?(?:pasnik_session|csrf_token)[^\s,;]*/g, '[credential]')
    .replace(/[A-Za-z0-9_-]{43,}/g, '[token-shaped-value]')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 7)
    .join(' ')
    .slice(0, 1000)
}
