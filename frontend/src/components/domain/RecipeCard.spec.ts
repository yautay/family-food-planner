import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { RecipeSummary } from '@/api/recipes'

import RecipeCard from './RecipeCard.vue'

/**
 * Odznaka zakresu na karcie (BATCH_21, D32): nazwy przepisów mogą się powtarzać,
 * więc kopia i jej oryginał byłyby na liście nie do odróżnienia bez wskaźnika.
 */

function recipe(scope: RecipeSummary['scope']): RecipeSummary {
  return {
    id: 9,
    name: 'Żurek',
    scope,
    owner_user_id: 1,
    base_servings: 2,
    prep_time_min: null,
    difficulty: null,
    is_archived: false,
    photo_url: null,
    photo_thumb_url: null,
    tags: [],
    avg_rating: null,
    ratings_count: 0,
    my_rating: null,
    nutrition: {
      kcal: '420',
      protein_g: '20',
      fat_g: '10',
      carbs_g: '55',
      fiber_g: '6',
      sugars_g: '8',
      glycemic_load: '25',
      complete: true,
      missing: [],
    },
    created_at: '2026-10-03T10:00:00Z',
    updated_at: '2026-10-03T10:00:00Z',
  }
}

describe('RecipeCard — odznaka zakresu', () => {
  it.each([
    ['global', 'Dla wszystkich'],
    ['household', 'Rodzinny'],
    ['private', 'Prywatny'],
  ] as const)('zakres %s pokazuje odznakę z tekstem', (scope, label) => {
    const wrapper = mount(RecipeCard, { props: { recipe: recipe(scope) } })

    expect(wrapper.get('[data-testid="recipe-scope-badge-9"]').text()).toBe(label)
  })
})
