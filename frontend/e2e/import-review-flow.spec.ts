import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { expect, test } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'

import { csrfHeaders } from './cleanup.js'

/**
 * Core flow 4 (08_TESTING §3, karta B16): upload `dieta.pdf` → review →
 * rozstrzygnięcie mapowań → gołąbki na 7 porcji → zatwierdzenie → przepis
 * widoczny w katalogu z poprawnymi wartościami per porcja.
 *
 * Środowisko E2E jest BEZ klucza AI, więc test przechodzi tryb czysto
 * deterministyczny (ADR-011) — przycisk „Zaproponuj z AI" nie ma prawa się
 * pokazać, a flow ma działać w 100%.
 *
 * **Rozstrzygnięcia seedujemy przez API, nie przez UI** (konwencja 08_TESTING
 * §3): kliknięcie 8 pickerów po kolei testowałoby cierpliwość Playwrighta, a
 * nie aplikację. Przez UI idzie to, co jest treścią tego flow: wejście
 * w review, sprawdzenie postępu i blokad oraz samo zatwierdzenie.
 *
 * **Sprzątanie** kasuje przepis i produkty utworzone przez zatwierdzenie
 * (po id z odpowiedzi API — produkty importu nie mają prefiksu E2E, bo ich
 * nazwy pochodzą wprost z jadłospisu). Zatwierdzony JOB zostaje: `DELETE
 * /import/jobs/{id}` świadomie nie przyjmuje statusów rozstrzygniętych
 * (karta B15), a ślad „ten plik wgrano i zatwierdzono" jest wart jednego
 * wiersza. Kolejne przebiegi nie zależą od tej listy — spec rozpoznaje swój
 * job po różnicy id.
 */
const API = '/api/v1'
const PDF_PATH = fileURLToPath(new URL('../../data/source_pdfs/dieta.pdf', import.meta.url))
const GOLABKI = 'Gołąbki bez zawijania'

interface StagedIngredient {
  id: number
  raw_name: string
}

interface StagedRecipe {
  id: number
  name: string
  declared_servings: number | null
  ingredients: StagedIngredient[]
}

interface StagedJob {
  recipes: StagedRecipe[]
  blockers: unknown[]
  ai_available: boolean
}

const cleanup: { jobId: number | null; recipeIds: number[]; productIds: number[] } = {
  jobId: null,
  recipeIds: [],
  productIds: [],
}

test.afterAll(async ({ request }) => {
  const headers = await csrfHeaders(request)
  // Kolejność wymuszona przez FK RESTRICT: przepis trzyma produkty (ADR-012).
  for (const id of cleanup.recipeIds) {
    await request.delete(`${API}/recipes/${id}`, { headers })
  }
  for (const id of cleanup.productIds) {
    await request.delete(`${API}/products/${id}`, { headers })
  }
  // Próba skasowania joba jest CELOWO bezwarunkowa: po zatwierdzeniu wróci 409
  // (statusy rozstrzygnięte są nieusuwalne — karta B15) i tak ma być, ale gdy
  // test padnie WCZEŚNIEJ, ta linia sprząta job sparsowany.
  if (cleanup.jobId !== null) {
    await request.delete(`${API}/import/jobs/${cleanup.jobId}`, { headers })
  }
})

async function jobIds(request: APIRequestContext): Promise<Set<number>> {
  const response = await request.get(`${API}/import/jobs`)
  const body = (await response.json()) as { items: { id: number }[] }
  return new Set(body.items.map((item) => item.id))
}

test('import PDF: review dieta.pdf → gołąbki na 7 porcji → przepis w katalogu', async ({
  page,
  request,
}) => {
  page.on('dialog', (dialog) => dialog.accept())

  // --- upload przez UI ------------------------------------------------------------
  await page.goto('/import')
  await expect(page.getByTestId('import-page')).toBeVisible()
  const before = await jobIds(request)

  await page.getByTestId('import-file-input').setInputFiles({
    name: 'dieta.pdf',
    mimeType: 'application/pdf',
    buffer: readFileSync(PDF_PATH),
  })

  // Czekamy na NOWY job w API, nie na widoczność wiersza: baza deweloperska
  // może już nieść importy z poprzednich przebiegów (zatwierdzonego joba nie
  // da się skasować — patrz nagłówek), więc `import-job` bywa widoczny od razu
  // i asercja przechodziłaby, zanim upload się skończy.
  await expect
    .poll(async () => [...(await jobIds(request))].filter((id) => !before.has(id)).length, {
      timeout: 60_000,
      message: 'upload dieta.pdf nie utworzył nowego importu',
    })
    .toBe(1)

  const fresh = [...(await jobIds(request))].filter((id) => !before.has(id))
  const jobId = fresh[0]!
  cleanup.jobId = jobId
  await expect(page.getByTestId('import-job').first()).toBeVisible({ timeout: 30_000 })

  // --- wejście w review z listy importów -------------------------------------------
  // Link namierzamy po `href` z NASZYM id: w bazie deweloperskiej mogą stać
  // importy z poprzednich przebiegów, więc „pierwszy wiersz" nie jest gwarancją.
  // Klikamy go naprawdę — to jest jedyne wejście w review z listy i ma działać.
  await page.locator(`a[href="/import/jobs/${jobId}/review"]`).click()
  await expect(page.getByTestId('import-review-page')).toBeVisible()
  await expect(page.getByTestId('import-review-filename')).toHaveText('dieta.pdf')
  // Bez klucza API asysta nie istnieje — i tak ma wyglądać (ADR-011).
  await expect(page.getByTestId('import-review-ai')).toHaveCount(0)

  // --- seed rozstrzygnięć przez API -------------------------------------------------
  const headers = await csrfHeaders(request)
  const staged = (await (
    await request.get(`${API}/import/jobs/${jobId}/staged`)
  ).json()) as StagedJob
  const golabki = staged.recipes.find((recipe) => recipe.name === GOLABKI)
  expect(golabki, 'dieta.pdf musi zawierać gołąbki — na nich stoi cały ten flow').toBeTruthy()
  // „Przepis na 7 porcji" czyta już parser (01_PDF_AUDIT §5.1) — review ma to
  // pokazać, a nie kazać wpisywać ponownie.
  expect(golabki!.declared_servings).toBe(7)

  await request.post(`${API}/import/jobs/${jobId}/resolve`, {
    headers,
    data: {
      recipes: staged.recipes
        .filter((recipe) => recipe.id !== golabki!.id)
        .map((recipe) => ({ staged_recipe_id: recipe.id, resolution: 'skip' })),
      ingredients: golabki!.ingredients.map((item) => ({
        ingredient_id: item.id,
        create_new_product: true,
      })),
    },
  })

  // --- zatwierdzenie przez UI --------------------------------------------------------
  await page.reload()
  await expect(page.getByTestId('import-review-page')).toBeVisible()
  await expect(page.getByTestId('import-review-ready')).toBeVisible()
  await expect(page.getByTestId('import-review-approve')).toBeEnabled()

  // Kartę namierzamy po ID dania, nie po tekście: nazwa dania mieszka w POLU
  // (jest edytowalna — errata §9.5), więc `hasText` jej nie widzi.
  await expect(page.getByTestId(`staged-recipe-name-${golabki!.id}`)).toHaveValue(GOLABKI)
  await expect(page.getByTestId(`staged-recipe-declared-${golabki!.id}`)).toContainText('7')

  await page.getByTestId('import-review-approve').click()
  await expect(page.getByTestId('import-review-summary')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId('summary-recipes')).toHaveText('1')

  // --- przepis w katalogu z wartościami per porcja -------------------------------------
  const detail = (await (await request.get(`${API}/import/jobs/${jobId}/staged`)).json()) as {
    job: { status: string }
  }
  expect(detail.job.status).toBe('approved')

  const recipes = (await (
    await request.get(`${API}/recipes`, { params: { q: GOLABKI, limit: 5, offset: 0 } })
  ).json()) as { items: { id: number; name: string; base_servings: number }[] }
  const created = recipes.items.find((item) => item.name === GOLABKI)
  expect(created, 'zatwierdzenie ma utworzyć przepis o nazwie z jadłospisu').toBeTruthy()
  cleanup.recipeIds.push(created!.id)
  expect(created!.base_servings).toBe(7)

  const products = (await (
    await request.get(`${API}/products`, { params: { limit: 200, offset: 0 } })
  ).json()) as { items: { id: number; name: string }[] }
  const names = new Set(golabki!.ingredients.map((item) => item.raw_name))
  cleanup.productIds = products.items.filter((item) => names.has(item.name)).map((item) => item.id)
  expect(cleanup.productIds.length).toBe(names.size)

  await page.getByTestId('summary-go-to-recipes').click()
  await expect(page.getByTestId('przepisy-page')).toBeVisible()
  await page.getByTestId('recipes-search').fill(GOLABKI)
  await expect(page.getByTestId('recipes-list')).toContainText(GOLABKI)
})
