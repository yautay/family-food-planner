import { addDays, daysBetween, startOfWeek } from '@/lib/dates'
import { isValidIsoDate } from '@/lib/schemas/template'

/** Limit prezentacji, nie limit zakresu zapisywanego przez API. */
export const CYCLE_PREVIEW_PAGE_DAYS = 28

export interface DatePreviewWindow {
  dates: string[]
  from: string
  to: string
  totalDays: number
  totalPages: number
  page: number
}

/** Materializuje wyłącznie bieżące okno, niezależnie od długości pełnego zakresu. */
export function datePreviewWindow(
  from: string,
  to: string,
  requestedPage: number,
): DatePreviewWindow | null {
  if (!isValidIsoDate(from) || !isValidIsoDate(to) || from > to) return null
  const totalDays = daysBetween(from, to) + 1
  const totalPages = Math.ceil(totalDays / CYCLE_PREVIEW_PAGE_DAYS)
  const page = Math.max(
    0,
    Math.min(totalPages - 1, Number.isFinite(requestedPage) ? Math.floor(requestedPage) : 0),
  )
  const offset = page * CYCLE_PREVIEW_PAGE_DAYS
  const length = Math.min(CYCLE_PREVIEW_PAGE_DAYS, totalDays - offset)
  const windowFrom = addDays(from, offset)
  return {
    dates: Array.from({ length }, (_, index) => addDays(windowFrom, index)),
    from: windowFrom,
    to: addDays(windowFrom, length - 1),
    totalDays,
    totalPages,
    page,
  }
}

/**
 * Użyte źródła pełnego zakresu, zgodnie z sequences.cycle_week_plan.
 * Po jednej pełnej rotacji dalsze tygodnie nie wprowadzają nowych szablonów.
 */
export function usedCycleTemplateIds(
  templateIds: number[],
  startDate: string | null,
  from: string,
  to: string,
): number[] {
  if (
    !templateIds.length ||
    !isValidIsoDate(from) ||
    !isValidIsoDate(to) ||
    from > to ||
    (startDate !== null && !isValidIsoDate(startDate))
  )
    return []
  const anchor = startDate ? startOfWeek(startDate) : from
  const elapsedWeeks = Math.floor(daysBetween(anchor, from) / 7)
  const usedWeeks = Math.min(templateIds.length, Math.floor(daysBetween(from, to) / 7) + 1)
  const ids = new Set<number>()
  for (let week = 0; week < usedWeeks; week += 1) {
    const index =
      (((elapsedWeeks + week) % templateIds.length) + templateIds.length) % templateIds.length
    const id = templateIds[index]
    if (id !== undefined) ids.add(id)
  }
  return [...ids]
}
