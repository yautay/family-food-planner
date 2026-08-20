/**
 * Prezentacja wartości żywieniowych: statusy, ich etykiety i klasy z tokens.
 *
 * Statusy liczy BACKEND (silnik `goal_status`, progi z `ui_settings`) — tutaj
 * jest wyłącznie warstwa prezentacji plus jedna czysta funkcja `statusFor`
 * używana do PODGLĄDU progów w ustawieniach (użytkownik widzi od razu, co
 * zmienia suwak, bez zapisywania i przeładowania planu).
 *
 * Kolory wyłącznie przez klasy semantyczne z `assets/tailwind.css`; status
 * zawsze niesie też tekst, nigdy sam kolor (06_UIUX §1).
 */

import type { GoalStatus } from '@/api/planning'

export interface StatusToken {
  /** Klasa wypełnienia dla elementów SVG. */
  fill: string
  /** Klasa koloru tekstu dla etykiety statusu. */
  text: string
}

const TOKENS: Record<GoalStatus, StatusToken> = {
  below: { fill: 'fill-warning', text: 'text-warning' },
  ok: { fill: 'fill-secondary', text: 'text-secondary' },
  above: { fill: 'fill-destructive', text: 'text-destructive' },
}

/** Bez celu wykres jest neutralny — „nie wiem" to nie „źle". */
const NEUTRAL: StatusToken = { fill: 'fill-primary', text: 'text-muted-foreground' }

const LABELS: Record<GoalStatus, string> = {
  below: 'za mało',
  ok: 'prawidłowo',
  above: 'za dużo',
}

export function statusToken(status: GoalStatus | null | undefined): StatusToken {
  return status ? TOKENS[status] : NEUTRAL
}

/** Słowny status po polsku albo pusty string, gdy celu nie ma (06_UIUX §3.5). */
export function statusLabel(status: GoalStatus | null | undefined): string {
  return status ? LABELS[status] : ''
}

export interface Thresholds {
  low: number
  high: number
}

/**
 * Status wartości względem celu — ODPOWIEDNIK `goal_status` z silnika.
 *
 * Używany wyłącznie do podglądu w ustawieniach progów; prawdą pozostaje
 * odpowiedź serwera (05_FRONTEND §5). Oba progi należą do przedziału
 * „prawidłowo" — dokładnie 90% i dokładnie 110% to jeszcze `ok` (D9).
 */
export function statusFor(
  value: number,
  target: number | null,
  thresholds: Thresholds,
): GoalStatus | null {
  if (target === null || !Number.isFinite(target) || target <= 0) {
    return null
  }
  // Mnożymy zamiast dzielić: `2200 / 2000 * 100` daje 110.00000000000001 i
  // dokładnie 110% celu wyszłoby „za dużo" zamiast „prawidłowo" (D9).
  const scaled = value * 100
  if (scaled < target * thresholds.low) {
    return 'below'
  }
  return scaled > target * thresholds.high ? 'above' : 'ok'
}
