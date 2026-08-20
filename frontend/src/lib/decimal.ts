/**
 * Liczby dziesiętne w UI — parsowanie i prezentacja bez `Number`.
 *
 * API przysyła i przyjmuje ilości jako stringi dziesiętne (ADR-008, 04_API §1),
 * a polski użytkownik wpisuje przecinek. Te dwie funkcje są jedynym miejscem,
 * które tłumaczy jedno na drugie — komponenty nie robią własnego `parseFloat`.
 *
 * BATCH_05 buduje na tym `AmountInput` i `formatAmount` (05_FRONTEND §7);
 * tutaj jest tylko tyle, ile potrzebuje mnożnik porcji i cel kcal.
 */

/** Wejście użytkownika → kanoniczny string dziesiętny (`"0,8"` → `"0.8"`). */
export function normalizeDecimalInput(value: string): string {
  return value.trim().replace(',', '.')
}

/** Kanoniczny string z API → zapis polski do pola formularza (`"0.80"` → `"0,80"`). */
export function toDecimalInput(value: string | null | undefined): string {
  return value == null ? '' : value.replace('.', ',')
}

/** Rozbicie stringa dziesiętnego na znak, część całkowitą i ułamkową. */
function parts(value: string): { negative: boolean; digits: string; scale: number } {
  const trimmed = normalizeDecimalInput(value)
  const negative = trimmed.startsWith('-')
  const unsigned = negative ? trimmed.slice(1) : trimmed
  const [integer = '0', fraction = ''] = unsigned.split('.')
  return { negative, digits: `${integer || '0'}${fraction}`, scale: fraction.length }
}

/**
 * Suma liczb dziesiętnych BEZ `Number` — na `BigInt` po sprowadzeniu do wspólnej
 * skali. Rozkład rodzinny 1,1 + 1,1 + 1,1 musi dać dokładnie 3,3; na floatach
 * wychodzi 3,3000000000000003 i backend odrzuciłby poprawne dane (ADR-008).
 */
export function sumDecimals(values: readonly string[]): string {
  const scale = values.reduce((max, value) => Math.max(max, parts(value).scale), 0)
  const total = values.reduce((sum, value) => {
    const { negative, digits, scale: valueScale } = parts(value)
    const scaled = BigInt(digits || '0') * 10n ** BigInt(scale - valueScale)
    return negative ? sum - scaled : sum + scaled
  }, 0n)

  if (scale === 0) {
    return total.toString()
  }
  const negative = total < 0n
  const text = (negative ? -total : total).toString().padStart(scale + 1, '0')
  const result = `${text.slice(0, -scale)}.${text.slice(-scale)}`
  return negative ? `-${result}` : result
}

/** Zamiana znaku liczby dziesiętnej (na tekście, bez arytmetyki zmiennoprzecinkowej). */
function negate(value: string): string {
  const normalized = normalizeDecimalInput(value)
  return normalized.startsWith('-') ? normalized.slice(1) : `-${normalized}`
}

/** Czy dwa zapisy oznaczają tę samą liczbę (`"6.20"` = `"6,2"`). */
export function decimalsEqual(first: string, second: string): boolean {
  return /^-?0(\.0*)?$/.test(sumDecimals([first, negate(second)]))
}

export interface DecimalRules {
  /** Maksymalna liczba cyfr po przecinku (odpowiada skali kolumny NUMERIC). */
  decimalPlaces: number
  /** Wartość musi być większa od zera (mnożnik, cel kcal). */
  positive?: boolean
}

/**
 * Czy wpisana wartość jest poprawną liczbą dziesiętną wg reguł kolumny.
 * Walidacja frontowa to UX — prawdą jest walidacja serwera (05_FRONTEND §5).
 */
export function isValidDecimal(value: string, rules: DecimalRules): boolean {
  const normalized = normalizeDecimalInput(value)
  const pattern =
    rules.decimalPlaces > 0 ? new RegExp(`^\\d+(\\.\\d{1,${rules.decimalPlaces}})?$`) : /^\d+$/
  if (!pattern.test(normalized)) {
    return false
  }
  return !rules.positive || Number.parseFloat(normalized) > 0
}
