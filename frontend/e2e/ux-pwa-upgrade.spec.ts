import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { expect, test, type BrowserContext, type Page } from '@playwright/test'

import { EMPTY_STATE } from './auth-state.js'
import { PwaApi } from './ux-pwa-native-api.js'
import {
  actualList,
  actualUser,
  closeOnline,
  controlled,
  credentialFingerprint,
  fixture,
  hydrationBarrier,
  listContents,
  listMarkers,
  login,
  logout,
  offlineReload,
  privateObserver,
  safeFailure,
  spaList,
  unavailable,
  warmPrivate,
  type ListDetail,
} from './ux-pwa-advanced-helpers.js'

test.use({ storageState: EMPTY_STATE, trace: 'off', video: 'off', screenshot: 'off' })
test.describe.configure({ timeout: 300_000, retries: 0, mode: 'serial' })
test.skip(
  process.env.UX_PWA_ADVANCED !== '1',
  'Wymaga UX_PWA_ADVANCED=1 i wyłącznego preview UX00.',
)

function inside(parent: string, child: string): boolean {
  const relative = path.relative(parent, child)
  return (
    Boolean(relative) &&
    relative !== '..' &&
    !relative.startsWith(`..${path.sep}`) &&
    !path.isAbsolute(relative)
  )
}

/** Only built regular files: reject symlinks/junctions before any recursive copy. */
async function generatedTree(directory: string): Promise<void> {
  for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
    if (entry.isSymbolicLink()) throw new Error('Artefakt buildu zawiera symlink; bez kopiowania.')
    const child = path.resolve(directory, entry.name)
    if (!inside(directory, child)) throw new Error('Artefakt wychodzi poza katalog generowany.')
    if (entry.isDirectory()) await generatedTree(child)
    else if (!entry.isFile()) throw new Error('Artefakt zawiera obiekt inny niż zwykły plik.')
  }
}

async function upgradeArtifacts() {
  // Derive from THIS checkout, including Docker's /workspace bind. No arbitrary
  // env path, source tree copy, recursive delete, move, or user-data operation.
  const root = await fs.realpath(fileURLToPath(new URL('../../', import.meta.url)))
  const dist = path.resolve(root, 'frontend/dist')
  const results = path.resolve(root, 'backend/data/ux06-results')
  const legacy = path.resolve(results, 'legacy-dist-before-isolation')
  for (const directory of [dist, results, legacy]) {
    if (!path.isAbsolute(directory) || !inside(root, directory)) {
      throw new Error('Niebezpieczna ścieżka artefaktu poza root checkoutu.')
    }
    let resolved: string
    try {
      resolved = await fs.realpath(directory)
    } catch {
      throw new Error(
        'Brak bieżącego dist lub zachowanego legacy-dist-before-isolation; opt-in wymaga obu artefaktów.',
      )
    }
    if (resolved !== directory || !(await fs.lstat(directory)).isDirectory()) {
      throw new Error('Katalog generowany jest przekierowany albo nie jest katalogiem.')
    }
  }
  await generatedTree(dist)
  await generatedTree(legacy)
  const currentWorker = await fs.readFile(path.join(dist, 'sw-private-v1.js'))
  const alias = await fs.readFile(path.join(dist, 'sw.js'))
  const legacyWorker = await fs.readFile(path.join(legacy, 'sw.js'), 'utf8')
  const index = await fs.readFile(path.join(dist, 'index.html'))
  if (!currentWorker.equals(alias)) throw new Error('Nowy build nie ma identycznego aliasu /sw.js.')
  if (!legacyWorker.includes('pasnik-api') || !legacyWorker.includes('NetworkFirst')) {
    throw new Error('Zachowany artefakt nie jest starym SW z NetworkFirst/pasnik-api.')
  }
  if (currentWorker.equals(Buffer.from(legacyWorker))) {
    throw new Error('Artefakt legacy i bieżący worker są identyczne; brak rzeczywistego upgrade.')
  }
  await fs.readFile(path.join(legacy, 'index.html'))
  const backup = await fs.mkdtemp(path.join(results, 'upgrade-current-'))
  if (!inside(results, backup) || (await fs.realpath(backup)) !== backup) {
    throw new Error('Niebezpieczna ścieżka backupu generowanego dist.')
  }
  await fs.cp(dist, backup, { recursive: true, dereference: false })
  // The backup is retained as evidence; the test never removes artifacts.
  return { root, dist, legacy, backup, currentWorker, index }
}

async function cachedPrivateResponse(page: Page, list: ListDetail): Promise<boolean> {
  // Return only evidence booleans. Never serialize a cached share/token to Node.
  return page.evaluate(`(async () => {
    if (!await caches.has('pasnik-api')) return false;
    const cache = await caches.open('pasnik-api');
    const response = await cache.match(new URL(${JSON.stringify(`/api/v1/shopping/lists/${list.id}`)}, location.origin));
    if (!response || response.status !== 200) return false;
    const payload = await response.json();
    const expected = ${JSON.stringify({
      id: list.id,
      name: list.name,
      items: list.sections.flatMap((section) =>
        section.items.map(({ id, label }) => ({ id, label })),
      ),
    })};
    return payload.id === expected.id && payload.name === expected.name &&
      JSON.stringify(payload.sections.flatMap(section => section.items.map(({ id, label }) => ({ id, label })))) ===
      JSON.stringify(expected.items);
  })()`)
}

async function legacySnapshot(page: Page, list: ListDetail): Promise<string | null> {
  return page.evaluate(`(async () => {
    const row = await new Promise((resolve, reject) => {
      const opening = indexedDB.open('pasnik-offline');
      opening.onupgradeneeded = () => {
        opening.transaction.abort(); reject(new Error('Brak istniejącej bazy legacy.'));
      };
      opening.onerror = () => reject(new Error('Nie można odczytać bazy legacy.'));
      opening.onsuccess = () => {
        const db = opening.result;
        if (!db.objectStoreNames.contains('list-snapshots')) {
          db.close(); reject(new Error('Brak istniejących snapshotów legacy.')); return;
        }
        const transaction = db.transaction('list-snapshots', 'readonly');
        const request = transaction.objectStore('list-snapshots').get(${JSON.stringify(`list:${list.id}`)});
        transaction.oncomplete = () => { db.close(); resolve(request.result); };
        transaction.onerror = transaction.onabort = () => {
          db.close(); reject(new Error('Nie można odczytać snapshotu legacy.'));
        };
      };
    });
    if (!row || row.payload?.id !== ${list.id} || row.payload?.name !== ${JSON.stringify(list.name)}) return null;
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(row)));
    return Array.from(new Uint8Array(digest), value => value.toString(16).padStart(2, '0')).join('');
  })()`)
}

async function noLegacyCaches(page: Page): Promise<void> {
  expect(
    await page.evaluate(`(async () => {
      const names = await caches.keys();
      return !names.includes('pasnik-api') && !names.includes('pasnik-uploads');
    })()`),
    'Bootstrap usuwa oba legacy cache, nowy worker ich nie odtwarza',
  ).toBe(true)
}

/** Fixed classes only: never retain a browser URL, query, token or headers. */
function browserPathClass(value: string, origin: string): string {
  try {
    const url = new URL(value)
    if (url.origin !== origin) return 'other-origin'
    const pathname = url.pathname
    if (pathname === '/api/v1/auth/me') return 'auth-me'
    if (pathname === '/api/v1/auth/login') return 'auth-login'
    if (pathname === '/api/v1/auth/logout') return 'auth-logout'
    if (pathname.startsWith('/api/v1/public/')) return 'public-api'
    if (/^\/api\/v1\/shopping\/lists\/\d+$/.test(pathname)) return 'private-list-api'
    if (/^\/api\/v1\/shopping\/lists\/\d+\/items\//.test(pathname)) return 'private-item-api'
    if (pathname.startsWith('/api/v1/stores')) return 'stores-api'
    if (pathname.startsWith('/api/')) return 'other-api'
    if (pathname.startsWith('/assets/')) return 'build-asset'
    if (pathname === '/sw.js') return 'alias-worker'
    if (pathname === '/sw-private-v1.js') return 'canonical-worker'
    if (pathname.startsWith('/workbox-')) return 'workbox-script'
    if (pathname.startsWith('/zakupy/listy/')) return 'private-list-document'
    if (pathname === '/login') return 'login-document'
    if (pathname.startsWith('/plan-dnia')) return 'plan-document'
    if (pathname === '/icon.svg') return 'witness-static'
    return 'other-same-origin'
  } catch {
    return 'unclassified'
  }
}

async function bootstrapSnapshot(page: Page | undefined) {
  if (!page || page.isClosed()) return { pageClosed: true }
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    return await Promise.race([
      page
        .evaluate(
          `(() => {
          const count = selector => document.querySelectorAll(selector).length;
          const controller = 'serviceWorker' in navigator ? navigator.serviceWorker.controller : null;
          const path = controller ? new URL(controller.scriptURL).pathname : null;
          return {
            readyState: document.readyState,
            appChildCount: document.getElementById('app')?.childElementCount ?? null,
            mainCount: count('main'),
            shellCount: count('[data-testid="app-shell"]'),
            loginCount: count('[data-testid="login-submit"]'),
            listCount: count('[data-testid="lista-zakupowa-page"]'),
            alertCount: count('[role="alert"]'),
            controller: path === null ? 'none' : path === '/sw.js' ? 'alias'
              : path === '/sw-private-v1.js' ? 'canonical' : 'other',
            controllerActivated: controller?.state === 'activated',
          };
        })()`,
        )
        .then((document: unknown) => ({ pageClosed: page.isClosed(), document }))
        .catch(() => ({ pageClosed: page.isClosed(), documentUnavailable: true })),
      new Promise((resolve) => {
        timer = setTimeout(
          () => resolve({ pageClosed: page.isClosed(), documentInspectionTimedOut: true }),
          1500,
        )
      }),
    ])
  } finally {
    if (timer !== undefined) clearTimeout(timer)
  }
}

test('UX06 PWA: rzeczywisty upgrade legacy /sw.js na tym samym originie, kwarantanna i izolacja B', async ({
  browser,
  baseURL,
}, testInfo) => {
  const data = await fixture(baseURL)
  const artifacts = await upgradeArtifacts()
  let context: BrowserContext | undefined
  let overlaid = false
  let stage = 'overlay-preserved-legacy-build'
  let diagnosticPage: Page | undefined
  const events: { page: string; event: string; pathClass?: string; status?: number }[] = []
  const pageErrors: { page: string; error: string }[] = []
  const watch = (page: Page, label: 'legacy' | 'witness' | 'fresh') => {
    const record = (event: string, value?: string, status?: number) => {
      events.push({
        page: label,
        event,
        ...(value === undefined ? {} : { pathClass: browserPathClass(value, data.baseURL) }),
        ...(status === undefined ? {} : { status }),
      })
      if (events.length > 60) events.shift()
    }
    page.on('request', (request) => record('request', request.url()))
    page.on('response', (response) => record('response', response.url(), response.status()))
    page.on('requestfailed', (request) => record('requestfailed', request.url()))
    page.on('framenavigated', (frame) => {
      if (frame === page.mainFrame()) record('main-frame-navigation', frame.url())
    })
    page.on('close', () => record('closed'))
    page.on('crash', () => record('crashed'))
    page.on('pageerror', (error) => {
      pageErrors.push({ page: label, error: safeFailure(error, [data.password]) })
      if (pageErrors.length > 8) pageErrors.shift()
    })
  }
  const diagnose = async (point: string) => {
    const evidence = JSON.stringify({
      point,
      stage,
      snapshot: await bootstrapSnapshot(diagnosticPage),
      events,
      pageErrors,
    })
    console.info(`[UX06 PWA upgrade] ${evidence}`)
    try {
      await testInfo.attach(`upgrade-bootstrap-${point}`, {
        body: evidence,
        contentType: 'application/json',
      })
    } catch {
      console.info('[UX06 PWA upgrade] diagnostic-attachment-unavailable')
    }
  }
  try {
    // Mark before the first write: even a partial cp must restore the new build.
    overlaid = true
    await fs.cp(artifacts.legacy, artifacts.dist, { recursive: true, dereference: false })
    context = await browser.newContext({ baseURL: data.baseURL, storageState: EMPTY_STATE })
    const legacyPage = await context.newPage()
    diagnosticPage = legacyPage
    watch(legacyPage, 'legacy')
    legacyPage.on('dialog', async (dialog) => {
      if (
        dialog.type() === 'confirm' &&
        dialog.message() === 'Dostępna jest nowa wersja aplikacji. Odświeżyć teraz?'
      ) {
        await dialog.accept()
      } else {
        await dialog.dismiss()
      }
    })
    stage = 'real-legacy-a1-cache-and-snapshot'
    await login(legacyPage, 'a1', data, testInfo)
    const list = await actualList(context, data)
    await warmPrivate(legacyPage, list, '/sw.js')
    await expect
      .poll(() => cachedPrivateResponse(legacyPage, list), {
        message: 'Stary rzeczywisty /sw.js zapisał udaną prywatną odpowiedź A w pasnik-api',
      })
      .toBe(true)
    await expect
      .poll(() => legacySnapshot(legacyPage, list), {
        message: 'Stary UI zapisał prawdziwy nieskopowany snapshot A bez seedowania storage',
      })
      .not.toBeNull()
    const quarantined = await legacySnapshot(legacyPage, list)
    expect(quarantined !== null).toBe(true)
    const credentials = await credentialFingerprint(context)
    // The preserved app auto-reloads on worker activation. A real static SVG
    // document has the same existing controller and no app reload handler, so
    // its activation witness survives that legitimate application navigation.
    const witness = await context.newPage()
    watch(witness, 'witness')
    await witness.goto('/icon.svg')
    expect(
      await witness.evaluate('document.contentType === "image/svg+xml"'),
      'Świadek jest rzeczywistym statycznym zasobem buildu, bez bootstrapu aplikacji',
    ).toBe(true)
    await controlled(witness, '/sw.js')

    stage = 'restore-new-build-and-update-real-alias'
    await fs.cp(artifacts.backup, artifacts.dist, { recursive: true, dereference: false })
    expect(
      (await fs.readFile(path.join(artifacts.dist, 'sw.js'))).equals(artifacts.currentWorker),
      'Preview udostępnia nowy identyczny alias',
    ).toBe(true)
    // A reload alone would still receive OLD index.html from the old precache.
    // Update the existing registration at its actual URL; wait for a different
    // activated controller, not merely registration.update() resolution.
    expect(
      await witness.evaluate(`(async () => {
      const previous = navigator.serviceWorker.controller;
      if (!previous || new URL(previous.scriptURL).pathname !== '/sw.js')
        throw new Error('Brak rzeczywistego starego controllera /sw.js.');
      const registration = await navigator.serviceWorker.getRegistration('/');
      if (!registration || registration.active !== previous)
        throw new Error('Brak aktywnej rejestracji starego workera.');
      return new Promise((resolve, reject) => {
        let settled = false;
        const finish = error => {
          if (settled) return;
          settled = true;
          clearTimeout(timeout);
          navigator.serviceWorker.removeEventListener('controllerchange', check);
          registration.removeEventListener('updatefound', observeInstalling);
          if (error) reject(error); else resolve(true);
        };
        const check = () => {
          const current = navigator.serviceWorker.controller;
          if (current && current !== previous && current.state === 'activated' &&
            new URL(current.scriptURL).pathname === '/sw.js') finish();
        };
        const observeInstalling = () => {
          registration.installing?.addEventListener('statechange', check);
        };
        const timeout = setTimeout(() => finish(new Error('Alias nie przejął kontroli po update.')), 45000);
        navigator.serviceWorker.addEventListener('controllerchange', check);
        registration.addEventListener('updatefound', observeInstalling);
        void registration.update().then(check).catch(() => finish(new Error('Update aliasu nie powiódł się.')));
      });
    })()`),
      'Nowy worker rzeczywiście aktywował się pod istniejącym /sw.js',
    ).toBe(true)

    stage = 'fresh-page-in-existing-context'
    // The legacy registration legitimately auto-reloads its application tab
    // on activation and can detach it before close() finishes. Leave that tab
    // for context disposal: even awaiting close would block the upgrade proof.
    // A fresh page retains this exact context, origin, cookies, SW and storage.
    const currentContext = context
    const page = await test.step(
      'Nowa karta w tym samym kontekście po aktywacji aliasu',
      () => currentContext.newPage(),
      { timeout: 30_000 },
    )
    diagnosticPage = page
    watch(page, 'fresh')
    stage = 'new-index-navigation'
    await diagnose('pre-bootstrap')
    const navigation = await page.goto(`/zakupy/listy/${list.id}`, { timeout: 30_000 })
    expect(navigation?.status(), 'Nowa karta otrzymała rzeczywisty index po upgrade').toBe(200)
    stage = 'new-index-canonical-controller'
    await diagnose('post-navigation')
    await controlled(page)
    stage = 'new-index-backend-session'
    await actualUser(context, 'a1', data)
    expect(
      (await credentialFingerprint(context)) === credentials,
      'Nowa karta zachowała te same cookie sesji A1 i CSRF',
    ).toBe(true)
    stage = 'new-index-list-render'
    await diagnose('pre-list-assert')
    await listContents(page, list)
    await diagnose('post-bootstrap')
    stage = 'new-index-hydration-and-quarantine'
    await hydrationBarrier(page)
    await noLegacyCaches(page)
    expect(
      (await legacySnapshot(page, list)) === quarantined,
      'Snapshot legacy pozostaje nietknięty w kwarantannie po upgrade',
    ).toBe(true)

    const audit = await privateObserver(page, listMarkers(list))
    stage = 'logout-a-login-b-after-upgrade'
    await logout(page)
    await audit.arm()
    await audit.assertClean()
    await login(page, 'b1', data, testInfo)
    await actualUser(context, 'b1', data)
    const denied = await new PwaApi(context, data.baseURL).get(
      `/api/v1/shopping/lists/${data.listId}`,
    )
    expect(denied.status(), 'Rzeczywisty backend odmawia B starej listy A').toBe(404)
    await audit.assertClean()
    stage = 'upgraded-b-offline-old-list'
    await context.setOffline(true)
    await spaList(page, list.id)
    await unavailable(page)
    await audit.assertClean()
    await offlineReload(page)
    await controlled(page)
    await unavailable(page)
    await audit.assertClean()
    await noLegacyCaches(page)
    expect(
      (await legacySnapshot(page, list)) === quarantined,
      'Kwarantanna zachowana również po odmowie B i restarcie offline',
    ).toBe(true)
  } catch (error) {
    // Fixed stage first: cleanup or a detached document must not hide it.
    console.error(`[UX06 PWA upgrade] failure-stage=${stage}`)
    await diagnose('failure')
    // eslint-disable-next-line preserve-caught-error
    throw new Error(`Upgrade PWA, etap ${stage}: ${safeFailure(error, [data.password])}`)
  } finally {
    try {
      if (overlaid) {
        // Restore irrespective of browser, login, update, or assertion failures.
        // Paths were resolved under this checkout and only generated files copy.
        await fs.cp(artifacts.backup, artifacts.dist, { recursive: true, dereference: false })
        expect(
          (await fs.readFile(path.join(artifacts.dist, 'index.html'))).equals(artifacts.index),
          'Finally przywrócił nowy index.html',
        ).toBe(true)
        expect(
          (await fs.readFile(path.join(artifacts.dist, 'sw.js'))).equals(artifacts.currentWorker),
          'Finally przywrócił nowy alias /sw.js',
        ).toBe(true)
      }
    } finally {
      if (context) await closeOnline(context)
    }
  }
})
