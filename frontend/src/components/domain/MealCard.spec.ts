import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { PlanMeal } from '@/api/planning'
import MealCard from './MealCard.vue'

const nutrition = {
  kcal: '600',
  protein_g: '20',
  fat_g: '10',
  carbs_g: '30',
  fiber_g: '1',
  sugars_g: '1',
  glycemic_load: '2',
  complete: true,
  missing: [],
}
const longName = 'Pełnoziarnista zapiekanka z pieczoną papryką, cukinią i serem po długim spacerze'
const meal: PlanMeal = {
  id: 2,
  position: 0,
  name: 'Po spacerze, nasz dowolny posiłek',
  kcal_target: '700',
  kcal_status: 'below',
  nutrition,
  items: [
    {
      id: 3,
      position: 0,
      recipe_id: 4,
      recipe_name: longName,
      recipe_photo_thumb_url: null,
      product_id: null,
      product_name: null,
      amount: null,
      amount_unit: null,
      servings: '1',
      servings_split: [],
      nutrition,
    },
    {
      id: 5,
      position: 1,
      recipe_name: null,
      recipe_photo_thumb_url: null,
      product_id: 6,
      product_name: 'Produkt luzem',
      recipe_id: null,
      amount: '100',
      amount_unit: 'g',
      servings: '1',
      servings_split: [],
      nutrition,
    },
  ],
}

describe('MealCard — dania i zachowane operacje', () => {
  it('nie zmienia osobnej sumy wbrew zapisanemu podziałowi rodzinnemu', () => {
    const withSplit = {
      ...meal,
      items: [
        {
          ...meal.items[0]!,
          servings_split: [{ member_profile_id: 1, member_name: 'Osoba', multiplier: '1' }],
        },
      ],
    }
    const wrapper = mount(MealCard, { props: { meal: withSplit } })
    expect(
      wrapper.get<HTMLButtonElement>('[data-testid="plan-item-plus-3"]').element.disabled,
    ).toBe(true)
    expect(
      wrapper.get<HTMLButtonElement>('[data-testid="plan-item-minus-3"]').element.disabled,
    ).toBe(true)
    expect(wrapper.find('[data-testid="plan-item-split-open-3"]').exists()).toBe(true)
  })
  it('zawija pełną nazwę i oferuje zamianę wyłącznie przepisu, cel nadal dotyczy posiłku', async () => {
    const wrapper = mount(MealCard, { props: { meal } })
    expect(wrapper.get('h4').text()).toBe(longName)
    expect(wrapper.get('h4').classes()).not.toContain('truncate')
    expect(wrapper.find('[data-testid="plan-item-replace-5"]').exists()).toBe(false)
    await wrapper.get('[data-testid="plan-item-replace-3"]').trigger('click')
    expect(wrapper.emitted('replace-item')?.[0]).toEqual([3])
    expect(wrapper.find('[data-testid="meal-bar-2"]').exists()).toBe(true)
  })
  it('menu zachowuje produkt luzem, edycję, kopię i usuwanie; pozycja ma split i jawny fit', async () => {
    const wrapper = mount(MealCard, { props: { meal } })
    await wrapper.get('[data-testid="meal-menu-2"]').trigger('click')
    for (const action of ['add-product', 'edit', 'duplicate', 'remove']) {
      const id = action === 'add-product' ? 'meal-add-product-2' : `meal-${action}-2`
      await wrapper.get(`[data-testid="${id}"]`).trigger('click')
      expect(wrapper.emitted(action)?.[0]).toEqual([2])
    }
    for (const [id, event] of [
      ['plan-item-split-open-3', 'open-split'],
      ['plan-item-fit-3', 'fit-to-target'],
      ['plan-item-remove-3', 'remove-item'],
    ]) {
      await wrapper.get(`[data-testid="${id}"]`).trigger('click')
      expect(wrapper.emitted(event!)?.[0]).toEqual([3])
    }
  })
})
