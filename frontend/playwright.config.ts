import { defineConfig, devices } from '@playwright/test'

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
 */
const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173'
const reuseServer = process.env.E2E_REUSE_SERVER === '1'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
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
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
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
