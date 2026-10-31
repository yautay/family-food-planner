import { randomUUID } from 'node:crypto'
import { mkdir, readFile, rename, rm, writeFile } from 'node:fs/promises'
import { dirname } from 'node:path'
import { setTimeout as delay } from 'node:timers/promises'
import { fileURLToPath } from 'node:url'

import type { TestInfo } from '@playwright/test'

const ATTEMPTS = 5
const WINDOW_MS = 60_000
// One second for small host/guest clock skew, one for dispatch after reservation.
const SAFETY_MS = 2_000
const CLOCK_SKEW_MS = 1_000
const STATE_FILE = fileURLToPath(new URL('./.auth/login-attempts.json', import.meta.url))
const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]', '::1'])

/** Epoch milliseconds are shared by Windows and the bind-mounted Linux runner. */
export function planLoginAttempt(
  state: unknown,
  now: number,
): { timestamps: number[]; waitMs: number } {
  if (
    !Number.isSafeInteger(now) ||
    now < 0 ||
    !Array.isArray(state) ||
    state.length > ATTEMPTS ||
    state.some(
      (timestamp: unknown, index: number) =>
        typeof timestamp !== 'number' ||
        !Number.isSafeInteger(timestamp) ||
        timestamp < 0 ||
        timestamp > now + CLOCK_SKEW_MS ||
        (index > 0 && timestamp < state[index - 1]),
    )
  ) {
    throw new Error(
      'Nieprawidłowy stan budżetu logowania lub rozbieżność zegarów; nie resetuję pliku.',
    )
  }
  const active = (state as number[]).filter((timestamp) => timestamp + WINDOW_MS + SAFETY_MS > now)
  if (active.length === ATTEMPTS) {
    return { timestamps: active, waitMs: active[0]! + WINDOW_MS + SAFETY_MS - now }
  }
  // A small backward clock correction must not reorder or expire reservations early.
  return { timestamps: [...active, Math.max(now, active.at(-1) ?? now)], waitMs: 0 }
}

async function readTimestamps(): Promise<unknown> {
  let contents: string
  try {
    contents = await readFile(STATE_FILE, 'utf8')
  } catch (error) {
    if (error && typeof error === 'object' && 'code' in error && error.code === 'ENOENT') return []
    throw error
  }
  try {
    return JSON.parse(contents) as unknown
  } catch {
    throw new Error('Nieprawidłowy JSON budżetu logowania; nie resetuję pliku.')
  }
}

/**
 * Reserve BEFORE every real login, including rejected credentials. The one-worker,
 * exclusive E2E runtime serializes access; atomic replacement survives worker restarts.
 * Only timestamps are persisted, never credentials or session state.
 * beforeAll must supply its existing hook timeout: TestInfo.timeout reads the test slot.
 */
export async function reserveLoginAttempt(
  baseURL: string | undefined,
  testInfo: Pick<TestInfo, 'timeout' | 'setTimeout'>,
  hookTimeoutMs?: number,
): Promise<void> {
  if (!baseURL || !LOCAL_HOSTS.has(new URL(baseURL).hostname)) {
    throw new Error('Budżet logowania E2E jest dozwolony wyłącznie na localhost.')
  }
  const timeoutMs = hookTimeoutMs ?? testInfo.timeout
  let waitBudgetMs = 0
  for (;;) {
    const plan = planLoginAttempt(await readTimestamps(), Date.now())
    if (plan.waitMs > 0) {
      waitBudgetMs += plan.waitMs
      if (timeoutMs > 0) testInfo.setTimeout(timeoutMs + waitBudgetMs)
      console.info(`[e2e login budget] oczekiwanie ${plan.waitMs} ms`)
      await delay(plan.waitMs)
      continue
    }
    await mkdir(dirname(STATE_FILE), { recursive: true })
    const temporary = `${STATE_FILE}.${randomUUID()}.tmp`
    try {
      await writeFile(temporary, JSON.stringify(plan.timestamps), { flag: 'wx' })
      await rename(temporary, STATE_FILE)
    } finally {
      await rm(temporary, { force: true })
    }
    return
  }
}
