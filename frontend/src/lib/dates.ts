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

/** Pierwszy dzień miesiąca, do którego należy data (preset „Miesiąc" statystyk). */
export function startOfMonth(date: string): string {
  const utc = toUtc(date)
  return `${utc.getUTCFullYear()}-${`${utc.getUTCMonth() + 1}`.padStart(2, '0')}-01`
}

/**
 * Ostatni dzień miesiąca, do którego należy data.
 *
 * Liczymy jako „dzień przed pierwszym dniem następnego miesiąca" — dzięki temu
 * lata przestępne i luty nie wymagają żadnej tabeli długości miesięcy.
 */
export function endOfMonth(date: string): string {
  const utc = toUtc(startOfMonth(date))
  const nextMonth = new Date(Date.UTC(utc.getUTCFullYear(), utc.getUTCMonth() + 1, 1))
  return addDays(nextMonth.toISOString().slice(0, 10), -1)
}

/** Różnica w pełnych dniach kalendarzowych (`to - from`); ujemna = `to` w przeszłości. */
export function daysBetween(from: string, to: string): number {
  return Math.round((toUtc(to).getTime() - toUtc(from).getTime()) / MS_PER_DAY)
}

/** Data w zapisie polskim (`2026-08-21` → `21.08.2026`). */
export function formatDate(date: string): string {
  const [year, month, day] = date.split('-')
  return year && month && day ? `${day}.${month}.${year}` : date
}
