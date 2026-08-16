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
