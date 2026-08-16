import { describe, expect, it } from 'vitest'

import {
  baseUnitFor,
  formatAmount,
  formatDecimal,
  formatNutrient,
  shiftDecimalLeft,
} from './format'

describe('formatAmount', () => {
  it('poniżej kilograma pokazuje gramy', () => {
    expect(formatAmount('999', 'g')).toBe('999 g')
  })

  it('od kilograma przechodzi na kilogramy z przecinkiem', () => {
    expect(formatAmount('1500', 'g')).toBe('1,5 kg')
  })

  it('równo tysiąc gramów to już kilogram', () => {
    expect(formatAmount('1000', 'g')).toBe('1 kg')
  })

  it('nie gubi cyfr przy przejściu na kilogramy', () => {
    expect(formatAmount('1567.5', 'g')).toBe('1,5675 kg')
  })

  it('obcina nieznaczące zera z API', () => {
    expect(formatAmount('105.00', 'g')).toBe('105 g')
    expect(formatAmount('12.50', 'g')).toBe('12,5 g')
  })

  it('mililitry zamienia na litry po tej samej regule', () => {
    expect(formatAmount('330', 'ml')).toBe('330 ml')
    expect(formatAmount('1750', 'ml')).toBe('1,75 l')
  })

  it('sztuki zostają sztukami niezależnie od wielkości', () => {
    expect(formatAmount('2', 'piece')).toBe('2 szt.')
    expect(formatAmount('1200', 'piece')).toBe('1200 szt.')
  })

  it('brak ilości to myślnik, nie zero', () => {
    expect(formatAmount(null, 'g')).toBe('—')
    expect(formatAmount('', 'g')).toBe('—')
  })
})

describe('shiftDecimalLeft', () => {
  it.each([
    ['1500', 3, '1.5'],
    ['999', 3, '0.999'],
    ['1000', 3, '1'],
    ['1234.56', 3, '1.23456'],
    ['0', 3, '0'],
  ])('przesuwa przecinek w %s o %i miejsc', (value, places, expected) => {
    expect(shiftDecimalLeft(value, places)).toBe(expected)
  })

  it('nie używa arytmetyki zmiennoprzecinkowej', () => {
    // 0.1 + 0.2 na floatach to 0.30000000000000004; tutaj liczy tekst.
    expect(shiftDecimalLeft('300.0000000001', 3)).toBe('0.3000000000001')
  })
})

describe('formatDecimal', () => {
  it.each([
    ['0.80', '0,8'],
    ['1.00', '1'],
    ['12.345', '12,345'],
    ['0', '0'],
  ])('%s zapisuje jako %s', (value, expected) => {
    expect(formatDecimal(value)).toBe(expected)
  })
})

describe('formatNutrient', () => {
  it('brak wartości pokazuje jako myślnik', () => {
    expect(formatNutrient(null)).toBe('—')
  })

  it('wartość podaje z jednostką', () => {
    expect(formatNutrient('1.10')).toBe('1,1 g')
    expect(formatNutrient('40.00', 'kcal')).toBe('40 kcal')
  })
})

describe('baseUnitFor', () => {
  it.each([
    ['mass', 'g'],
    ['volume', 'ml'],
    ['piece', 'piece'],
  ] as const)('typ miary %s liczy się w %s', (measureKind, expected) => {
    expect(baseUnitFor(measureKind)).toBe(expected)
  })
})
