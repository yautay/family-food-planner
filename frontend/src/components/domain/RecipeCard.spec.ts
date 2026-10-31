import { mount, RouterLinkStub } from '@vue/test-utils'
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
    const wrapper = mount(RecipeCard, {
      props: { recipe: recipe(scope) },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })

    expect(wrapper.get('[data-testid="recipe-scope-badge-9"]').text()).toBe(label)
  })

  it('pełna długa nazwa, czas, baza porcji i odrębne dostępne akcje', async () => {
    const item = {
      ...recipe('household'),
      name: 'Pełnoziarnista zapiekanka z pieczoną papryką, cukinią, serem i delikatnymi świeżymi ziołami',
      prep_time_min: 30,
    }
    const to = { name: 'przepis-szczegol', params: { id: 9 }, query: { q: 'zapiekanka' } }
    const wrapper = mount(RecipeCard, {
      props: { recipe: item, to },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    expect(wrapper.get('h2').text()).toBe(item.name)
    expect(wrapper.get('h2').classes()).not.toContain('truncate')
    expect(wrapper.text()).toContain('30 min')
    expect(wrapper.text()).toContain('2 porcji bazowych')
    expect(wrapper.findComponent(RouterLinkStub).props('to')).toEqual(to)
    await wrapper.get('[data-testid="recipe-plan-9"]').trigger('click')
    expect(wrapper.emitted('plan')).toEqual([[item]])
    expect(wrapper.find('button button, a button, button a').exists()).toBe(false)
  })

  it('brak zdjęcia i błąd rzeczywistego zdjęcia korzystają z ilustracji RecipeImage', async () => {
    const wrapper = mount(RecipeCard, {
      props: { recipe: recipe('global') },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    expect(wrapper.find('[data-testid="recipe-image-fallback"]').exists()).toBe(true)
    await wrapper.setProps({
      recipe: { ...recipe('global'), photo_thumb_url: '/uploads/recipes/photo_thumb.jpg' },
    })
    expect(wrapper.get('img').attributes('src')).toBe('/uploads/recipes/photo_thumb.jpg')
    await wrapper.get('img').trigger('error')
    expect(wrapper.find('[data-testid="recipe-image-fallback"]').exists()).toBe(true)
    expect(wrapper.find('img').exists()).toBe(false)
  })

  it('serce jest etykietą tagu, bez zapisu i bez osobistej zakładki globalnego', () => {
    const wrapper = mount(RecipeCard, {
      props: {
        recipe: { ...recipe('global'), tags: [{ id: 1, name: 'ulubione', is_system: true }] },
      },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    expect(wrapper.get('[data-testid="recipe-favorite-9"]').attributes('aria-label')).toBe(
      'Tag: ulubione',
    )
    expect(wrapper.findAll('button')).toHaveLength(1)
    expect(wrapper.get('[data-testid="recipe-plan-9"]').attributes('disabled')).toBeUndefined()
  })
})
