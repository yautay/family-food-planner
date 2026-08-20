/**
 * Daty planu — wyłącznie kalendarzowe `YYYY-MM-DD`, bez stref czasowych.
 *
 * API operuje datami kalendarzowymi (04_API §1), więc arytmetykę robimy na
 * `Date` w UTC i natychmiast wracamy do tekstu: `new Date("2026-08-17")` jest
 * północą UTC, a lokalne `getDate()` w strefie ujemnej pokazałoby dzień
 * wcześniej. To jedyne miejsce w aplikacji, które liczy na datach.
 */

const MS_PER_DAY = 24 * 60 * 60 * 1000

/** Dni tygodnia po polsku, indeksowane jak `getUTCDay()` (0 = niedziela). */
const WEEKDAYS = ['nd', 'pon', 'wt', 'śr', 'czw', 'pt', 'sob'] as const

/** `Date` → `YYYY-MM-DD` w strefie LOKALNEJ (dla „dziś" liczy się data użytkownika). */
export function isoDate(value: Date): string {
  const year = value.getFullYear()
  const month = `${value.getMonth() + 1}`.padStart(2, '0')
  const day = `${value.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

function toUtc(date: string): Date {
  return new Date(`${date}T00:00:00.000Z`)
}

/** Data przesunięta o `days` dni (ujemne = wstecz). */
export function addDays(date: string, days: number): string {
  const shifted = new Date(toUtc(date).getTime() + days * MS_PER_DAY)
  return shifted.toISOString().slice(0, 10)
}

/** Poniedziałek tygodnia, do którego należy data (tydzień pon–nd, jak w PL). */
export function startOfWeek(date: string): string {
  const weekday = toUtc(date).getUTCDay()
  const offset = weekday === 0 ? -6 : 1 - weekday
  return addDays(date, offset)
}

/** Skrót dnia tygodnia („pon", „wt"…) — etykieta mini-słupków tygodnia. */
export function weekDayLabel(date: string): string {
  return WEEKDAYS[toUtc(date).getUTCDay()] ?? ''
}
