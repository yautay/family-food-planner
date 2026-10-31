// @vitest-environment node
import { readFile, rename, writeFile } from 'node:fs/promises'
import { setTimeout as delay } from 'node:timers/promises'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { planLoginAttempt, reserveLoginAttempt } from '../../e2e/login-budget'

vi.mock('node:fs/promises', () => ({
  mkdir: vi.fn(),
  readFile: vi.fn(),
  rename: vi.fn(),
  rm: vi.fn(),
  writeFile: vi.fn(),
}))
vi.mock('node:timers/promises', () => ({ setTimeout: vi.fn() }))

const NOW = 1_800_000_000_000
const LOCAL_URL = 'http://127.0.0.1:5173'

describe('budżet logowania E2E — okno i zegary', () => {
  it('rezerwuje pierwsze pięć prób, także gdy ich odpowiedź będzie błędna', () => {
    let timestamps: number[] = []
    for (let attempt = 0; attempt < 5; attempt++) {
      const plan = planLoginAttempt(timestamps, NOW + attempt)
      expect(plan.waitMs).toBe(0)
      timestamps = plan.timestamps
    }
    expect(planLoginAttempt(timestamps, NOW + 5).waitMs).toBe(61_995)
  })

  it('zwalnia tylko najstarszy slot po 60 sekundach i buforze, nie całe okno', () => {
    const attempts = [NOW, NOW + 10_000, NOW + 20_000, NOW + 30_000, NOW + 40_000]
    expect(planLoginAttempt(attempts, NOW + 60_000).waitMs).toBe(2_000)
    expect(planLoginAttempt(attempts, NOW + 62_000)).toEqual({
      timestamps: [...attempts.slice(1), NOW + 62_000],
      waitMs: 0,
    })
  })

  it('przechowuje konserwatywny czas po niewielkiej korekcie zegara Windows/Linux', () => {
    expect(planLoginAttempt([NOW + 500], NOW)).toEqual({
      timestamps: [NOW + 500, NOW + 500],
      waitMs: 0,
    })
    expect(planLoginAttempt(Array(5).fill(NOW + 500), NOW).waitMs).toBe(62_500)
  })

  it.each([
    null,
    {},
    ['1800000000000'],
    [-1],
    [1.5],
    [Infinity],
    [NOW, NOW - 1],
    Array(6).fill(NOW),
    [NOW + 1_001],
  ])('odmawia uszkodzonego stanu lub dużego przesunięcia zegara: %j', (state) => {
    expect(() => planLoginAttempt(state, NOW)).toThrow(/nie resetuję pliku/)
  })
})

describe('rezerwacja przed loginem — trwałość i budżet timeoutu bez sieci ani plików', () => {
  let now: number
  let persisted: string
  let temporary: string
  beforeEach(() => {
    vi.resetAllMocks()
    now = NOW
    persisted = '[]'
    vi.spyOn(Date, 'now').mockImplementation(() => now)
    vi.spyOn(console, 'info').mockImplementation(() => {})
    vi.mocked(readFile).mockImplementation(async () => persisted)
    vi.mocked(writeFile).mockImplementation(async (_path, contents) => {
      temporary = String(contents)
    })
    vi.mocked(rename).mockImplementation(async () => {
      persisted = temporary
    })
    vi.mocked(delay).mockImplementation(async (ms) => {
      now += ms ?? 0
    })
  })

  it('kolejny worker korzysta z zapisanych slotów i zwiększa timeout wyłącznie o oczekiwanie', async () => {
    const timeout = { timeout: 30_000, setTimeout: vi.fn() }
    for (let attempt = 0; attempt < 5; attempt++) await reserveLoginAttempt(LOCAL_URL, timeout)
    expect(timeout.setTimeout).not.toHaveBeenCalled()
    await reserveLoginAttempt(LOCAL_URL, timeout)
    expect(delay).toHaveBeenCalledExactlyOnceWith(62_000)
    expect(timeout.setTimeout).toHaveBeenCalledExactlyOnceWith(92_000)
    expect(JSON.parse(persisted)).toEqual([NOW + 62_000])
    expect(rename).toHaveBeenCalledTimes(6)
  })

  it('zachowuje istniejące 180 sekund hooka mimo domyślnego TestInfo.timeout=30 sekund', async () => {
    persisted = JSON.stringify(Array(5).fill(NOW))
    const timeout = { timeout: 30_000, setTimeout: vi.fn() }
    await reserveLoginAttempt(LOCAL_URL, timeout, 180_000)
    expect(timeout.setTimeout).toHaveBeenCalledExactlyOnceWith(242_000)
  })

  it('brak pliku rozpoczyna budżet, inne błędy odczytu są propagowane', async () => {
    vi.mocked(readFile).mockRejectedValueOnce({ code: 'ENOENT' })
    await reserveLoginAttempt(LOCAL_URL, { timeout: 30_000, setTimeout: vi.fn() })
    expect(JSON.parse(persisted)).toEqual([NOW])
    vi.mocked(readFile).mockRejectedValueOnce({ code: 'EACCES' })
    await expect(
      reserveLoginAttempt(LOCAL_URL, { timeout: 30_000, setTimeout: vi.fn() }),
    ).rejects.toEqual({ code: 'EACCES' })
    expect(rename).toHaveBeenCalledTimes(1)
  })

  it('nie nadpisuje niepoprawnego JSON ani nie przyznaje próby przed udanym zapisem', async () => {
    persisted = '[bad json'
    const timeout = { timeout: 30_000, setTimeout: vi.fn() }
    await expect(reserveLoginAttempt(LOCAL_URL, timeout)).rejects.toThrow(/Nieprawidłowy JSON/)
    expect(rename).not.toHaveBeenCalled()
    persisted = '[]'
    vi.mocked(rename).mockRejectedValueOnce(new Error('write failed'))
    await expect(reserveLoginAttempt(LOCAL_URL, timeout)).rejects.toThrow('write failed')
  })

  it('odmawia koordynacji poza localhost przed odczytem i zapisem', async () => {
    await expect(
      reserveLoginAttempt('https://example.com', { timeout: 30_000, setTimeout: vi.fn() }),
    ).rejects.toThrow(/localhost/)
    expect(readFile).not.toHaveBeenCalled()
    expect(writeFile).not.toHaveBeenCalled()
  })
})
