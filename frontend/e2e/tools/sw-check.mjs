/**
 * Weryfikacja rejestracji service workera NA BUILDZIE PRODUKCYJNYM (karta B17,
 * „Do przeglądu z B12" pkt 1 + ustalenie R4 pkt 2): po zaostrzeniu CSP SW mógłby
 * wyłączyć się po cichu — aplikacja działa, offline nie. Playwrightowe Chromium
 * traktuje http://127.0.0.1 jako secure context, więc rejestruje SW jak telefon
 * przez HTTPS. Uruchomienie (stack testowy: `task test-stack-up`):
 *
 *   node frontend/e2e/tools/sw-check.mjs http://127.0.0.1:8081
 *
 * Kod wyjścia 0 = aktywny SW o scope `/`, precache wypełniony, zero błędów CSP
 * w konsoli. Narzędzie operacyjne, nie spec — nie wchodzi do `task test-e2e`.
 */
import { chromium } from '@playwright/test'

const base = process.argv[2] ?? 'http://127.0.0.1:8081'
const browser = await chromium.launch()
const context = await browser.newContext()
const page = await context.newPage()
const consoleErrors = []
page.on('console', (msg) => {
  if (msg.type() === 'error') consoleErrors.push(msg.text())
})
const failed = []
page.on('requestfailed', (req) => failed.push(`${req.url()} ${req.failure()?.errorText ?? ''}`))
let workerUrl = null
context.on('serviceworker', (worker) => {
  workerUrl = worker.url()
  worker.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(`[sw] ${msg.text()}`)
  })
})

await page.goto(`${base}/`, { waitUntil: 'load' })

// Precache to ~70 wpisów; na obciążonym hoście instalacja trwa kilkanaście sekund.
let lifecycle = []
for (let i = 0; i < 45; i += 1) {
  await page.waitForTimeout(2000)
  lifecycle = await page.evaluate(async () => {
    const regs = await navigator.serviceWorker.getRegistrations()
    return regs.map((r) => ({
      scope: r.scope,
      installing: r.installing?.state ?? null,
      waiting: r.waiting?.state ?? null,
      active: r.active?.state ?? null,
    }))
  })
  if (lifecycle.some((r) => r.active === 'activated')) break
}

const caches = await page.evaluate(async () => {
  const names = await window.caches.keys()
  let precached = 0
  for (const name of names) {
    precached += (await (await window.caches.open(name)).keys()).length
  }
  return { names, precached }
})

const csp = consoleErrors.filter((e) => /Content Security Policy|CSP/i.test(e))
const ok =
  workerUrl !== null &&
  lifecycle.some((r) => r.scope === `${base}/` && r.active === 'activated') &&
  caches.precached > 0 &&
  csp.length === 0

console.log(JSON.stringify({ base, workerUrl, lifecycle, caches, failed, consoleErrors }, null, 2))
console.log(
  ok
    ? 'SW-CHECK: OK — service worker aktywny, precache wypełniony, zero błędów CSP'
    : 'SW-CHECK: FAIL',
)
await browser.close()
process.exit(ok ? 0 : 1)
