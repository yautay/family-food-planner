import { describe, expect, it } from 'vitest'
import {
  ingredientDraftError,
  isIngredientDraftValid,
  recipeFormSchema,
  type IngredientDraft,
} from './recipe'

const ingredient = (): IngredientDraft => ({
  key: 'row',
  product: { id: 1, name: 'Makaron', measure_kind: 'mass' },
  quantity: '99999.999',
  unit: 'g',
  note: '',
})
describe('edytor przepisu — granice API bez konwersji ilości na float', () => {
  it('przyjmuje maksymalną ilość i notatkę oraz kanoniczny string z zerami wiodącymi', () => {
    expect(isIngredientDraftValid({ ...ingredient(), note: 'a'.repeat(500) })).toBe(true)
    expect(isIngredientDraftValid({ ...ingredient(), quantity: '00012.500' })).toBe(true)
  })
  it.each([null, '0', '-1', '12.1234', '100000', '1e3', 'zła liczba'])(
    'odrzuca błędną ilość %s',
    (quantity) => {
      expect(ingredientDraftError({ ...ingredient(), quantity })?.field).toBe('quantity')
    },
  )
  it.each([{ product: null }, { unit: '' }, { unit: 'a'.repeat(51) }, { note: 'a'.repeat(501) }])(
    'odrzuca niekompletny lub za długi składnik %j',
    (patch) => {
      expect(isIngredientDraftValid({ ...ingredient(), ...patch })).toBe(false)
    },
  )
  it('zachowuje granice pól podstawowych i dodatkowych zgodne z RecipePayload', () => {
    const form = {
      name: 'Zupa',
      instructions: '',
      base_servings: '100',
      prep_time_min: '6000',
      difficulty: '10',
      scope: 'private',
    }
    expect(recipeFormSchema.safeParse(form).success).toBe(true)
    for (const patch of [
      { base_servings: '101' },
      { prep_time_min: '6001' },
      { difficulty: '11' },
      { instructions: 'a'.repeat(20001) },
    ]) {
      expect(recipeFormSchema.safeParse({ ...form, ...patch }).success).toBe(false)
    }
  })
})
