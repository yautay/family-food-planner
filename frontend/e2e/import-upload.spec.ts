import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { expect, test } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'

import { csrfHeaders } from './cleanup.js'

/**
 * Smoke importu PDF (karta B15 §Tests): login → upload `dieta.pdf` → job
 * `Sparsowany` → raport z liczbami z 01_PDF_AUDIT.
 *
 * Sprzątanie NIE idzie przez `cleanupE2eData`: importy nie mają nazw, po
 * których dałoby się je dopasować prefiksem (`filename` to nazwa pliku
 * użytkownika), więc kasujemy dokładnie te joby, które ten spec wgrał — po id
 * z odpowiedzi API. Kasowanie „wszystkich importów" zabrałoby dane, które
 * mógł zostawić człowiek pracujący na tej samej bazie deweloperskiej.
 *
 * `dieta.pdf` jest w repozytorium (`data/source_pdfs/`) i to ten sam plik,
 * na którym stoją testy korpusowe backendu — liczby poniżej pochodzą z audytu,
 * nie z tego, co akurat wyszło.
 */
const API = '/api/v1'
const PDF_PATH = fileURLToPath(new URL('../../data/source_pdfs/dieta.pdf', import.meta.url))

/** Liczby dla `dieta.pdf` z 01_PDF_AUDIT §1: 3 dni × 4 posiłki, 13 dań. */
const EXPECTED_MEALS = 12
const EXPECTED_RECIPES = 13

const createdJobIds: number[] = []

async function removeJob(request: APIRequestContext, id: number): Promise<void> {
  const headers = await csrfHeaders(request)
  await request.delete(`${API}/import/jobs/${id}`, { headers })
}

test.afterAll(async ({ request }) => {
  for (const id of createdJobIds) {
    await removeJob(request, id)
  }
})

test('import PDF: wgranie jadłospisu daje job „Sparsowany" i raport odczytu', async ({
  page,
  request,
}) => {
  await page.goto('/import')
  await expect(page.getByTestId('import-page')).toBeVisible()

  const before = await request.get(`${API}/import/jobs`)
  const idsBefore = new Set(
    ((await before.json()) as { items: { id: number }[] }).items.map((item) => item.id),
  )

  await page.getByTestId('import-file-input').setInputFiles({
    name: 'dieta.pdf',
    mimeType: 'application/pdf',
    buffer: readFileSync(PDF_PATH),
  })

  const job = page.getByTestId('import-job').first()
  await expect(job).toBeVisible({ timeout: 30_000 })
  await expect(job.getByTestId('import-job-status')).toHaveText('Sparsowany')
  await expect(job.getByTestId('import-job-filename')).toHaveText('dieta.pdf')

  // Raport otwiera się sam po uploadzie — to jedyna treść, po którą się tu wchodzi.
  const report = job.getByTestId('import-job-report')
  await expect(report).toBeVisible()
  await expect(job.getByTestId('import-job-numbers')).toContainText(`${EXPECTED_MEALS}`)
  await expect(job.getByTestId('import-job-numbers')).toContainText(`${EXPECTED_RECIPES}`)

  // Gołąbki niosą „Przepis na 7 porcji", więc ten plik nie ma ani jednego
  // blockera — dokładnie to sprawdza `test_golabki_multi_portion_declared`.
  await expect(report.getByTestId('import-report-issues')).toHaveText('Nic nie wymaga decyzji.')
  // Trzy dni, wszystkie sumy kontrolne zgodne (01_PDF_AUDIT §4).
  await expect(report.getByTestId('import-report-checksums').locator('li')).toHaveCount(3)
  await expect(report.getByTestId('import-report-checksums')).not.toContainText('rozjazd')

  // Zakres B15 kończy się na odczycie — strona ma to mówić wprost.
  await expect(report).toContainText('Review i zatwierdzanie — wkrótce')

  const after = await request.get(`${API}/import/jobs`)
  const fresh = ((await after.json()) as { items: { id: number }[] }).items.filter(
    (item) => !idsBefore.has(item.id),
  )
  expect(fresh).toHaveLength(1)
  createdJobIds.push(fresh[0]!.id)
})
