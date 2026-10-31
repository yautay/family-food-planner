import fs from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

import {
  expect,
  test,
  type BrowserContext,
  type Page,
  type Request,
  type TestInfo,
} from '@playwright/test'

import type { components } from '../src/api/generated.js'
import { EMPTY_STATE } from './auth-state.js'
import { reserveLoginAttempt } from './login-budget.js'
import { fillSecretPassword } from './secret-password.js'
import { PwaApi } from './ux-pwa-native-api.js'

const enabled = process.env.UX_PWA === '1'
const prefix = 'UX00 kontrakty v1'
const manifestPath =
  process.env.UX_BASELINE_MANIFEST ??
  fileURLToPath(new URL('../../backend/data/ux-baseline/manifest.json', import.meta.url))

type ListDetail = components['schemas']['ShoppingListDetailRead']
type PublicList = components['schemas']['PublicListRead']

test.use({ storageState: EMPTY_STATE, trace: 'off', video: 'off', screenshot: 'off' })
test.describe.configure({ timeout: 180_000, retries: 0 })
test.skip(!enabled, 'Wymaga UX_PWA=1, zbudowanego PWA i istniejącego fixture UX00.')

async function fixture(baseURL: string | undefined) {
  if (!baseURL || !['localhost', '127.0.0.1', '[::1]'].includes(new URL(baseURL).hostname)) {
    throw new Error('Preflight PWA jest dozwolony wyłącznie na localhost.')
  }
  const password = process.env.UX_BASELINE_PASSWORD
  if (!password) throw new Error('Brak lokalnego UX_BASELINE_PASSWORD.')
  // Format pliku lokalnego narzędzia, nie odpowiedź API. Nie tworzymy ani nie resetujemy danych.
  const manifest: { prefix: string; complete: boolean; ids: Record<string, number> } = JSON.parse(
    await fs.readFile(manifestPath, 'utf8'),
  )
  if (manifest.prefix !== prefix || manifest.complete !== true) {
    throw new Error('Wymagany ukończony i zweryfikowany zestaw UX00.')
  }
  const id = (key: string): number => {
    const value = manifest.ids[key]
    if (!Number.isSafeInteger(value) || value <= 0) throw new Error(`Brak ID UX00: ${key}`)
    return value
  }
  return { baseURL, password, a1: id('user-a1'), b1: id('user-b1'), listId: id('list-plain') }
}

async function login(
  page: Page,
  baseURL: string,
  password: string,
  account: 'a1' | 'b1',
  userId: number,
  testInfo: TestInfo,
): Promise<void> {
  await page.goto('/login')
  await page.getByTestId('login-email').fill(`ux00-${account}@example.com`)
  await fillSecretPassword(page.getByTestId('login-password'), password)
  await reserveLoginAttempt(baseURL, testInfo)
  const response = page.waitForResponse(
    (entry) =>
      new URL(entry.url()).pathname === '/api/v1/auth/login' && entry.request().method() === 'POST',
  )
  await page.getByTestId('login-submit').click()
  expect((await response).status(), 'Rzeczywiste logowanie, bez ponowień').toBe(200)
  await expect(page).toHaveURL(/\/plan-dnia/)
  await actualUser(page.context(), userId, baseURL)
}

async function actualUser(context: BrowserContext, userId: number, baseURL: string): Promise<void> {
  // Native transport bypasses SW/cache without a credential-bearing HTTP step.
  const response = await new PwaApi(context, baseURL).get('/api/v1/auth/me')
  expect(response.status(), 'Rzeczywista sesja backendu').toBe(200)
  const me: components['schemas']['CurrentUser'] = await response.json()
  expect(me.id).toBe(userId)
}

async function actualList(
  context: BrowserContext,
  listId: number,
  baseURL: string,
): Promise<ListDetail> {
  const response = await new PwaApi(context, baseURL).get(`/api/v1/shopping/lists/${listId}`)
  expect(response.status(), 'Rzeczywisty prywatny odczyt A1').toBe(200)
  const list: ListDetail = await response.json()
  expect(list.name).toBe(`${prefix} — lista offline`)
  expect(list.sections.flatMap((section) => section.items).length).toBeGreaterThan(0)
  return list
}

async function privateContents(page: Page, list: ListDetail): Promise<void> {
  await expect(page.getByTestId('lista-zakupowa-page')).toBeVisible()
  await expect(page.getByTestId('lista-nazwa')).toHaveText(list.name)
  const items = list.sections.flatMap((section) => section.items)
  await expect(page.locator('[data-testid^="shopping-item-"]')).toHaveCount(items.length)
  for (const item of items) {
    await expect(page.getByTestId(`shopping-label-${item.id}`)).toHaveText(item.label)
    await expect(page.getByTestId(`shopping-check-${item.id}`)).toBeChecked({
      checked: item.checked,
    })
  }
  await expect(page.getByTestId('login-submit')).toHaveCount(0)
  await expect(page.getByRole('alert')).toHaveCount(0)
}

async function builtPwa(page: Page): Promise<void> {
  // tsconfig.node nie ma DOM: te skrypty wykonują się wyłącznie w przeglądarce.
  expect(
    await page.evaluate(`[
      ...Array.from(document.scripts, script => script.src),
      ...performance.getEntriesByType('resource').map(entry => entry.name),
    ].filter(url => url.includes('/@vite/client')).length`),
    'Build PWA nie może ładować klienta Vite',
  ).toBe(0)
  await page.waitForFunction(
    `navigator.serviceWorker.ready.then(registration => registration.active?.state === 'activated')`,
    undefined,
    { timeout: 30_000 },
  )
}

async function controlled(page: Page): Promise<void> {
  await page.waitForFunction('navigator.serviceWorker.controller !== null', undefined, {
    timeout: 30_000,
  })
}

async function warmPrivate(page: Page, list: ListDetail): Promise<void> {
  const apiPath = `/api/v1/shopping/lists/${list.id}`
  const loaded = () =>
    page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === apiPath && response.request().method() === 'GET',
    )
  const first = loaded()
  await page.goto(`/zakupy/listy/${list.id}`)
  expect((await first).status()).toBe(200)
  await privateContents(page, list)
  await builtPwa(page)
  const reloaded = loaded()
  await page.reload()
  expect((await reloaded).status()).toBe(200)
  await controlled(page)
  await privateContents(page, list)
}

async function closeOnline(context: BrowserContext): Promise<void> {
  try {
    await context.setOffline(false)
  } finally {
    await context.close()
  }
}

function safeFailure(error: unknown, password: string): string {
  if (!(error instanceof Error)) return 'Nieznany błąd.'
  return error.message
    .replaceAll(password, '[local-secret]')
    .replace(/(?:https?:\/\/|\/api\/v1\/public\/lists\/|\/l\/)[^\s"'<>]+/g, '[public-url]')
    .replace(/[A-Za-z0-9_-]{43}/g, '[token-shaped-value]')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 7)
    .join(' ')
    .slice(0, 1000)
}

async function pageDiagnostics(page: Page | undefined, expectedName?: string): Promise<string> {
  if (!page || page.isClosed()) return '{"pageClosed":true}'
  try {
    // Wyłącznie klasy trasy, booleany i liczności; bez URL, tokenu, treści listy i PII.
    return JSON.stringify(
      await page.evaluate(`(() => {
        const count = selector => document.querySelectorAll(selector).length;
        const route = location.pathname.startsWith('/l/') ? 'public-list'
          : location.pathname.startsWith('/zakupy/listy/') ? 'private-list'
          : location.pathname === '/login' ? 'login'
          : location.pathname.startsWith('/plan-dnia') ? 'plan' : 'other';
        return {
          route,
          blank: !document.body?.textContent.trim(),
          online: navigator.onLine,
          controlled: navigator.serviceWorker.controller !== null,
          loginCount: count('[data-testid="login-submit"]'),
          alertCount: count('[role="alert"]'),
          privatePageCount: count('[data-testid="lista-zakupowa-page"]'),
          publicPageCount: count('[data-testid="public-list-page"]'),
          rowCount: count('[data-testid^="shopping-item-"]'),
          nameMatched: Array.from(document.querySelectorAll('[data-testid="lista-nazwa"]'))
            .some(node => node.textContent.trim() === ${JSON.stringify(expectedName ?? '')}),
          privateSeen: window.__uxPwaPrivateSeen === true,
          bannerCount: count('[data-testid="offline-banner"]'),
          bannerOffline: Array.from(document.querySelectorAll('[data-testid="offline-banner"]'))
            .some(node => node.textContent.includes('Tryb offline')),
        };
      })()`),
    )
  } catch {
    return '{"diagnosticsUnavailable":true}'
  }
}

test('UX06 PWA: prywatna lista A1 przeżywa prawdziwy restart offline', async ({
  browser,
  baseURL,
}, testInfo) => {
  const data = await fixture(baseURL)
  const context = await browser.newContext({ baseURL: data.baseURL, storageState: EMPTY_STATE })
  let diagnosticPage: Page | undefined
  let original: { id: number; checked: boolean } | undefined
  let mutationAttempted = false
  let stage = 'login-a1'
  const failures: string[] = []
  const inFlight = new Map<Request, { done: Promise<void>; finish: () => void }>()
  context.on('request', (request) => {
    if (
      !original ||
      request.method() !== 'PATCH' ||
      new URL(request.url()).pathname !==
        `/api/v1/shopping/lists/${data.listId}/items/${original.id}`
    )
      return
    let finish = () => {}
    const done = new Promise<void>((resolve) => {
      finish = resolve
    })
    inFlight.set(request, { done, finish })
  })
  const finishPatch = (request: Request) => {
    inFlight.get(request)?.finish()
    inFlight.delete(request)
  }
  context.on('requestfinished', finishPatch)
  context.on('requestfailed', finishPatch)
  const reopenOnline = async (page: Page) => {
    await test.step(
      'Ponowne otwarcie aplikacji online z zachowaną trwałą kolejką',
      async () => {
        // Playwright enables focus emulation, so bringToFront does not prove
        // a native focus transition. Reload exercises the documented startup
        // replay, preserving cookies, IndexedDB and the actual server session.
        if (original) await expect(page.getByTestId(`shopping-check-${original.id}`)).toBeEnabled()
        await page.reload({ timeout: 30_000 })
        await controlled(page)
        await expect(page.getByTestId('lista-zakupowa-page')).toBeVisible()
      },
      { timeout: 30_000 },
    )
  }
  const settleOwnItem = async (page: Page, itemId: number) => {
    await test.step(
      'Bariera trwałej kolejki i zakończenia PATCH własnej pozycji',
      async () => {
        // onSettled re-enables this input only after an earlier UI mutation
        // finishes its durable enqueue/forget. Do not navigate and abort replay.
        await expect(page.getByTestId(`shopping-check-${itemId}`)).toBeEnabled()
        const queueAbsent = () =>
          page.waitForFunction(
            `(async () => {
              return new Promise((resolve, reject) => {
                const opening = indexedDB.open('pasnik-offline');
                opening.onupgradeneeded = () => {
                  opening.transaction.abort();
                  reject(new Error('Brak istniejącej bazy kolejki PWA.'));
                };
                opening.onerror = () => reject(new Error('Odczyt kolejki PWA nie powiódł się.'));
                opening.onsuccess = () => {
                  const db = opening.result;
                  if (!db.objectStoreNames.contains('mutation-queue')) {
                    db.close(); reject(new Error('Brak istniejącego magazynu kolejki PWA.')); return;
                  }
                  // A readonly transaction waits behind earlier writes. Only
                  // this item's absence crosses into Node, never rows/keys/scope.
                  const transaction = db.transaction('mutation-queue', 'readonly');
                  const request = transaction.objectStore('mutation-queue').getAll();
                  transaction.oncomplete = () => {
                    const absent = !request.result.some(row => row.target?.kind === 'list' &&
                      row.target.listId === ${data.listId} && row.itemId === ${itemId});
                    db.close(); resolve(absent);
                  };
                  transaction.onerror = transaction.onabort = () => {
                    db.close(); reject(new Error('Bariera odczytu kolejki PWA nie powiodła się.'));
                  };
                };
              });
            })()`,
            undefined,
            { timeout: 30_000 },
          )
        // Read durable state, not pending=[] during asynchronous bootstrap.
        await queueAbsent()
        await Promise.all([...inFlight.values()].map((entry) => entry.done))
        await queueAbsent()
        expect(inFlight.size, 'Brak niezakończonego PATCH przed serwerowym GET i restore').toBe(0)
      },
      { timeout: 30_000 },
    )
  }
  const revealCheckbox = async (page: Page, itemId: number) => {
    const checkbox = page.getByTestId(`shopping-check-${itemId}`)
    await expect(checkbox).toHaveCount(1)
    if (!(await checkbox.isVisible())) {
      await checkbox
        .locator('xpath=ancestor::section[1]')
        .getByTestId('shopping-purchased-toggle')
        .click()
    }
    await expect(checkbox).toBeVisible()
    await expect(checkbox).toBeEnabled()
    return checkbox
  }
  const restoreOwnItem = async () => {
    if (!mutationAttempted) return
    if (!original || !diagnosticPage || diagnosticPage.isClosed())
      throw new Error('Brak otwartej karty do bezpiecznego przywrócenia własnej pozycji.')
    // Restore just this item through UI, with the same already-authenticated
    // context. No API mutation, storage reset, extra login, or other item edit.
    const own = original
    const page = diagnosticPage
    await context.setOffline(false)
    await reopenOnline(page)
    await actualUser(context, data.a1, data.baseURL)
    await controlled(diagnosticPage)
    await expect(diagnosticPage.getByTestId('lista-zakupowa-page')).toBeVisible()
    await settleOwnItem(diagnosticPage, own.id)
    await expect(diagnosticPage.getByTestId('offline-pending')).toHaveCount(0)
    const current = await actualList(context, data.listId, data.baseURL)
    const currentItem = current.sections
      .flatMap((section) => section.items)
      .find((entry) => entry.id === own.id)
    if (!currentItem || currentItem.received_at)
      throw new Error('Nie można bezpiecznie przywrócić własnej pozycji fixture.')
    const checkbox = await revealCheckbox(diagnosticPage, own.id)
    await expect(checkbox).toBeChecked({ checked: currentItem.checked })
    if (currentItem.checked !== own.checked) {
      const itemPath = `/api/v1/shopping/lists/${data.listId}/items/${own.id}`
      const [restored] = await Promise.all([
        diagnosticPage.waitForResponse(
          (response) =>
            new URL(response.url()).pathname === itemPath &&
            response.request().method() === 'PATCH',
          { timeout: 30_000 },
        ),
        (async () => {
          await checkbox.setChecked(own.checked)
        })(),
      ])
      expect(restored.status(), 'UI przywrócił wyłącznie oryginalną decyzję tej pozycji').toBe(200)
    }
    await expect(checkbox).toBeChecked({ checked: own.checked })
    await settleOwnItem(diagnosticPage, own.id)
    await expect(diagnosticPage.getByTestId('offline-pending')).toHaveCount(0)
    const restored = await actualList(context, data.listId, data.baseURL)
    expect(
      restored.sections.flatMap((section) => section.items).find((entry) => entry.id === own.id)
        ?.checked,
      'Serwerowy GET potwierdza przywrócony stan własnej pozycji',
    ).toBe(own.checked)
  }
  try {
    const page = await context.newPage()
    diagnosticPage = page
    await login(page, data.baseURL, data.password, 'a1', data.a1, testInfo)
    const list = await actualList(context, data.listId, data.baseURL)
    stage = 'warm-private'
    await warmPrivate(page, list)
    const items = list.sections.flatMap((section) => section.items)
    const item =
      items.find((entry) => !entry.received_at && !entry.already_have) ??
      items.find((entry) => !entry.received_at)
    if (!item) throw new Error('Brak własnej pozycji fixture nieprzyjętej do spiżarni.')
    original = { id: item.id, checked: item.checked }
    const intended = !item.checked
    const pendingList: ListDetail = {
      ...list,
      sections: list.sections.map((section) => ({
        ...section,
        items: section.items.map((entry) =>
          entry.id === item.id ? { ...entry, checked: intended } : entry,
        ),
      })),
    }
    await expect(page.getByTestId('offline-pending')).toHaveCount(0)
    stage = 'private-offline-reload'
    await context.setOffline(true)
    await page.reload()
    await controlled(page)
    await privateContents(page, list)
    stage = 'private-offline-banner'
    await expect(page.getByTestId('offline-banner')).toContainText('Tryb offline')
    stage = 'private-offline-toggle'
    const checkbox = await revealCheckbox(page, item.id)
    // Flag before clicking: a failed assertion can still leave a durable intent.
    mutationAttempted = true
    await checkbox.setChecked(intended)
    await expect(checkbox).toBeChecked({ checked: intended })
    await expect(page.getByTestId('offline-pending')).toHaveText('Oczekuje 1 zmiana')
    stage = 'private-pending-offline-restart'
    await page.reload()
    await controlled(page)
    await privateContents(page, pendingList)
    await expect(page.getByTestId('offline-banner')).toContainText('Tryb offline')
    await expect(page.getByTestId('offline-pending')).toHaveText('Oczekuje 1 zmiana')
    await expect(page.getByTestId(`shopping-check-${item.id}`)).toBeChecked({
      checked: intended,
    })
    stage = 'private-online-reopen'
    let meConfirmed = false
    let replayAfterMe = false
    const itemPath = `/api/v1/shopping/lists/${list.id}/items/${item.id}`
    const [confirmed, , patched] = await Promise.all([
      page.waitForResponse(
        (response) => {
          if (
            new URL(response.url()).pathname !== '/api/v1/auth/me' ||
            response.request().method() !== 'GET'
          )
            return false
          meConfirmed = response.status() === 200
          return true
        },
        { timeout: 30_000 },
      ),
      page.waitForRequest(
        (request) => {
          if (new URL(request.url()).pathname !== itemPath || request.method() !== 'PATCH')
            return false
          replayAfterMe = meConfirmed
          return true
        },
        { timeout: 30_000 },
      ),
      page.waitForResponse(
        (response) =>
          new URL(response.url()).pathname === itemPath && response.request().method() === 'PATCH',
        { timeout: 30_000 },
      ),
      (async () => {
        await context.setOffline(false)
        await reopenOnline(page)
      })(),
    ])
    stage = 'private-online-replay-evidence'
    expect(confirmed.status(), 'Przeglądarka ponownie potwierdziła sesję przed replay').toBe(200)
    expect(replayAfterMe, 'Rzeczywisty PATCH nastąpił po udanym /me').toBe(true)
    expect(patched.status(), 'Backend przyjął intencję zachowaną przez restart offline').toBe(200)
    await actualUser(context, data.a1, data.baseURL)
    await expect(page.getByTestId('offline-pending')).toHaveCount(0)
    stage = 'private-online-server-value'
    const saved = await actualList(context, data.listId, data.baseURL)
    expect(
      saved.sections.flatMap((section) => section.items).find((entry) => entry.id === item.id)
        ?.checked,
      'Niezależny rzeczywisty GET potwierdza zsynchronizowaną decyzję',
    ).toBe(intended)
    stage = 'private-online-banner'
    await expect(page.getByTestId('offline-banner')).toHaveCount(0)
    await page.reload()
    await controlled(page)
    await actualUser(context, data.a1, data.baseURL)
    await privateContents(page, pendingList)
  } catch (error) {
    // Emit a fixed stage immediately, before diagnostics or cleanup can time out.
    console.error(`[UX06 PWA] failure-stage=${stage}`)
    failures.push(
      `Prywatny PWA, etap ${stage}: ${safeFailure(error, data.password)}; ${await pageDiagnostics(diagnosticPage)}.`,
    )
  } finally {
    try {
      await restoreOwnItem()
    } catch (error) {
      failures.push(`Przywrócenie pozycji PWA: ${safeFailure(error, data.password)}`)
    } finally {
      try {
        await closeOnline(context)
      } catch {
        failures.push('Nie udało się zamknąć kontekstu prywatnego testu PWA.')
      }
    }
  }
  if (failures.length) throw new Error(failures.join(' '))
})

test('UX06 PWA: B1 nie widzi prywatnego snapshotu A1 w tym samym profilu', async ({
  browser,
  baseURL,
}, testInfo) => {
  const data = await fixture(baseURL)
  const context = await browser.newContext({ baseURL: data.baseURL, storageState: EMPTY_STATE })
  let diagnosticPage: Page | undefined
  let expectedName: string | undefined
  let presentations = 0
  let stage = 'warm-a1'
  try {
    const page = await context.newPage()
    diagnosticPage = page
    await login(page, data.baseURL, data.password, 'a1', data.a1, testInfo)
    const list = await actualList(context, data.listId, data.baseURL)
    expectedName = list.name
    await warmPrivate(page, list)
    stage = 'logout-a1'
    await page.getByTestId('account-toggle').click()
    const logout = page.waitForResponse(
      (response) => new URL(response.url()).pathname === '/api/v1/auth/logout',
    )
    await page.getByTestId('logout-button').click()
    expect((await logout).status()).toBe(204)
    await expect(page.getByTestId('login-submit')).toBeVisible()

    // Obserwacja także krótkiego ujawnienia przed błędem; żadnego czyszczenia storage w teście.
    await context.exposeBinding('__uxPwaPrivatePresented', () => {
      presentations += 1
    })
    const observation = `(() => {
      const selectors = ${JSON.stringify([
        '[data-testid="lista-nazwa"]',
        ...list.sections.flatMap((section) =>
          section.items.map((item) => `[data-testid="shopping-item-${item.id}"]`),
        ),
      ])};
      window.__uxPwaPrivateSeen = false;
      const inspect = () => {
        if (window.__uxPwaPrivateSeen) return;
        const visible = selectors.some(selector => Array.from(document.querySelectorAll(selector))
          .some(node => node.getClientRects().length > 0 &&
            getComputedStyle(node).visibility !== 'hidden' &&
            (selector !== selectors[0] || node.textContent.trim() === ${JSON.stringify(list.name)})));
        if (visible) {
          window.__uxPwaPrivateSeen = true;
          void window.__uxPwaPrivatePresented();
        }
      };
      new MutationObserver(inspect).observe(document, { childList: true, subtree: true, attributes: true });
      inspect();
    })()`
    await context.addInitScript(observation)
    await page.evaluate(observation)
    stage = 'login-b1'
    await login(page, data.baseURL, data.password, 'b1', data.b1, testInfo)
    stage = 'online-b1'
    await page.reload()
    await expect(page.getByTestId('plan-dnia-page')).toBeVisible()
    await controlled(page)
    await actualUser(context, data.b1, data.baseURL)
    const forbidden = await new PwaApi(context, data.baseURL).get(
      `/api/v1/shopping/lists/${data.listId}`,
    )
    expect(forbidden.status(), 'Backend odmawia B1 dostępu do listy A1').toBe(404)

    const unavailable = async () => {
      const terminal = page.getByTestId('lista-zakupowa-brak').or(page.getByRole('alert')).first()
      await expect(terminal).toBeVisible({ timeout: 30_000 })
      // Pusta transakcja jest barierą za wcześniejszymi odczytami/zapisami hydratacji.
      // Nie tworzymy bazy/stores i nie wykonujemy put/delete/clear.
      await page.evaluate(`(async () => {
        await new Promise((resolve, reject) => {
          const opening = indexedDB.open('pasnik-offline');
          opening.onupgradeneeded = () => {
            opening.transaction.abort();
            reject(new Error('Brak istniejącej bazy offline.'));
          };
          opening.onerror = () => reject(new Error('Odczyt bazy offline nie powiódł się.'));
          opening.onsuccess = () => {
            const database = opening.result;
            const stores = Array.from(database.objectStoreNames);
            if (stores.length === 0) {
              database.close();
              reject(new Error('Brak istniejących magazynów offline.'));
              return;
            }
            const barrier = database.transaction(stores, 'readwrite');
            barrier.oncomplete = () => { database.close(); resolve(); };
            barrier.onerror = barrier.onabort = () => {
              database.close();
              reject(new Error('Bariera hydratacji nie powiodła się.'));
            };
          };
        });
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      })()`)
      // Ponownie terminalny stan PO hydratacji i renderze, nie chwilowa nieobecność danych.
      await expect(terminal).toBeVisible()
      expect(await page.evaluate('window.__uxPwaPrivateSeen'), 'Brak chwilowego ujawnienia').toBe(
        false,
      )
      expect(presentations, 'Liczba ujawnień danych A1 dla B1').toBe(0)
      await expect(page.getByTestId('lista-nazwa')).toHaveCount(0)
      await expect(page.locator('[data-testid^="shopping-item-"]')).toHaveCount(0)
      await expect(page.getByTestId('login-submit')).toHaveCount(0)
    }
    stage = 'b1-offline-spa'
    await context.setOffline(true)
    // Nawigacja historii uruchamia prawdziwy router/guard bez restartu sesji w pamięci.
    // Sam goto od razu trafiłby na błąd auth/me i nie zbadałby hydratacji cudzej listy.
    await page.evaluate(`(() => {
      history.pushState(null, '', ${JSON.stringify(`/zakupy/listy/${data.listId}`)});
      dispatchEvent(new PopStateEvent('popstate', { state: history.state }));
    })()`)
    await unavailable()
    stage = 'b1-offline-reload'
    await page.reload()
    await controlled(page)
    await unavailable()
  } catch (error) {
    // Oryginalny cause może zawierać token URL; zachowujemy zredagowaną diagnozę.
    // eslint-disable-next-line preserve-caught-error
    throw new Error(
      `Izolacja PWA, etap ${stage}: ${safeFailure(error, data.password)}; presentations ${presentations}; ${await pageDiagnostics(diagnosticPage, expectedName)}.`,
    )
  } finally {
    await closeOnline(context)
  }
})

test('UX06 PWA: anonimowa publiczna lista przeżywa restart offline bez auth/me', async ({
  browser,
  baseURL,
}, testInfo) => {
  const data = await fixture(baseURL)
  const owner = await browser.newContext({ baseURL: data.baseURL, storageState: EMPTY_STATE })
  let publicContext: BrowserContext | undefined
  let diagnosticPage: Page | undefined
  let stage = 'owner-login'
  let authRequests = 0
  const statuses: number[] = []
  try {
    const ownerPage = await owner.newPage()
    await login(ownerPage, data.baseURL, data.password, 'a1', data.a1, testInfo)
    const list = await actualList(owner, data.listId, data.baseURL)
    const share = list.share
    if (!share || !/^\/l\/[A-Za-z0-9_-]{43}$/.test(share.url)) {
      throw new Error('Brak aktywnego publicznego linku fixture.')
    }
    // Token wyłącznie w pamięci; bez share-dialog, trace, wideo, zrzutów i zapisu stanu.
    publicContext = await browser.newContext({ baseURL: data.baseURL, storageState: EMPTY_STATE })
    publicContext.on('request', (request) => {
      if (new URL(request.url()).pathname === '/api/v1/auth/me') authRequests += 1
    })
    publicContext.on('response', (response) => {
      if (new URL(response.url()).pathname.startsWith('/api/v1/public/lists/')) {
        statuses.push(response.status())
      }
    })
    const page = await publicContext.newPage()
    diagnosticPage = page
    stage = 'public-open'
    const loaded = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname.startsWith('/api/v1/public/lists/') &&
        response.request().method() === 'GET',
    )
    // goto(token) umieściłoby URL także w tytule kroku raportu HTML.
    const opened = page.waitForEvent('framenavigated', (frame) => frame === page.mainFrame())
    await page.evaluate(`location.assign(${JSON.stringify(new URL(share.url, data.baseURL).href)})`)
    await opened
    await page.waitForLoadState('domcontentloaded')
    const response = await loaded
    expect(response.status()).toBe(200)
    const publicList: PublicList = await response.json()
    expect(publicList.name).toBe(list.name)
    expect(publicList.items.length).toBeGreaterThan(0)
    const reload = async () => {
      const navigated = page.waitForEvent('framenavigated', (frame) => frame === page.mainFrame())
      await page.evaluate('location.reload()')
      await navigated
      await page.waitForLoadState('domcontentloaded')
    }
    const contents = async () => {
      await expect(page.getByTestId('public-list-page')).toBeVisible()
      await expect(page.getByTestId('public-list-title')).toHaveText(publicList.name)
      await expect(page.locator('[data-testid^="shopping-item-"]')).toHaveCount(
        publicList.items.length,
      )
      for (const item of publicList.items) {
        await expect(page.getByTestId(`shopping-label-${item.id}`)).toHaveText(item.label)
        await expect(page.getByTestId(`shopping-check-${item.id}`)).toBeChecked({
          checked: item.checked,
        })
      }
      await expect(page.getByTestId('app-shell')).toHaveCount(0)
      await expect(page.getByTestId('public-list-error')).toHaveCount(0)
      await expect(page.getByTestId('public-list-unavailable')).toHaveCount(0)
      expect(authRequests).toBe(0)
    }
    stage = 'public-initial-contents'
    await contents()
    stage = 'public-sw-ready'
    await builtPwa(page)
    stage = 'public-online-reload'
    await reload()
    await controlled(page)
    await contents()
    stage = 'public-offline-reload'
    await publicContext.setOffline(true)
    await reload()
    await controlled(page)
    await contents()
    stage = 'public-offline-banner'
    await expect(page.getByTestId('offline-banner')).toContainText('Tryb offline')
    stage = 'public-online-return'
    await publicContext.setOffline(false)
    await reload()
    await contents()
  } catch (error) {
    // Nigdy nie przepuszczaj błędu goto/reload z pełnym URL-em do raportu.
    // eslint-disable-next-line preserve-caught-error
    throw new Error(
      `Publiczny control PWA, etap ${stage}: ${safeFailure(error, data.password)}; statusy HTTP [${statuses.join(',')}], auth/me ${authRequests}; ${await pageDiagnostics(diagnosticPage)}.`,
    )
  } finally {
    try {
      if (publicContext) await closeOnline(publicContext)
    } finally {
      await closeOnline(owner)
    }
  }
  expect(authRequests, 'Anonimowy context nie pyta o sesję także po powrocie sieci').toBe(0)
})
