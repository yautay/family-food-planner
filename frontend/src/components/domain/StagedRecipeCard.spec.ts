import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { ImportIssueRead, StagedRecipeRead } from '@/api/pdfImport'

import StagedRecipeCard from './StagedRecipeCard.vue'

/**
 * Karta dania w review importu — Acceptance Criteria 1, 3 i 4 karty B16.
 *
 * Najważniejsza asercja pliku: przy rozjeździe kalorii karta pokazuje OBIE
 * wartości (z jadłospisu i wyliczoną), a nie samą plakietkę „coś się nie zgadza".
 * Bez obu liczb człowiek nie ma jak zdecydować, czy to on źle zmapował produkt,
 * czy dietetyczka zaokrągliła.
 */
const STUBS = {
  ProductPicker: { template: '<div />' },
  RecipePicker: {
    name: 'RecipePicker',
    props: ['modelValue', 'label', 'disabled'],
    emits: ['update:modelValue', 'selected'],
    template: '<div data-testid="recipe-picker-stub" />',
  },
}

function issue(overrides: Partial<ImportIssueRead> = {}): ImportIssueRead {
  return {
    id: 1,
    staged_recipe_id: 5,
    kind: 'multi_portion_suspect',
    severity: 'blocker',
    details: { powód: 'Nieznana liczba porcji' },
    resolution: null,
    resolved_at: null,
    ...overrides,
  }
}

function recipe(overrides: Partial<StagedRecipeRead> = {}): StagedRecipeRead {
  return {
    id: 5,
    name: 'Gołąbki bez zawijania',
    day_label: 'Środa',
    meal_label: 'OBIAD',
    instructions: '',
    comment: '',
    declared_servings: null,
    resolved_servings: null,
    resolution: null,
    target_recipe_id: null,
    pdf_macros: null,
    meal: { computed_kcal: null, pdf_kcal: '635.0', delta_pct: null, reason: '' },
    ingredients: [],
    issues: [],
    ...overrides,
  }
}

function mountCard(overrides: Partial<StagedRecipeRead> = {}, disabled = false) {
  return mount(StagedRecipeCard, {
    props: { recipe: recipe(overrides), disabled },
    global: { stubs: STUBS },
  })
}

describe('StagedRecipeCard', () => {
  it('przy rozjeździe kalorii pokazuje OBIE wartości i deltę', () => {
    const wrapper = mountCard({
      meal: { computed_kcal: '489', pdf_kcal: '635.0', delta_pct: '-23.0', reason: '' },
      issues: [issue({ kind: 'kcal_mismatch', severity: 'warning' })],
    })
    const kcal = wrapper.get('[data-testid="staged-recipe-kcal"]').text()

    expect(kcal).toContain('635.0')
    expect(kcal).toContain('489')
    expect(kcal).toContain('-23.0')
    expect(wrapper.find('[data-testid="staged-recipe-kcal-badge"]').exists()).toBe(true)
  })

  it('bez wyliczenia pokazuje POWÓD, a nie fałszywy rozjazd', () => {
    const wrapper = mountCard({
      meal: {
        computed_kcal: null,
        pdf_kcal: '635.0',
        delta_pct: null,
        reason: 'Nie wszystkie składniki mają wskazany produkt.',
      },
    })

    expect(wrapper.get('[data-testid="staged-recipe-kcal"]').text()).toContain(
      'Nie wszystkie składniki mają wskazany produkt.',
    )
    expect(wrapper.find('[data-testid="staged-recipe-kcal-badge"]').exists()).toBe(false)
  })

  it('blocker wieloporcyjności otwiera pytanie o liczbę porcji', async () => {
    const wrapper = mountCard({ issues: [issue()] })

    await wrapper.get('[data-testid="staged-recipe-servings-5"]').setValue('7')

    expect(wrapper.emitted('servings')?.at(-1)?.[0]).toEqual({ id: 5, servings: 7 })
  })

  it('podpowiedź AI jest OZNACZONA jako propozycja i nie wypełnia pola', () => {
    const wrapper = mountCard({
      issues: [
        issue({
          details: { powód: 'Nieznana liczba porcji', propozycja_ai_porcje: 21 },
        }),
      ],
    })
    const input = wrapper.get('[data-testid="staged-recipe-servings-5"]')
      .element as HTMLInputElement

    expect(wrapper.get('[data-testid="servings-ai-hint"]').text()).toContain('21')
    expect(input.value).toBe('')
  })

  it('bez blockera porcji pokazuje liczbę z dokumentu zamiast pytać', () => {
    const wrapper = mountCard({ declared_servings: 7 })

    expect(wrapper.find('[data-testid="staged-recipe-servings-5"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="staged-recipe-declared-5"]').text()).toContain('7')
  })

  it('zmiana decyzji o daniu emituje `resolution`', async () => {
    const wrapper = mountCard()

    await wrapper.get('[data-testid="staged-recipe-resolution-skip-5"]').trigger('click')

    expect(wrapper.emitted('resolution')).toEqual([[{ id: 5, resolution: 'skip' }]])
  })

  it('pominięte danie nie pokazuje już składników do mapowania', () => {
    const wrapper = mountCard({ resolution: 'skip' })

    expect(wrapper.text()).not.toContain('Składniki')
  })

  it('duplikat daje dwa wyjścia: scal albo „to osobny przepis"', async () => {
    const wrapper = mountCard({
      issues: [
        issue({
          id: 9,
          kind: 'duplicate_recipe',
          severity: 'warning',
          details: { powód: 'AI', przepis_id: 3, przepis_nazwa: 'Gołąbki' },
        }),
      ],
    })

    await wrapper.get('[data-testid="staged-recipe-merge-duplicate-5"]').trigger('click')
    await wrapper.get('[data-testid="staged-recipe-duplicate-separate-5"]').trigger('click')

    expect(wrapper.emitted('merge-target')).toEqual([[{ id: 5, recipeId: 3 }]])
    expect(wrapper.emitted('resolve-issue')?.[0]?.[0]).toMatchObject({ issueId: 9 })
  })

  it('scalenie pokazuje picker przepisu — nie własny select (05_FRONTEND §4)', () => {
    const wrapper = mountCard({ resolution: 'merge_into_existing' })

    expect(wrapper.find('[data-testid="recipe-picker-stub"]').exists()).toBe(true)
  })

  it('poprawiona nazwa (ucięta przez zawijanie kolumn) emituje `rename`', async () => {
    const wrapper = mountCard({ name: 'Pizza na tortilli z szynką, pomidorkami i' })
    const input = wrapper.get('[data-testid="staged-recipe-name-5"]')

    await input.setValue('Pizza na tortilli z szynką, pomidorkami i rukolą')

    expect(wrapper.emitted('rename')?.at(-1)?.[0]).toEqual({
      id: 5,
      name: 'Pizza na tortilli z szynką, pomidorkami i rukolą',
    })
  })

  it('rozstrzygnięte uwagi znikają z listy — zostaje tylko to, co czeka', () => {
    const wrapper = mountCard({
      issues: [issue({ resolved_at: '2026-08-29T10:00:00Z', resolution: 'Ustalono 7 porcji.' })],
    })

    expect(wrapper.find('[data-testid="staged-recipe-issues"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="staged-recipe-servings-5"]').exists()).toBe(false)
  })
})
