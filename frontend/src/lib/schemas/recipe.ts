/**
 * Schemat walidacji formularza przepisu (05_FRONTEND §5, vee-validate + zod).
 *
 * Walidacja frontowa jest UX-em — prawdą jest odpowiedź serwera (422 mapowane
 * na pola). Składniki żyją POZA vee-validate (dynamiczna lista z ProductPicker
 * + AmountInput), więc schemat obejmuje pola proste; kompletność składników
 * pilnuje strona edytora przed wysyłką.
 */

import * as z from 'zod'

import type { MeasureKind } from '@/api/catalog'
import { isValidDecimal } from '@/lib/decimal'
import { recipes as texts } from '@/lib/texts'

/** Zakresy przepisu — 3 wartości (D32); inne encje (plan, szablony…) mają tylko 2. */
export const RECIPE_SCOPES = ['private', 'household', 'global'] as const

/** Pole całkowite opcjonalne: pusty string = „nie podano" (API dostaje null). */
function optionalInt(max: number, message: string) {
  return z
    .string()
    .trim()
    .refine((value) => {
      if (value === '') {
        return true
      }
      const parsed = Number(value)
      return Number.isInteger(parsed) && parsed >= 1 && parsed <= max
    }, message)
}

export const recipeFormSchema = z.object({
  name: z.string().trim().min(1, texts.nameRequired).max(200, 'Nazwa jest za długa.'),
  instructions: z.string().max(20000, 'Opis przygotowania jest za długi.'),
  base_servings: z
    .string()
    .trim()
    .refine((value) => {
      const parsed = Number(value)
      return Number.isInteger(parsed) && parsed >= 1 && parsed <= 100
    }, texts.baseServingsInvalid),
  prep_time_min: optionalInt(6000, texts.prepTimeInvalid),
  difficulty: optionalInt(10, texts.difficultyInvalid),
  scope: z.enum(RECIPE_SCOPES),
})

export type RecipeFormValues = z.infer<typeof recipeFormSchema>

/** Szkic składnika w edytorze — produkt z pickera + ilość z AmountInput. */
export interface IngredientDraft {
  /** Losowy klucz wiersza (stabilny dla v-for przy usuwaniu pozycji). */
  key: string
  /** `MeasureKind` z `generated.ts` — nowy typ miary ma wywrócić vue-tsc, nie runtime. */
  product: { id: number; name: string; measure_kind: MeasureKind } | null
  /** Kanoniczny string dziesiętny (AmountInput) albo null, gdy pusto. */
  quantity: string | null
  unit: string
  note: string
}

/** Czy szkic składnika nadaje się do wysłania (produkt + poprawna ilość). */
export function isIngredientDraftValid(draft: IngredientDraft): boolean {
  return ingredientDraftError(draft) === null
}

/** Pierwsze pole wymagające poprawy; limity odpowiadają RecipeIngredientInput. */
export function ingredientDraftError(
  draft: IngredientDraft,
): { field: 'product' | 'quantity' | 'unit' | 'note'; message: string } | null {
  if (!draft.product) return { field: 'product', message: 'Wybierz produkt dla tego składnika.' }
  if (
    draft.quantity === null ||
    !isValidDecimal(draft.quantity, { decimalPlaces: 3, positive: true }) ||
    draft.quantity.split('.')[0]!.replace(/^0+/, '').length > 5
  ) {
    return { field: 'quantity', message: 'Podaj ilość większą od 0, do 99999,999.' }
  }
  if (!draft.unit.trim() || draft.unit.trim().length > 50) {
    return { field: 'unit', message: 'Wybierz jednostkę (do 50 znaków).' }
  }
  if (draft.note.trim().length > 500) {
    return { field: 'note', message: 'Notatka może mieć do 500 znaków.' }
  }
  return null
}
