import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import type { StagedJobResponse } from '@/api/pdfImport'
import { routes } from '@/router'

import ImportReviewPage from './ImportReviewPage.vue'

/**
 * Ekran review importu — Acceptance Criteria 1, 5 i 8 karty B16.
 *
 * Trzy rzeczy, których pilnuje ten plik:
 *
 * 1. **Przycisk „Zatwierdź" jest nieczynny, dopóki serwer zgłasza blokady** —
 *    i mówi, KTÓRE to blokady. Lista pochodzi z odpowiedzi, nie z sumowania
 *    w UI, więc tooltip nie może się rozjechać z tym, co odrzuci `approve`.
 * 2. **Przyciski AI znikają bez klucza** (`ai_available: false`) — tryb
 *    deterministyczny z ADR-011 ma wyglądać na kompletny, a nie zepsuty.
 * 3. **Zapis jest przyrostowy**: jedna akcja = jedno `resolve` z JEDNĄ zmianą.
 */
const importApi = vi.hoisted(() => ({
  getStaged: vi.fn(),
  resolveJob: vi.fn(),
  aiSuggest: vi.fn(),
  approveJob: vi.fn(),
  rejectJob: vi.fn(),
  groupByMeal: (job: { recipes?: { day_label: string; meal_label: string }[] }) => {
    const groups: { day: string; meal: string; recipes: unknown[] }[] = []
    for (const recipe of job.recipes ?? []) {
      const last = groups[groups.length - 1]
      if (last && last.day === recipe.day_label && last.meal === recipe.meal_label) {
        last.recipes.push(recipe)
      } else {
        groups.push({ day: recipe.day_label, meal: recipe.meal_label, recipes: [recipe] })
      }
    }
    return groups
  },
  mappedCount: (job: {
    recipes?: { ingredients?: { confirmed_product_id: number | null }[] }[]
  }) => {
    const items = (job.recipes ?? []).flatMap((recipe) => recipe.ingredients ?? [])
    return {
      mapped: items.filter((item) => item.confirmed_product_id !== null).length,
      total: items.length,
    }
  },
}))
vi.mock('@/api/pdfImport', () => importApi)

function staged(overrides: Partial<StagedJobResponse> = {}): StagedJobResponse {
  return {
    job: {
      id: 1,
      filename: 'dieta.pdf',
      status: 'parsed',
      created_at: '2026-08-29T10:00:00+00:00',
      updated_at: '2026-08-29T10:00:05+00:00',
      error: null,
      parse_report: null,
    },
    recipes: [
      {
        id: 5,
        name: 'Gołąbki bez zawijania',
        day_label: 'Środa',
        meal_label: 'OBIAD',
        instructions: '',
        comment: '',
        declared_servings: 7,
        resolved_servings: null,
        resolution: null,
        target_recipe_id: null,
        pdf_macros: null,
        meal: { computed_kcal: null, pdf_kcal: '635.0', delta_pct: null, reason: '' },
        ingredients: [
          {
            id: 7,
            raw_name: 'Cebula',
            raw_qty: '2.000',
            raw_unit: 'Sztuka',
            grams: '210.000',
            from_extras_section: false,
            match_kind: 'exact',
            confidence: null,
            suggested_product_id: 42,
            suggested_product_name: 'Cebula',
            confirmed_product_id: null,
            confirmed_product_name: null,
            create_new_product: false,
          },
        ],
        issues: [],
      },
    ],
    job_issues: [],
    blockers: [],
    ai_available: false,
    ...overrides,
  } as StagedJobResponse
}

async function mountPage() {
  setActivePinia(createPinia())
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push('/import/jobs/1/review')
  await router.isReady()

  const wrapper = mount(ImportReviewPage, {
    global: {
      plugins: [VueQueryPlugin, router],
      stubs: { ProductPicker: { template: '<div />' }, RecipePicker: { template: '<div />' } },
    },
  })
  await flushPromises()
  return wrapper
}

describe('ImportReviewPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    importApi.getStaged.mockResolvedValue(staged())
  })

  it('pokazuje postęp mapowań i liczbę otwartych uwag', async () => {
    const wrapper = await mountPage()

    expect(wrapper.get('[data-testid="import-review-progress"]').text()).toBe('0 / 1')
    expect(wrapper.get('[data-testid="import-review-issues"]').text()).toBe('0')
  })

  it('blokady z serwera wyłączają zatwierdzenie i są WYPISANE', async () => {
    importApi.getStaged.mockResolvedValue(
      staged({
        blockers: [
          {
            staged_recipe_id: 5,
            recipe_name: 'Gołąbki bez zawijania',
            kind: 'multi_portion_suspect',
            message: 'Trzeba ustalić liczbę porcji',
          },
        ],
      }),
    )

    const wrapper = await mountPage()
    const approve = wrapper.get('[data-testid="import-review-approve"]')

    expect(approve.attributes('disabled')).toBeDefined()
    expect(approve.attributes('title')).toBeTruthy()
    const blockers = wrapper.get('[data-testid="import-review-blockers"]').text()
    expect(blockers).toContain('Gołąbki bez zawijania')
    expect(blockers).toContain('Trzeba ustalić liczbę porcji')
  })

  it('bez blokad zatwierdzenie jest czynne i mówi o tym wprost', async () => {
    const wrapper = await mountPage()

    expect(
      wrapper.get('[data-testid="import-review-approve"]').attributes('disabled'),
    ).toBeUndefined()
    expect(wrapper.find('[data-testid="import-review-ready"]').exists()).toBe(true)
  })

  it('bez klucza API nie ma przycisku AI — tryb deterministyczny (ADR-011)', async () => {
    const wrapper = await mountPage()

    expect(wrapper.find('[data-testid="import-review-ai"]').exists()).toBe(false)
  })

  it('z kluczem API przycisk AI jest, a jego kliknięcie pyta serwer', async () => {
    importApi.getStaged.mockResolvedValue(staged({ ai_available: true }))
    importApi.aiSuggest.mockResolvedValue(staged({ ai_available: true }))

    const wrapper = await mountPage()
    await wrapper.get('[data-testid="import-review-ai"]').trigger('click')
    await flushPromises()

    expect(importApi.aiSuggest).toHaveBeenCalledWith(1)
  })

  it('potwierdzenie mapowania wysyła JEDNO żądanie z JEDNĄ zmianą', async () => {
    importApi.resolveJob.mockResolvedValue(staged())

    const wrapper = await mountPage()
    await wrapper.get('[data-testid="staged-ingredient-confirm-7"]').trigger('click')
    await flushPromises()

    expect(importApi.resolveJob).toHaveBeenCalledTimes(1)
    expect(importApi.resolveJob).toHaveBeenCalledWith(1, {
      ingredients: [{ ingredient_id: 7, confirmed_product_id: 42, create_new_product: false }],
    })
  })

  it('po zatwierdzeniu pokazuje podsumowanie z liczbami, a nie samo „gotowe"', async () => {
    importApi.approveJob.mockResolvedValue({
      job: staged().job,
      created_recipe_ids: [11, 12],
      created_product_ids: [3],
      merged_count: 1,
      skipped_count: 4,
      unit_weight_rows: 6,
    })

    const wrapper = await mountPage()
    await wrapper.get('[data-testid="import-review-approve"]').trigger('click')
    await flushPromises()

    const summary = wrapper.get('[data-testid="import-review-summary"]')
    expect(summary.text()).toContain('Import zatwierdzony')
    expect(wrapper.get('[data-testid="summary-recipes"]').text()).toBe('2')
    expect(wrapper.get('[data-testid="summary-go-to-recipes"]').attributes('href')).toBe(
      '/przepisy',
    )
  })

  it('rozstrzygnięty import przechodzi w tryb tylko do odczytu', async () => {
    importApi.getStaged.mockResolvedValue(staged({ job: { ...staged().job, status: 'approved' } }))

    const wrapper = await mountPage()

    expect(wrapper.find('[data-testid="import-review-settled"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="import-review-approve"]').exists()).toBe(false)
  })

  it('uwagi do CAŁEGO pliku (nieodczytane linie) mają własną sekcję', async () => {
    importApi.getStaged.mockResolvedValue(
      staged({
        job_issues: [
          {
            id: 3,
            staged_recipe_id: null,
            kind: 'parse_warning',
            severity: 'warning',
            details: { powód: 'Linia wygląda na składnik', linia: 'Czekolada ciemna, 2 x' },
            resolution: null,
            resolved_at: null,
          },
        ],
      }),
    )

    const wrapper = await mountPage()

    expect(wrapper.get('[data-testid="import-review-job-issues"]').text()).toContain(
      'Czekolada ciemna, 2 x',
    )
  })
})
