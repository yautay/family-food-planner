import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { expect, test, type Page } from '@playwright/test'

import type { components } from '../src/api/generated.js'
import { EMPTY_STATE } from './auth-state.js'
import { reserveLoginAttempt } from './login-budget.js'

// Tylko jawny opt-in. Zwykły E2E zachowuje wszystkie swoje wymagane scenariusze.
const enabled = process.env.UX_VISUAL === '1'
const dataDir = fileURLToPath(new URL('../../backend/data/ux-baseline/', import.meta.url))
const prefix = 'UX00 kontrakty v1'
type ListDetail = components['schemas']['ShoppingListDetailRead']

test.use({ storageState: EMPTY_STATE, trace: 'off', video: 'off', screenshot: 'off' })

function widths(): number[] {
  const result = (process.env.UX_VISUAL_WIDTHS ?? '390,1440').split(',').map(Number)
  if (result.some((width) => !Number.isInteger(width) || width < 320 || width > 2560)) {
    throw new Error('UX_VISUAL_WIDTHS: podaj szerokości 320–2560, oddzielone przecinkami.')
  }
  return [...new Set(result)]
}

async function ready(page: Page, testId: string): Promise<void> {
  await expect(page.getByTestId(testId)).toBeVisible()
  await expect(page.locator('[role="alert"]')).toHaveCount(0)
  // tsconfig.node nie włącza DOM; skrypt działa wyłącznie w prawdziwej stronie.
  await page.evaluate(`(async () => {
    await document.fonts.ready
    await Promise.all(
      Array.from(document.images).map(async (image) => {
        if (image.loading === 'lazy') image.loading = 'eager'
        await image.decode()
      }),
    )
  })()`)
}

test('UX00: prawdziwy interfejs, telefon/desktop i prywatna lista offline', async ({
  page,
  baseURL,
  browser,
}, testInfo) => {
  test.skip(!enabled, 'Wymaga jawnego UX_VISUAL=1 i zestawu task ux-baseline.')
  test.setTimeout(180_000)
  if (!baseURL || !['localhost', '127.0.0.1', '[::1]'].includes(new URL(baseURL).hostname)) {
    throw new Error('Zrzuty UX00 są dozwolone wyłącznie na localhost.')
  }
  const password = process.env.UX_BASELINE_PASSWORD
  if (!password) throw new Error('Brak lokalnego UX_BASELINE_PASSWORD.')
  // To format lokalnego narzędzia, nie ręcznie zadeklarowana odpowiedź HTTP.
  const manifest: { prefix: string; complete: boolean; ids: Record<string, number> } = JSON.parse(
    await fs.readFile(path.join(dataDir, 'manifest.json'), 'utf8'),
  )
  if (manifest.prefix !== prefix || !manifest.complete) {
    throw new Error('Zestaw UX00 nie został ukończony i zweryfikowany.')
  }
  const id = (key: string): number => {
    const value = manifest.ids[key]
    if (!Number.isInteger(value) || value <= 0) throw new Error(`Brak ID UX00: ${key}`)
    return value
  }
  await page.goto('/login')
  await page.getByTestId('login-email').fill('ux00-a1@example.com')
  await page.getByTestId('login-password').fill(password)
  await reserveLoginAttempt(baseURL, testInfo)
  await page.getByTestId('login-submit').click()
  await expect(page).toHaveURL(/\/plan-dnia/)
  const meResponse = await page.request.get('/api/v1/auth/me')
  expect(meResponse.ok()).toBeTruthy()
  const me: components['schemas']['CurrentUser'] = await meResponse.json()
  expect(me.id).toBe(id('user-a1'))
  expect(me.email).toBe('ux00-a1@example.com')
  expect(me.household?.name).toBe(`${prefix} — Dom A`)
  const read = async <T>(route: string): Promise<T> => {
    const response = await page.request.get(`/api/v1${route}`)
    expect(response.ok(), `Odczyt danych odniesienia: ${route}`).toBeTruthy()
    return response.json()
  }
  const product = await read<components['schemas']['ProductDetail']>(`/products/${id('product-0')}`)
  const recipes = await Promise.all(
    [0, 1, 2].map((index) =>
      read<components['schemas']['RecipeDetail']>(`/recipes/${id(`recipe-${index}`)}`),
    ),
  )
  const days = await Promise.all(
    [4, 5, 6].map((day) => read<components['schemas']['DayRead']>(`/plan/days/2029-06-0${day}`)),
  )
  for (const day of days) expect(day.meals).toHaveLength(1)
  const apiFailures: string[] = []
  page.on('response', (response) => {
    if (new URL(response.url()).pathname.startsWith('/api/v1/') && !response.ok()) {
      // Bez URL-i/tokenów ani payloadów. Nie ukrywaj błędu odświeżenia za cache'em.
      apiFailures.push(`HTTP ${response.status()}`)
    }
  })
  const open = async (route: string, apiPaths: string[]): Promise<void> => {
    const responses = apiPaths.map((apiPath) =>
      page.waitForResponse(
        (response) =>
          new URL(response.url()).pathname === `/api/v1${apiPath}` &&
          response.request().method() === 'GET',
      ),
    )
    const results = await Promise.all([...responses, page.goto(route)])
    for (const response of results) expect(response?.ok()).toBeTruthy()
  }
  const output = path.join(dataDir, 'screenshots')
  await fs.mkdir(output, { recursive: true })
  const capture = async (target: Page, width: number, label: string): Promise<void> => {
    expect(apiFailures, 'Błędy prawdziwych żądań UI, również przy danych w cache').toEqual([])
    const file = path.join(output, `${width}-${label}.png`)
    await target.screenshot({ path: file, fullPage: true, animations: 'disabled', caret: 'hide' })
    await testInfo.attach(`${width}-${label}`, { path: file, contentType: 'image/png' })
    // Długi katalog skaluje pełny PNG do nieczytelnej miniatury; zachowaj też pierwszy ekran.
    if (['recipes', 'recipe-photo', 'recipe-no-photo', 'recipe-global'].includes(label)) {
      const viewportFile = path.join(output, `${width}-${label}-viewport.png`)
      await target.screenshot({
        path: viewportFile,
        fullPage: false,
        animations: 'disabled',
        caret: 'hide',
      })
      await testInfo.attach(`${width}-${label}-viewport`, {
        path: viewportFile,
        contentType: 'image/png',
      })
    }
  }
  const detail = async (): Promise<ListDetail> => {
    const response = await page.request.get(`/api/v1/shopping/lists/${id('list-plain')}`)
    expect(response.ok()).toBeTruthy()
    const result: ListDetail = await response.json()
    expect(result.name).toBe(`${prefix} — lista offline`)
    return result
  }
  const list = await detail()
  for (const width of widths()) {
    await page.setViewportSize({ width, height: 900 })
    for (const [label, route, testId, contentId, apiPaths] of [
      ['day-no-split', '/plan-dnia/2029-06-04', 'plan-dnia-page', 'plan-add-meal', ['/plan/days']],
      ['day-partial', '/plan-dnia/2029-06-05', 'plan-dnia-page', 'plan-add-meal', ['/plan/days']],
      ['day-full', '/plan-dnia/2029-06-06', 'plan-dnia-page', 'plan-add-meal', ['/plan/days']],
      ['day-empty', '/plan-dnia/2029-06-10', 'plan-dnia-page', 'plan-empty', ['/plan/days']],
      [
        'recipes',
        '/przepisy',
        'przepisy-page',
        `recipe-open-${id('recipe-0')}`,
        ['/recipes', '/tags'],
      ],
      [
        'recipe-photo',
        `/przepisy/${id('recipe-0')}`,
        'przepis-szczegol-page',
        'recipe-name',
        [`/recipes/${id('recipe-0')}`],
      ],
      [
        'recipe-no-photo',
        `/przepisy/${id('recipe-1')}`,
        'przepis-szczegol-page',
        'recipe-name',
        [`/recipes/${id('recipe-1')}`],
      ],
      [
        'recipe-global',
        `/przepisy/${id('recipe-2')}`,
        'przepis-szczegol-page',
        'recipe-name',
        [`/recipes/${id('recipe-2')}`],
      ],
      ['week', '/tydzien/2029-06-04', 'plan-tygodnia-page', 'week-grid', ['/plan/days']],
      [
        'shopping',
        '/zakupy',
        'zakupy-page',
        'zakupy-form',
        ['/shopping/round-configs', '/shopping/lists'],
      ],
      [
        'shopping-list',
        `/zakupy/listy/${id('list-plain')}`,
        'lista-zakupowa-page',
        'lista-nazwa',
        [`/shopping/lists/${id('list-plain')}`, '/stores'],
      ],
      ['pantry', '/spizarnia', 'spizarnia-page', 'pantry-list', ['/pantry']],
      [
        'recipe-editor',
        `/przepisy/${id('recipe-0')}/edytuj`,
        'przepis-edytor-page',
        'recipe-photo-preview',
        [
          `/recipes/${id('recipe-0')}`,
          '/tags',
          `/products/${id('product-0')}/unit-weights`,
          `/products/${id('product-1')}/unit-weights`,
          `/products/${id('product-2')}/unit-weights`,
        ],
      ],
      ['summary', '/statystyki', 'statystyki-page', 'stats-preset-custom', ['/stats/daily']],
      ['products', '/produkty', 'produkty-page', `product-card-${id('product-0')}`, ['/products']],
      [
        'settings',
        '/ustawienia',
        'ustawienia-page',
        'profiles-list',
        ['/households/my', '/households/my/profiles', '/goals', '/stores'],
      ],
      [
        'product-form',
        `/produkty/${id('product-0')}/edytuj`,
        'produkt-form-page',
        'product-name',
        [`/products/${id('product-0')}`, '/categories', '/retail-products'],
      ],
    ] as const) {
      await open(route, [...apiPaths])
      await expect(page.getByTestId(contentId)).toBeVisible()
      if (label === 'week') {
        for (const day of days) {
          for (const meal of day.meals) {
            await expect(page.getByTestId(`week-meal-${meal.id}`)).toContainText(meal.name)
            await expect(page.getByTestId(`week-day-empty-${day.day}`)).toHaveCount(0)
          }
        }
      }
      if (label.startsWith('day-') && label !== 'day-empty') {
        const day = days.find((entry) => route.endsWith(entry.day))!
        for (const meal of day.meals) {
          await expect(page.getByTestId(`meal-name-${meal.id}`)).toHaveText(meal.name)
          for (const item of meal.items)
            await expect(page.getByTestId(`plan-item-${item.id}`)).toBeVisible()
        }
      }
      if (label === 'settings') {
        await expect(page.getByTestId('household-name')).toHaveText(`${prefix} — Dom A`)
        await expect(page.locator('[data-testid^="profile-row-"]')).toHaveCount(3)
        for (const [index, name] of ['Łucja', 'Michał', 'Żaneta'].entries()) {
          await expect(page.getByTestId(`profile-row-${id(`profile-${index}`)}`)).toContainText(
            name,
          )
        }
        await expect(page.getByTestId(`goal-row-${id('goal')}`)).toBeVisible()
        await expect(page.getByTestId(`store-name-${id('store-0')}`)).toHaveText(
          `${prefix} — Sklep 1`,
        )
      }
      if (label === 'product-form') {
        await expect(page.getByTestId('product-name')).toHaveValue(product.name)
        await expect(page.getByTestId('unit-weights-list')).toContainText('łyżka')
      }
      if (label === 'recipe-editor') {
        await expect(page.getByTestId('recipe-name')).toHaveValue(recipes[0]!.name)
        await expect(page.locator('[data-testid^="ingredient-row-"]')).toHaveCount(
          recipes[0]!.ingredients.length,
        )
      } else if (label.startsWith('recipe-')) {
        const recipe = recipes.find((entry) => route.endsWith(`/${entry.id}`))!
        await expect(page.getByTestId('recipe-name')).toHaveText(recipe.name)
        await expect(page.locator('[data-testid^="recipe-ingredient-"]')).toHaveCount(
          recipe.ingredients.length,
        )
      }
      if (label === 'pantry') {
        await expect(page.getByTestId(`pantry-name-${id('pantry-0')}`)).toHaveText(product.name)
      }
      if (label === 'shopping-list') {
        await expect(page.getByTestId('lista-nazwa')).toHaveText(list.name)
        await expect(page.locator('[data-testid^="shopping-check-"]')).toHaveCount(
          list.sections.flatMap((section) => section.items).length,
        )
      }
      if (label === 'shopping') {
        await expect(page.getByTestId('shopping-catalog-list')).toBeVisible()
        await expect(page.locator('[data-testid^="round-config-"]').first()).toBeAttached()
        await page.getByTestId('zakupy-date-from').fill('2029-06-04')
        await page.getByTestId('zakupy-date-to').fill('2029-06-06')
      }
      if (label === 'summary') {
        const loaded = page.waitForResponse((response) => {
          const url = new URL(response.url())
          return (
            url.pathname === '/api/v1/stats/daily' &&
            url.searchParams.get('from') === '2029-06-04' &&
            url.searchParams.get('to') === '2029-06-10'
          )
        })
        await page.getByTestId('stats-preset-custom').click()
        await page.getByTestId('stats-from').fill('2029-06-04')
        await page.getByTestId('stats-to').fill('2029-06-10')
        expect((await loaded).ok()).toBeTruthy()
        await expect(page.getByTestId('stats-days')).toHaveText(
          '3 z 7 dni ma plan — średnie liczymy tylko z nich.',
        )
        await expect(page.getByTestId('stats-chart-kcal')).toBeVisible()
      }
      await ready(page, testId)
      await capture(page, width, label)
      if (label === 'shopping') {
        await page.getByTestId('zakupy-round-settings').locator('summary').click()
        await expect(page.locator('[data-testid^="round-config-"]').first()).toBeVisible()
        await capture(page, width, 'shopping-round-settings')
      }
    }
    // Własna lista: hydratacja online, odcięcie sieci, realna kolejka, powrót i GET.
    // Reload offline wymaga zbudowanego PWA; Vite nie ma shella w cache (ADR-009).
    await page.goto(`/zakupy/listy/${id('list-plain')}`)
    await ready(page, 'lista-zakupowa-page')
    const item = list.sections.flatMap((section) => section.items).find((row) => !row.received_at)
    expect(item).toBeDefined()
    const checkbox = page.getByTestId(`shopping-check-${item!.id}`)
    await expect(checkbox).toBeVisible()
    const original = await checkbox.isChecked()
    try {
      await page.context().setOffline(true)
      await expect(page.getByTestId('offline-banner')).toContainText('Tryb offline')
      await checkbox.setChecked(!original)
      await capture(page, width, 'shopping-offline')
      await page.context().setOffline(false)
      await expect
        .poll(async () => {
          const current = await detail()
          return current.sections
            .flatMap((section) => section.items)
            .find((row) => row.id === item!.id)?.checked
        })
        .toBe(!original)
      await page.reload()
      await expect(checkbox).toBeChecked({ checked: !original })
    } finally {
      await page.context().setOffline(false)
      await checkbox.setChecked(original)
      await expect
        .poll(async () => {
          const current = await detail()
          return current.sections
            .flatMap((section) => section.items)
            .find((row) => row.id === item!.id)?.checked
        })
        .toBe(original)
    }
    // URL tokenu pozostaje tylko w pamięci. Brak trace/video i otwartego dialogu share.
    const share = list.share
    expect(share?.url).toMatch(/^\/l\//)
    const publicContext = await browser.newContext({ viewport: { width, height: 900 } })
    try {
      const publicPage = await publicContext.newPage()
      await publicPage.goto(new URL(share!.url, baseURL).href)
      await expect(publicPage.locator('[data-testid^="shopping-check-"]').first()).toBeVisible()
      await ready(publicPage, 'public-list-page')
      await capture(publicPage, width, 'shopping-public')
      await publicPage.goto(new URL('/login', baseURL).href)
      await ready(publicPage, 'login-submit')
      await capture(publicPage, width, 'login')
    } finally {
      await publicContext.close()
    }
  }
})
