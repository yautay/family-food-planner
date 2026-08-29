import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createMemoryHistory, createRouter } from 'vue-router'

import ImportPage from './ImportPage.vue'
import type { ImportJobDetail, ImportJobSummary } from '@/api/pdfImport'
import { routes } from '@/router'

/**
 * Strona importu niczego nie liczy — testujemy to, co robi z odpowiedziami
 * `/import/jobs` i `/import/jobs/{id}`: plakietki statusów po polsku, render
 * raportu odczytu i stan pusty. Zapytania są zamockowane (05_FRONTEND §8).
 *
 * Podział odpowiedzi jest tu ISTOTNY, bo złapał go dopiero E2E: **lista NIE
 * niesie `parse_report`** (`ImportJobSummary` ma same liczby zbiorcze), więc
 * raport dociąga się osobnym żądaniem o szczegóły joba. Mocki odwzorowują ten
 * podział — spec z raportem wklejonym w listę przechodziłby przy zepsutej
 * stronie.
 */
const importApi = vi.hoisted(() => ({
  listJobs: vi.fn(),
  uploadPdf: vi.fn(),
  deleteJob: vi.fn(),
  getJob: vi.fn(),
  MAX_PDF_MB: 25,
  JOBS_PAGE_SIZE: 50,
  parseReportOf: (job: { parse_report?: unknown } | null | undefined) =>
    (job?.parse_report as unknown) ?? null,
  exactMatchPercent: (report: { match: { exact: number; none: number } } | null) => {
    if (!report) return null
    const total = report.match.exact + report.match.none
    return total === 0 ? null : Math.round((report.match.exact / total) * 100)
  },
}))
vi.mock('@/api/pdfImport', () => importApi)

function report(overrides: Record<string, unknown> = {}) {
  return {
    pages: { total: 10, days: 5, skipped_shopping: 2, skipped_exchanges: 1 },
    days: 3,
    meals: 12,
    staged_recipes: 13,
    ingredients: 85,
    issues: { blocker: 0, warning: 0 },
    match: { exact: 40, none: 45 },
    day_checksums: [
      { day: 'Poniedziałek', expected: '2021', computed: '2021', ok: true },
      { day: 'Wtorek', expected: '1953', computed: '1953', ok: true },
      { day: 'Środa', expected: '1919', computed: '1919', ok: true },
    ],
    warnings: [],
    ...overrides,
  }
}

/** Wiersz listy — dokładnie to, co zwraca `ImportJobSummary` (BEZ raportu). */
function summary(overrides: Partial<ImportJobSummary> = {}): ImportJobSummary {
  return {
    id: 1,
    filename: 'dieta.pdf',
    status: 'parsed',
    created_at: '2026-08-29T10:00:00+00:00',
    updated_at: '2026-08-29T10:00:05+00:00',
    error: null,
    days: 3,
    meals: 12,
    staged_recipes: 13,
    ingredients: 85,
    blockers: 0,
    warnings: 0,
    ...overrides,
  } as ImportJobSummary
}

/** Odpowiedź `GET /import/jobs/{id}` — ta niesie `parse_report`. */
function detail(parseReport: unknown = report()): ImportJobDetail {
  return { ...summary(), parse_report: parseReport } as ImportJobDetail
}

async function mountPage() {
  // Router jest realny (pamięciowy), bo strona ma teraz LINK do review —
  // `RouterLinkStub` nie sprawdziłby, że powstaje prawdziwe `<a href>` (R2).
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push('/import')
  await router.isReady()

  const wrapper = mount(ImportPage, { global: { plugins: [VueQueryPlugin, router] } })
  await flushPromises()
  return wrapper
}

describe('ImportPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    importApi.listJobs.mockResolvedValue({ items: [], total: 0 })
    importApi.getJob.mockResolvedValue(detail())
  })

  it('pokazuje uczący stan pusty, gdy nie ma jeszcze żadnego importu', async () => {
    const wrapper = await mountPage()

    expect(wrapper.find('[data-testid="import-empty"]').text()).toContain(
      'Nie masz jeszcze żadnych importów',
    )
    expect(wrapper.findAll('[data-testid="import-job"]')).toHaveLength(0)
  })

  it('tłumaczy statusy jobów na polskie plakietki', async () => {
    importApi.listJobs.mockResolvedValue({
      items: [
        summary({ id: 1, status: 'parsed' }),
        summary({ id: 2, status: 'uploaded' }),
        summary({ id: 3, status: 'failed', error: 'Nie udało się odczytać.' }),
      ],
      total: 3,
    })

    const wrapper = await mountPage()
    const statuses = wrapper.findAll('[data-testid="import-job-status"]').map((node) => node.text())

    expect(statuses).toEqual(['Sparsowany', 'Wgrany', 'Błąd'])
  })

  it('pokazuje komunikat błędu przy jobie zakończonym niepowodzeniem', async () => {
    importApi.listJobs.mockResolvedValue({
      items: [summary({ status: 'failed', error: 'Nie udało się odczytać.' })],
      total: 1,
    })

    const wrapper = await mountPage()

    expect(wrapper.find('[data-testid="import-job-error"]').text()).toBe('Nie udało się odczytać.')
    // Bez raportu nie ma czego rozwijać.
    expect(wrapper.find('[data-testid="import-job-toggle-report"]').exists()).toBe(false)
  })

  it('renderuje raport odczytu z liczbami i sumami kontrolnymi', async () => {
    importApi.listJobs.mockResolvedValue({ items: [summary()], total: 1 })
    const wrapper = await mountPage()

    await wrapper.find('[data-testid="import-job-toggle-report"]').trigger('click')
    await flushPromises()

    expect(importApi.getJob).toHaveBeenCalledWith(1)
    const panel = wrapper.find('[data-testid="import-job-report"]')
    expect(panel.exists()).toBe(true)
    expect(panel.text()).toContain('5 / 10')
    expect(wrapper.find('[data-testid="import-report-match"]').text()).toContain('40 / 85')
    expect(wrapper.find('[data-testid="import-report-match"]').text()).toContain('47%')
    const checksums = wrapper.findAll('[data-testid="import-report-checksums"] li')
    expect(checksums).toHaveLength(3)
    expect(checksums[0]!.text()).toContain('Poniedziałek')
    expect(checksums[0]!.text()).toContain('zgodna')
  })

  it('pokazuje liczbę rzeczy do rozstrzygnięcia, gdy raport ma issues', async () => {
    importApi.listJobs.mockResolvedValue({ items: [summary()], total: 1 })
    importApi.getJob.mockResolvedValue(detail(report({ issues: { blocker: 4, warning: 7 } })))
    const wrapper = await mountPage()

    await wrapper.find('[data-testid="import-job-toggle-report"]').trigger('click')
    await flushPromises()

    const issues = wrapper.find('[data-testid="import-report-issues"]').text()
    expect(issues).toContain('4 blokujące')
    expect(issues).toContain('7 ostrzeżenia')
  })

  it('oznacza rozjazd sumy kontrolnej dnia', async () => {
    importApi.listJobs.mockResolvedValue({ items: [summary()], total: 1 })
    importApi.getJob.mockResolvedValue(
      detail(
        report({
          day_checksums: [{ day: 'Poniedziałek', expected: '2021', computed: '1800', ok: false }],
        }),
      ),
    )
    const wrapper = await mountPage()

    await wrapper.find('[data-testid="import-job-toggle-report"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="import-report-checksums"]').text()).toContain('rozjazd')
  })

  it('sparsowany job prowadzi do ekranu review (BATCH_16)', async () => {
    importApi.listJobs.mockResolvedValue({ items: [summary()], total: 1 })
    const wrapper = await mountPage()

    // Przycisk nawigujący MUSI być linkiem — `as-child` + `RouterLink`
    // (ustalenie review R2; `as="router-link"` renderuje nieznany tag).
    const link = wrapper.find('[data-testid="import-job-review"]')
    expect(link.exists()).toBe(true)
    expect(link.element.tagName.toLowerCase()).toBe('a')
    expect(link.attributes('href')).toBe('/import/jobs/1/review')
  })

  it('rozstrzygnięty job nie prowadzi już do review, tylko mówi, że jest po decyzji', async () => {
    importApi.listJobs.mockResolvedValue({ items: [summary({ status: 'approved' })], total: 1 })
    const wrapper = await mountPage()

    expect(wrapper.find('[data-testid="import-job-review"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="import-job-settled"]').text()).toContain('rozstrzygnięty')
  })
})
