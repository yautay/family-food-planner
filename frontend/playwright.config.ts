import { defineConfig, devices } from '@playwright/test'

import { AUTH_STATE_FILE } from './e2e/auth-state.js'

/**
 * E2E (08_TESTING §3) — utrzymywane małe i stabilne.
 *
 * BATCH_01 dowozi wyłącznie konfigurację i smoke „strona /login się renderuje";
 * pełny smoke login → plan dnia → wylogowanie dostarcza BATCH_02 (nie ma
 * jeszcze auth). Uruchomienie: `task test-e2e`.
 *
 * Domyślnie Playwright sam podnosi vite dev server. Gdy stack stoi już na
 * compose (`task dev`), wskaż go przez E2E_BASE_URL i pomiń start serwera:
 *   E2E_BASE_URL=http://127.0.0.1:5173 E2E_REUSE_SERVER=1 task test-e2e
 *
 * Sesja: projekt `setup` (`e2e/auth.setup.ts`) loguje się JEDEN RAZ i zapisuje
 * ciasteczka; projekt `chromium` startuje z tym stanem. Bez tego suita zderzała
 * się z limitem `/auth/login` (5/min/IP) i specy padały losowo na 429.
 * Testy samego logowania zerują `storageState` u siebie (`smoke.spec.ts`).
 */
const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173'
const reuseServer = process.env.E2E_REUSE_SERVER === '1'

export default defineConfig({
  testDir: './e2e',
  // Specy NIE są od siebie niezależne i nie da się tego obejść asercjami:
  // dzielą JEDNĄ bazę deweloperską i JEDNO konto (07_SECURITY §2 — w repo nie
  // ma drugiego hasła), a katalog produktów jest globalny. Do tego szukajki
  // produktów i przepisów są TRIGRAMOWE, więc encja utworzona równolegle przez
  // inny spec pod podobną nazwą wystarcza, żeby opcja „+ Dodaj" zniknęła
  // (`canCreate` w pickerach wymaga ZERA wyników) i inline create stał się
  // nieosiągalny. Równoległość kupowała tu kilkadziesiąt sekund za cenę
  // losowych czerwonych przebiegów — 08_TESTING §3 stawia na stabilność
  // (ustalenie R2, dług U15).
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'list' : [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL,
    trace: 'on-first-retry',
    // Selektory E2E: data-testid (08_TESTING §3).
    testIdAttribute: 'data-testid',
  },
  projects: [
    // Loguje się RAZ i zapisuje ciasteczka — `/auth/login` ma limit 5/min/IP
    // (07_SECURITY §2), a suita logowała się osiem razy i dostawała 429.
    { name: 'setup', testMatch: /auth\.setup\.ts/ },
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], storageState: AUTH_STATE_FILE },
      // `households.spec.ts` przenosi konto E2E do NOWEJ rodziny i na koniec ją
      // usuwa. Encje ze scope zapisują `household_id` także dla `private`
      // (ADR-006), więc gdy inne specy tworzą wtedy przepisy, dni planu czy
      // szablony, dostają `household_id` tej rodziny i sprzątające
      // `DELETE /admin/households/{id}` kończy się 409 (FK RESTRICT).
      // Kod zachowuje się POPRAWNIE — to projekt testów był wadliwy, więc
      // rozwiązaniem jest kolejność, nie osłabianie asercji (ustalenie R2).
      testIgnore: /households\.spec\.ts/,
      dependencies: ['setup'],
    },
    {
      // Osobny projekt = uruchomienie PO zakończeniu `chromium`, więc żaden inny
      // spec nie tworzy encji w czasie, gdy konto należy do rodziny tego specu.
      name: 'households',
      testMatch: /households\.spec\.ts/,
      use: { ...devices['Desktop Chrome'], storageState: AUTH_STATE_FILE },
      dependencies: ['chromium'],
    },
  ],
  webServer: reuseServer
    ? undefined
    : {
        command: 'npm run dev',
        url: baseURL,
        reuseExistingServer: true,
        timeout: 60_000,
      },
})
