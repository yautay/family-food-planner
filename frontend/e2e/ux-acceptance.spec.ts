import fs from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

import { expect, test, type Locator, type Page } from '@playwright/test'

import type { components } from '../src/api/generated.js'
import { EMPTY_STATE } from './auth-state.js'
import { reserveLoginAttempt } from './login-budget.js'
import { fillSecretPassword } from './secret-password.js'
import { PwaApi } from './ux-pwa-native-api.js'

test.use({ storageState: EMPTY_STATE, trace: 'off', video: 'off', screenshot: 'off' })

test('UX11: 320 px, tekst 200%, etykiety i naturalny fokus edytora', async ({
  page,
  baseURL,
}, testInfo) => {
  test.skip(process.env.UX_ACCEPTANCE !== '1', 'Jawny opt-in UX_ACCEPTANCE=1.')
  test.setTimeout(180_000)
  if (!baseURL || !['localhost', '127.0.0.1', '[::1]'].includes(new URL(baseURL).hostname))
    throw new Error('Odbiór UX11 jest dozwolony tylko na localhost.')
  const password = process.env.UX_BASELINE_PASSWORD
  if (!password) throw new Error('Brak hasła lokalnego fixture UX00.')
  const manifest: { prefix: string; complete: boolean; ids: Record<string, number> } = JSON.parse(
    await fs.readFile(
      fileURLToPath(new URL('../../backend/data/ux-baseline/manifest.json', import.meta.url)),
      'utf8',
    ),
  )
  expect(manifest.prefix).toBe('UX00 kontrakty v1')
  expect(manifest.complete).toBe(true)
  const id = (key: string): number => {
    const value = manifest.ids[key]
    if (!Number.isInteger(value) || value! <= 0) throw new Error(`Brak ID fixture: ${key}`)
    return value!
  }
  await page.goto('/login')
  await page.getByTestId('login-email').fill('ux00-a1@example.com')
  await fillSecretPassword(page.getByTestId('login-password'), password)
  await reserveLoginAttempt(baseURL, testInfo)
  await page.getByTestId('login-submit').click()
  await expect(page).toHaveURL(/\/plan-dnia/)
  const api = new PwaApi(page.context(), baseURL)
  const meResponse = await api.get('/api/v1/auth/me')
  expect(meResponse.status()).toBe(200)
  expect((await meResponse.json<components['schemas']['CurrentUser']>()).id).toBe(id('user-a1'))
  const failures: number[] = []
  page.on('response', (response) => {
    if (new URL(response.url()).pathname.startsWith('/api/v1/') && !response.ok())
      failures.push(response.status())
  })
  const metrics: unknown[] = []
  type Box = { x: number; y: number; width: number; height: number }
  const overlap = (first: Box, second: Box): boolean =>
    Math.min(first.x + first.width, second.x + second.width) > Math.max(first.x, second.x) + 1 &&
    Math.min(first.y + first.height, second.y + second.height) > Math.max(first.y, second.y) + 1
  const inkBox = async (locator: Locator): Promise<Box> =>
    locator.evaluate((element) => {
      const range = element.ownerDocument.createRange()
      range.selectNodeContents(element)
      const rect = range.getBoundingClientRect()
      return { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
    })
  async function prepare(target: Page, scale: number): Promise<void> {
    await target.locator('html').evaluate(async (element, factor) => {
      element.style.fontSize = factor === 2 ? '200%' : ''
      await element.ownerDocument.fonts.ready
      // The tooling tsconfig omits DOM globals; these are browser image methods.
      const images = Array.from(element.ownerDocument.images) as {
        loading: string
        decode(): Promise<void>
      }[]
      await Promise.all(
        images.map(async (image) => {
          image.loading = 'eager'
          await image.decode()
        }),
      )
    }, scale)
  }
  async function capture(label: string): Promise<void> {
    await testInfo.attach(`${label}.png`, {
      body: await page.screenshot({ fullPage: true, animations: 'disabled', caret: 'hide' }),
      contentType: 'image/png',
    })
  }
  const screens = [
    ['day', '/plan-dnia/2029-06-06', 'plan-add-meal', '/plan/days'],
    ['week', '/tydzien/2029-06-04', 'week-grid', '/plan/days'],
    ['recipes', '/przepisy', `recipe-open-${id('recipe-0')}`, '/recipes'],
    ['recipe', `/przepisy/${id('recipe-0')}`, 'recipe-name', `/recipes/${id('recipe-0')}`],
    ['editor', `/przepisy/${id('recipe-0')}/edytuj`, 'recipe-name', `/recipes/${id('recipe-0')}`],
    ['shopping', '/zakupy', 'shopping-catalog-list', '/shopping/lists'],
    [
      'list',
      `/zakupy/listy/${id('list-plain')}`,
      'lista-nazwa',
      `/shopping/lists/${id('list-plain')}`,
    ],
    ['pantry', '/spizarnia', 'pantry-list', '/pantry'],
    [
      'summary',
      '/statystyki?from=2029-06-04&to=2029-06-10&selectedDate=2029-06-04',
      'stats-chart-kcal',
      '/stats/daily',
    ],
    ['products', '/produkty', `product-card-${id('product-0')}`, '/products'],
    ['settings', '/ustawienia', 'profiles-list', '/households/my/profiles'],
  ] as const
  // Root-font reflow tests text enlargement; this is not native browser zoom.
  for (const [width, scale] of [
    [320, 1],
    [1024, 2],
  ] as const) {
    await page.setViewportSize({ width, height: 900 })
    for (const [label, route, readyId, endpoint] of screens) {
      const loaded = page.waitForResponse(
        (response) =>
          new URL(response.url()).pathname === `/api/v1${endpoint}` &&
          response.request().method() === 'GET',
      )
      await page.goto(route)
      expect((await loaded).ok()).toBe(true)
      await expect(page.getByTestId(readyId)).toBeVisible()
      await prepare(page, scale)
      await expect(page.locator('[role="alert"]')).toHaveCount(0)
      const geometry = await page.locator('html').evaluate((element) => ({
        width: element.ownerDocument.defaultView!.innerWidth,
        scroll: element.scrollWidth,
        fontSize: element.ownerDocument.defaultView!.getComputedStyle(element).fontSize,
      }))
      const overflow = await page.locator('html').evaluate((element) => {
        const candidates = Array.from(element.querySelectorAll('main *')) as {
          tagName: string
          getAttribute(name: string): string | null
          getBoundingClientRect(): { x: number; right: number; width: number }
        }[]
        return candidates
          .map((candidate) => ({
            tag: candidate.tagName,
            testId: candidate.getAttribute('data-testid'),
            class: candidate.getAttribute('class'),
            x: candidate.getBoundingClientRect().x,
            right: candidate.getBoundingClientRect().right,
          }))
          .filter(
            (candidate) => candidate.right > element.ownerDocument.defaultView!.innerWidth + 1,
          )
      })
      const controls = page.locator(
        'main input:not([type="hidden"]), main select, main textarea, main button',
      )
      let labelled = 0
      for (const control of await controls.all()) {
        if (!(await control.isVisible())) continue
        await expect(control).toHaveAccessibleName(/\S/)
        labelled += 1
      }
      const layoutProblems: string[] = []
      const filterIds =
        label === 'recipes'
          ? ['recipes-search']
          : label === 'products'
            ? ['products-search', 'products-category-filter']
            : label === 'pantry'
              ? ['pantry-search', 'pantry-category-filter', 'pantry-sort']
              : label === 'shopping'
                ? ['zakupy-date-from', 'zakupy-date-to']
                : []
      const filterMetrics = []
      for (const filterId of filterIds) {
        const filter = await page.getByTestId(filterId).evaluate((element) => {
          const style = element.ownerDocument.defaultView!.getComputedStyle(element)
          const isDate = element.getAttribute('type') === 'date'
          const selected = isDate
            ? '99/99/9999'
            : element.tagName === 'SELECT'
              ? (element.querySelector('option:checked')?.textContent?.trim() ?? '')
              : (element.getAttribute('placeholder') ?? '')
                  .trim()
                  .split(/\s+/)
                  .slice(0, 2)
                  .join(' ')
          const canvas = element.ownerDocument.createElement('canvas')
          const context = canvas.getContext('2d')!
          context.font = style.font
          return {
            width: element.getBoundingClientRect().width,
            needed:
              context.measureText(selected).width +
              parseFloat(style.paddingLeft) +
              parseFloat(style.paddingRight) +
              (isDate ? 24 : element.tagName === 'SELECT' ? 16 : 0),
            textLength: selected.length,
          }
        })
        filterMetrics.push({ filterId, ...filter })
        if (filter.width + 1 < filter.needed)
          layoutProblems.push(`Nieczytelna szerokość filtra: ${filterId}`)
      }
      for (const decoration of await page.getByTestId('header-decoration').all()) {
        if (!(await decoration.isVisible())) continue
        const motifBox = await decoration.boundingBox()
        for (const text of await decoration
          .locator('xpath=ancestor::header[1]')
          .locator('h1,p')
          .all()) {
          const textBox = await text.boundingBox()
          if (motifBox && textBox && overlap(motifBox, textBox))
            layoutProblems.push('Dekoracja nakłada się na tekst nagłówka')
        }
      }
      if (label === 'recipes') {
        for (const button of await page.locator('[data-testid^="recipe-plan-"]').all()) {
          const buttonBox = await button.boundingBox()
          const contentBox = await inkBox(button)
          const cardBox = await button.locator('xpath=ancestor::article[1]').boundingBox()
          if (
            buttonBox &&
            cardBox &&
            (buttonBox.x < cardBox.x - 1 ||
              buttonBox.x + buttonBox.width > cardBox.x + cardBox.width + 1)
          )
            layoutProblems.push('Zaplanuj wychodzi poza przycinaną kartę przepisu')
          if (
            buttonBox &&
            (contentBox.x < buttonBox.x - 1 ||
              contentBox.x + contentBox.width > buttonBox.x + buttonBox.width + 1)
          )
            layoutProblems.push('Tekst lub ikona Zaplanuj wychodzi poza przycisk')
        }
      }
      if (label === 'day') {
        const dates = []
        for (const button of await page.getByTestId('plan-week').locator('button').all())
          dates.push(await button.boundingBox())
        for (let first = 0; first < dates.length; first += 1)
          for (let second = first + 1; second < dates.length; second += 1)
            if (dates[first] && dates[second] && overlap(dates[first]!, dates[second]!))
              layoutProblems.push('Przyciski dni nakładają się na siebie')
        for (const tile of await page.locator('li[data-testid^="plan-tile-"]').all()) {
          const tileBox = await tile.boundingBox()
          for (const text of await tile.locator('span,strong').all()) {
            const textBox = await inkBox(text)
            if (
              tileBox &&
              (textBox.x < tileBox.x - 1 ||
                textBox.x + textBox.width > tileBox.x + tileBox.width + 1)
            )
              layoutProblems.push('Nazwa lub wartość makro wychodzi poza własną kolumnę')
          }
        }
      }
      if (label === 'shopping') {
        for (const row of await page.locator('li[data-testid^="shopping-list-"]').all()) {
          const linkBox = await row.locator('[data-testid^="shopping-list-link-"]').boundingBox()
          for (const text of await row.locator('h3,p').all()) {
            const textBox = await text.boundingBox()
            if (linkBox && textBox && overlap(linkBox, textBox))
              layoutProblems.push('Otwórz listę nakłada się na opis zapisanej listy')
          }
        }
      }
      if (label === 'settings') {
        for (const row of await page.locator('[data-testid^="profile-row-"]').all()) {
          const name = row.locator('p').first()
          expect(await name.innerText(), 'Fixture ma krótkie, jednowyrazowe imiona').toMatch(
            /^\S+$/u,
          )
          const lines = await name.evaluate(
            (element) =>
              element.getBoundingClientRect().height /
              parseFloat(element.ownerDocument.defaultView!.getComputedStyle(element).lineHeight),
          )
          if (lines > 2.01)
            layoutProblems.push('Krótkie imię profilu rozpada się na ponad dwa wiersze')
        }
      }
      await capture(`ux11-${label}-${width}-text${scale}`)
      metrics.push({
        label,
        width,
        scale,
        geometry,
        labelled,
        overflow,
        layoutProblems,
        filterMetrics,
      })
      await testInfo.attach(`ux11-geometry-${label}-${width}-text${scale}.json`, {
        body: Buffer.from(
          JSON.stringify({ geometry, overflow, layoutProblems, filterMetrics }, null, 2),
        ),
        contentType: 'application/json',
      })
      expect(geometry.fontSize).toBe(scale === 2 ? '32px' : '16px')
      expect
        .soft(geometry.scroll, `${label}: przepełnienie dokumentu`)
        .toBeLessThanOrEqual(width + 1)
      expect(failures, 'Błędy rzeczywistych API').toEqual([])
      expect.soft(layoutProblems, `${label}: treść i główne akcje pozostają czytelne`).toEqual([])
    }
  }
  for (const width of [320, 390, 1024]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto(`/przepisy/${id('recipe-0')}/edytuj`)
    await expect(page.getByTestId('recipe-name')).toBeVisible()
    await prepare(page, 1)
    await page.getByTestId('recipe-extras').locator('summary').focus()
    await page.keyboard.press('Enter')
    await expect(page.getByTestId('recipe-difficulty')).toBeVisible()
    await page.getByTestId('recipe-name').focus()
    const visited: unknown[] = []
    let reachedSave = false
    for (let index = 0; index < 60; index += 1) {
      // Allow native focus scrolling and one scoped focusin animation-frame handler.
      await page.locator('html').evaluate(
        (element) =>
          new Promise<void>((resolve) => {
            element.ownerDocument.defaultView!.requestAnimationFrame(() => resolve())
          }),
      )
      const focus = await page.locator('html').evaluate((element) => {
        const doc = element.ownerDocument
        const active = doc.activeElement
        if (!active) return null
        const rect = active.getBoundingClientRect()
        const x = Math.max(0, Math.min(doc.defaultView!.innerWidth - 1, rect.x + rect.width / 2))
        const y = Math.max(0, Math.min(doc.defaultView!.innerHeight - 1, rect.y + rect.height / 2))
        const hit = doc.elementFromPoint(x, y)
        const style = doc.defaultView!.getComputedStyle(active)
        return {
          id: active.getAttribute('data-testid') || active.id || active.tagName,
          y: rect.y,
          bottom: rect.bottom,
          covered: !hit || (!active.contains(hit) && !hit.contains(active)),
          inViewport: rect.bottom > 0 && rect.top < doc.defaultView!.innerHeight,
          outline: style.outlineStyle,
          shadow: style.boxShadow,
        }
      })
      visited.push(focus)
      if (!focus || focus.covered || !focus.inViewport) {
        await testInfo.attach(`ux11-obscured-${width}-${index}.png`, {
          body: await page.screenshot({ fullPage: false, animations: 'disabled', caret: 'hide' }),
          contentType: 'image/png',
        })
      }
      if (focus?.id === 'recipe-submit') {
        reachedSave = true
        break
      }
      await page.keyboard.press('Tab')
    }
    await capture(`ux11-editor-keyboard-${width}`)
    metrics.push({ width, keyboard: visited })
    await testInfo.attach(`keyboard-${width}.json`, {
      body: Buffer.from(JSON.stringify(visited, null, 2)),
      contentType: 'application/json',
    })
    expect.soft(reachedSave, 'Naturalny Tab dochodzi do Zapisz').toBe(true)
    expect
      .soft(
        visited.filter((value) => {
          const focus = value as { covered: boolean; inViewport: boolean } | null
          return !focus || focus.covered || !focus.inViewport
        }),
        'Fokus w edytorze pozostaje widoczny',
      )
      .toEqual([])
  }
  await testInfo.attach('ux11-metrics.json', {
    body: Buffer.from(JSON.stringify(metrics, null, 2)),
    contentType: 'application/json',
  })
})
