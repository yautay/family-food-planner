/**
 * Schematy walidacji formularza produktu (05_FRONTEND §5, vee-validate + zod).
 *
 * Walidacja frontowa jest UX-em — prawdą jest odpowiedź serwera (422 mapowane na
 * pola). Odwzorowujemy tu reguły backendu: zakres IG 0–110, wartości nieujemne,
 * waga sztuki wymagana dla produktów mierzonych w sztukach, precyzja kolumn
 * NUMERIC.
 *
 * Wszystkie liczby są **stringami dziesiętnymi** (ADR-008): użytkownik wpisuje
 * przecinek, `normalizeDecimalInput` zamienia go na kropkę, a do API idzie
 * tekst — nigdy `Number`.
 */

import * as z from 'zod'

import { isValidDecimal, normalizeDecimalInput } from '@/lib/decimal'

export const MEASURE_KINDS = ['mass', 'volume', 'piece'] as const
export const PERISHABILITY = ['fresh', 'durable'] as const

const REQUIRED_NAME = 'Podaj nazwę produktu.'
const REQUIRED_CATEGORY = 'Wybierz kategorię.'
const INVALID_DECIMAL = 'Podaj liczbę, np. 12,5.'
const PIECE_WEIGHT_REQUIRED = 'Produkt liczony w sztukach musi mieć podaną wagę jednej sztuki.'
const GLYCEMIC_RANGE = 'Indeks glikemiczny mieści się w zakresie 0–110.'

/**
 * Pole liczbowe opcjonalne: pusty string znaczy „nie wiem" i idzie do API jako
 * `null`. To nie to samo co zero — 0 kcal byłoby zapisaniem nieprawdy (ADR-004).
 */
function optionalDecimal(decimalPlaces: number, max?: number) {
  return z
    .string()
    .trim()
    .refine((value) => value === '' || isValidDecimal(value, { decimalPlaces }), INVALID_DECIMAL)
    .refine(
      (value) => value === '' || max === undefined || Number(normalizeDecimalInput(value)) <= max,
      // Porównanie z progiem jest wyłącznie prezentacyjne (podpowiedź w formularzu),
      // więc `Number` jest tu bezpieczny — do API i tak leci oryginalny tekst.
      max === undefined ? INVALID_DECIMAL : `Wartość nie może przekraczać ${max}.`,
    )
}

/** Wartość dodatnia i wymagana (waga sztuki, gramatura jednostki domowej). */
function requiredPositiveDecimal(decimalPlaces: number, message: string) {
  return z
    .string()
    .trim()
    .refine((value) => isValidDecimal(value, { decimalPlaces, positive: true }), message)
}

export const productFormSchema = z
  .object({
    name: z.string().trim().min(1, REQUIRED_NAME).max(200, 'Nazwa jest za długa.'),
    category_id: z.coerce.number({ invalid_type_error: REQUIRED_CATEGORY }).int().positive({
      message: REQUIRED_CATEGORY,
    }),
    measure_kind: z.enum(MEASURE_KINDS),
    piece_weight_g: z.string().trim(),
    perishability_override: z.union([z.enum(PERISHABILITY), z.literal('')]),
  })
  .superRefine((values, ctx) => {
    // Reguła sprzężona dwóch pól — dlatego `superRefine`, a nie walidacja pola.
    if (values.measure_kind !== 'piece') {
      return
    }
    if (!isValidDecimal(values.piece_weight_g, { decimalPlaces: 2, positive: true })) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['piece_weight_g'],
        message: PIECE_WEIGHT_REQUIRED,
      })
    }
  })

export const nutritionFormSchema = z.object({
  kcal_100: optionalDecimal(2, 99999),
  protein_100: optionalDecimal(2, 100),
  fat_100: optionalDecimal(2, 100),
  carbs_100: optionalDecimal(2, 100),
  fiber_100: optionalDecimal(2, 100),
  sugars_100: optionalDecimal(2, 100),
  glycemic_index: optionalDecimal(1, 110).refine(
    (value) => value === '' || Number(normalizeDecimalInput(value)) <= 110,
    GLYCEMIC_RANGE,
  ),
  nutrition_source: z.string().trim().max(300, 'Źródło jest za długie.'),
})

export const unitWeightFormSchema = z.object({
  unit_label: z
    .string()
    .trim()
    .min(1, 'Podaj nazwę jednostki, np. łyżka.')
    .max(200, 'Nazwa jednostki jest za długa.')
    .refine(
      (value) => !['szt', 'szt.', 'sztuka', 'sztuki'].includes(value.toLowerCase()),
      'Sztuki wynikają z wagi sztuki produktu — nie definiuje się ich przelicznikiem.',
    ),
  grams_per_unit: requiredPositiveDecimal(2, 'Podaj gramaturę większą od zera, np. 12,5.'),
  source: z.string().trim().max(300, 'Źródło jest za długie.'),
})

export type ProductFormValues = z.infer<typeof productFormSchema>
export type NutritionFormValues = z.infer<typeof nutritionFormSchema>
export type UnitWeightFormValues = z.infer<typeof unitWeightFormSchema>

/** Pusty string → `null`; wartość → kanoniczny string dziesiętny dla API. */
export function toApiDecimal(value: string): string | null {
  const trimmed = value.trim()
  return trimmed === '' ? null : normalizeDecimalInput(trimmed)
}

/** Pusty string → `null`; inaczej przycięty tekst (źródło wartości, notatka). */
export function toApiText(value: string): string | null {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}
