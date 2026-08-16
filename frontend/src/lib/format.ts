/**
 * Formatowanie ilości — JEDYNE miejsce w aplikacji, które zamienia liczbę na
 * napis dla użytkownika (05_FRONTEND §7).
 *
 * Dwie zasady, z których wynika cała reszta:
 *
 * 1. **Bez `Number`.** API przysyła ilości jako stringi dziesiętne (ADR-008),
 *    a `parseFloat("0.1")` już na wejściu przestaje być 0,1. Przesuwanie
 *    przecinka robimy więc na tekście — to operacja dokładna i tania.
 * 2. **Dane zawsze w g/ml, prezentacja bywa w kg/l.** Powyżej 1000 g pokazujemy
 *    kilogramy (02_DOMAIN §4.2), ale w bazie i w silnikach nic się nie zmienia.
 *
 * Separator dziesiętny to przecinek — UI jest wyłącznie polskie (D3/ADR-007).
 */

import type { components } from '@/api/generated'

export type AmountUnit = 'g' | 'ml' | 'piece'
export type MeasureKind = components['schemas']['MeasureKind']

/** Od tylu jednostek bazowych przechodzimy na jednostkę większą (g→kg, ml→l). */
const LARGER_UNIT_THRESHOLD_DIGITS = 4

interface DecimalParts {
  negative: boolean
  integer: string
  fraction: string
}

function splitDecimal(value: string): DecimalParts {
  const trimmed = value.trim()
  const negative = trimmed.startsWith('-')
  const unsigned = negative ? trimmed.slice(1) : trimmed
  const [integer = '0', fraction = ''] = unsigned.split('.')
  return { negative, integer: integer.replace(/^0+(?=\d)/, '') || '0', fraction }
}

/** Usuwa nieznaczące zera z końca części ułamkowej (`"1.500"` → `"1.5"`). */
function trimFraction(fraction: string): string {
  return fraction.replace(/0+$/, '')
}

/**
 * Przesuwa przecinek w lewo o `places` pozycji — czyli dzieli przez 10^places
 * bez arytmetyki zmiennoprzecinkowej.
 */
export function shiftDecimalLeft(value: string, places: number): string {
  const { negative, integer, fraction } = splitDecimal(value)
  const digits = integer + fraction
  const pointFromRight = fraction.length + places
  const padded = digits.padStart(pointFromRight + 1, '0')
  const cut = padded.length - pointFromRight
  const nextInteger = padded.slice(0, cut).replace(/^0+(?=\d)/, '') || '0'
  const nextFraction = trimFraction(padded.slice(cut))
  const result = nextFraction ? `${nextInteger}.${nextFraction}` : nextInteger
  return negative && result !== '0' ? `-${result}` : result
}

/** Kanoniczny string dziesiętny → zapis polski, bez zer na końcu (`"1.50"` → `"1,5"`). */
export function formatDecimal(value: string): string {
  const { negative, integer, fraction } = splitDecimal(value)
  const trimmed = trimFraction(fraction)
  const text = trimmed ? `${integer},${trimmed}` : integer
  return negative && text !== '0' ? `-${text}` : text
}

/** Czy wartość zasługuje na większą jednostkę (≥ 1000 w jednostce bazowej). */
function needsLargerUnit(value: string): boolean {
  const { negative, integer } = splitDecimal(value)
  return !negative && integer.length >= LARGER_UNIT_THRESHOLD_DIGITS
}

/**
 * Ilość gotowa do pokazania: `"1500"` + `g` → `"1,5 kg"`, `"999"` + `g` →
 * `"999 g"`. `null`/pusty string daje `"—"`, bo brak ilości to nie zero.
 */
export function formatAmount(value: string | null | undefined, unit: AmountUnit): string {
  if (value == null || value.trim() === '') {
    return '—'
  }
  if (unit === 'piece') {
    return `${formatDecimal(value)} szt.`
  }
  if (needsLargerUnit(value)) {
    const larger = unit === 'g' ? 'kg' : 'l'
    return `${formatDecimal(shiftDecimalLeft(value, 3))} ${larger}`
  }
  return `${formatDecimal(value)} ${unit}`
}

/** Jednostka bazowa produktu wg jego typu miary (ADR-005). */
export function baseUnitFor(measureKind: MeasureKind): AmountUnit {
  if (measureKind === 'volume') {
    return 'ml'
  }
  return measureKind === 'piece' ? 'piece' : 'g'
}

/**
 * Wartość odżywcza „na 100" z jednostką — `null` zostaje myślnikiem, bo brak
 * danych to nie zero (ADR-004).
 */
export function formatNutrient(value: string | null | undefined, unit = 'g'): string {
  return value == null ? '—' : `${formatDecimal(value)} ${unit}`
}
