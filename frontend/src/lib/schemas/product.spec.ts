import { describe, expect, it } from 'vitest'

import {
  nutritionFormSchema,
  productFormSchema,
  toApiDecimal,
  toApiText,
  unitWeightFormSchema,
} from './product'

const BASE_PRODUCT = {
  name: 'Cebula',
  category_id: 1,
  measure_kind: 'mass' as const,
  piece_weight_g: '',
  perishability_override: '' as const,
}

const EMPTY_NUTRITION = {
  kcal_100: '',
  protein_100: '',
  fat_100: '',
  carbs_100: '',
  fiber_100: '',
  sugars_100: '',
  glycemic_index: '',
  nutrition_source: '',
}

describe('productFormSchema', () => {
  it('przyjmuje minimalny poprawny produkt', () => {
    expect(productFormSchema.safeParse(BASE_PRODUCT).success).toBe(true)
  })

  it('wymaga nazwy', () => {
    expect(productFormSchema.safeParse({ ...BASE_PRODUCT, name: '   ' }).success).toBe(false)
  })

  it('wymaga kategorii', () => {
    expect(productFormSchema.safeParse({ ...BASE_PRODUCT, category_id: 0 }).success).toBe(false)
  })

  it('produkt w sztukach musi mieć wagę sztuki', () => {
    const result = productFormSchema.safeParse({ ...BASE_PRODUCT, measure_kind: 'piece' })

    expect(result.success).toBe(false)
    if (!result.success) {
      expect(result.error.issues[0]?.path).toEqual(['piece_weight_g'])
    }
  })

  it('waga sztuki przyjmuje przecinek dziesiętny', () => {
    const result = productFormSchema.safeParse({
      ...BASE_PRODUCT,
      measure_kind: 'piece',
      piece_weight_g: '60,5',
    })

    expect(result.success).toBe(true)
  })

  it('waga sztuki musi być dodatnia', () => {
    const result = productFormSchema.safeParse({
      ...BASE_PRODUCT,
      measure_kind: 'piece',
      piece_weight_g: '0',
    })

    expect(result.success).toBe(false)
  })
})

describe('nutritionFormSchema', () => {
  it('puste wartości są dozwolone — to „nie wiem", nie zero', () => {
    expect(nutritionFormSchema.safeParse(EMPTY_NUTRITION).success).toBe(true)
  })

  it('przyjmuje liczby z przecinkiem', () => {
    const result = nutritionFormSchema.safeParse({ ...EMPTY_NUTRITION, kcal_100: '40,5' })

    expect(result.success).toBe(true)
  })

  it.each(['111', '110,5', '200'])('odrzuca indeks glikemiczny %s', (value) => {
    expect(
      nutritionFormSchema.safeParse({ ...EMPTY_NUTRITION, glycemic_index: value }).success,
    ).toBe(false)
  })

  it.each(['0', '110', '55,5'])('przyjmuje indeks glikemiczny %s', (value) => {
    expect(
      nutritionFormSchema.safeParse({ ...EMPTY_NUTRITION, glycemic_index: value }).success,
    ).toBe(true)
  })

  it('odrzuca makroskładnik powyżej 100 g na 100 g', () => {
    expect(nutritionFormSchema.safeParse({ ...EMPTY_NUTRITION, protein_100: '150' }).success).toBe(
      false,
    )
  })

  it('odrzuca tekst zamiast liczby', () => {
    expect(nutritionFormSchema.safeParse({ ...EMPTY_NUTRITION, kcal_100: 'dużo' }).success).toBe(
      false,
    )
  })

  it('odrzuca trzy miejsca po przecinku (kolumna ma dwa)', () => {
    expect(nutritionFormSchema.safeParse({ ...EMPTY_NUTRITION, kcal_100: '40,123' }).success).toBe(
      false,
    )
  })
})

describe('unitWeightFormSchema', () => {
  it('przyjmuje przelicznik z przecinkiem', () => {
    const result = unitWeightFormSchema.safeParse({
      unit_label: 'łyżka',
      grams_per_unit: '12,5',
      source: '',
    })

    expect(result.success).toBe(true)
  })

  it('odrzuca zerową gramaturę', () => {
    expect(
      unitWeightFormSchema.safeParse({ unit_label: 'łyżka', grams_per_unit: '0', source: '' })
        .success,
    ).toBe(false)
  })

  it.each(['szt', 'szt.', 'Sztuka'])('odrzuca jednostkę „%s" (wynika z wagi sztuki)', (label) => {
    expect(
      unitWeightFormSchema.safeParse({ unit_label: label, grams_per_unit: '50', source: '' })
        .success,
    ).toBe(false)
  })
})

describe('konwersja do API', () => {
  it('pusty string idzie jako null, nie jako zero', () => {
    expect(toApiDecimal('  ')).toBeNull()
    expect(toApiText('')).toBeNull()
  })

  it('przecinek zamienia się na kropkę', () => {
    expect(toApiDecimal('12,5')).toBe('12.5')
  })

  it('tekst jest przycinany', () => {
    expect(toApiText('  usda:11282 ')).toBe('usda:11282')
  })
})
