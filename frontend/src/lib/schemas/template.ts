/**
 * Walidacja formularzy szablonów, cykli i bloku (05_FRONTEND §5, zod).
 *
 * Walidacja frontowa jest UX-em — prawdą pozostaje odpowiedź serwera (422
 * mapowane na pola). Odwzorowujemy tu reguły backendu, żeby użytkownik nie
 * czekał na rundę HTTP po informację, że wpisał wtorek tam, gdzie musi być
 * poniedziałek.
 *
 * Wyliczanie dat bloku i sekwencji jest tutaj (a nie w komponencie), bo to
 * czysta funkcja z testem jednostkowym — dokładnie jak `block_copy_sequence`
 * po stronie backendu. Obie strony muszą dawać ten sam wynik, inaczej podgląd
 * w dialogu kłamałby o tym, co się stanie po kliknięciu.
 */

import { z } from 'zod'

import { addDays, isoDate, startOfWeek } from '@/lib/dates'
import { week as texts } from '@/lib/texts'

/** Sufity z backendu (`schemas.py`): iloczyn nie może przekroczyć 62 dni. */
export const BLOCK_SOURCE_DAYS_LIMIT = 31
export const BLOCK_REPEAT_LIMIT = 7
export const COPY_TARGETS_LIMIT = 62

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

/** Czy tekst jest poprawną datą kalendarzową (a nie tylko pasuje do wzorca). */
export function isValidIsoDate(value: string): boolean {
  if (!ISO_DATE.test(value)) {
    return false
  }
  const parsed = new Date(`${value}T00:00:00.000Z`)
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value
}

/** Czy data jest poniedziałkiem — ten sam warunek, co `is_week_start` w backendzie. */
export function isMonday(value: string): boolean {
  return isValidIsoDate(value) && startOfWeek(value) === value
}

const isoDateField = z.string().refine(isValidIsoDate, { message: texts.datesInvalid })

/**
 * Lista dat z pola tekstowego („po jednej w wierszu") → tablica ISO.
 *
 * Puste linie i duplikaty odpadają: użytkownik wkleja daty z różnych miejsc,
 * a dwa razy ta sama data znaczyłaby dwa razy dopisane posiłki.
 */
export function parseDateList(raw: string): string[] {
  const seen = new Set<string>()
  for (const line of raw.split(/[\n,;]/)) {
    const value = line.trim()
    if (value) {
      seen.add(value)
    }
  }
  return [...seen]
}

export const dateListSchema = z
  .string()
  .transform(parseDateList)
  .refine((dates) => dates.length > 0, { message: texts.datesRequired })
  .refine((dates) => dates.every(isValidIsoDate), { message: texts.datesInvalid })
  .refine((dates) => dates.length <= COPY_TARGETS_LIMIT, {
    message: `Maksymalnie ${COPY_TARGETS_LIMIT} dat naraz.`,
  })

export const templateSaveSchema = z.object({
  name: z.string().trim().min(1, 'Podaj nazwę szablonu.').max(200),
  scope: z.enum(['private', 'household']),
  kind: z.enum(['day', 'week']),
  /** Wymagany tylko dla `kind === 'day'`. */
  sourceDate: isoDateField.optional(),
})

export type TemplateSaveForm = z.infer<typeof templateSaveSchema>

export const cycleSchema = z.object({
  name: z.string().trim().min(1, 'Podaj nazwę cyklu.').max(200),
  scope: z.enum(['private', 'household']),
  templateIds: z.array(z.number().int().positive()).min(1, texts.cycleNeedsTemplate).max(26),
  startDate: z.union([isoDateField, z.literal('')]).optional(),
})

export type CycleForm = z.infer<typeof cycleSchema>

export const cycleApplySchema = z
  .object({
    dateFrom: isoDateField,
    dateTo: isoDateField,
  })
  .refine((value) => isMonday(value.dateFrom), {
    message: texts.mondayRequired,
    path: ['dateFrom'],
  })
  .refine((value) => value.dateFrom <= value.dateTo, {
    message: 'Data „od” nie może być późniejsza niż data „do”.',
    path: ['dateTo'],
  })

export const blockCopySchema = z
  .object({
    sourceFrom: isoDateField,
    sourceDays: z.coerce.number().int().min(1).max(BLOCK_SOURCE_DAYS_LIMIT),
    repeatEach: z.coerce.number().int().min(1).max(BLOCK_REPEAT_LIMIT),
    targetStart: isoDateField,
  })
  .refine((value) => value.sourceDays * value.repeatEach <= COPY_TARGETS_LIMIT, {
    message: `Blok dawałby więcej niż ${COPY_TARGETS_LIMIT} dni — zmniejsz liczbę dni albo powtórzeń.`,
    path: ['repeatEach'],
  })

export type BlockCopyForm = z.infer<typeof blockCopySchema>

export interface BlockPair {
  source: string
  target: string
}

/**
 * Sekwencja (dzień źródłowy → dzień docelowy) dla „powiel blok".
 *
 * ODPOWIEDNIK `block_copy_sequence` z backendu: każdy dzień powtarza się
 * `repeatEach` razy POD RZĄD, więc 3 dni x 2 dają d1,d1,d2,d2,d3,d3.
 * Podgląd w dialogu musi pokazywać dokładnie to, co zrobi serwer.
 */
export function blockCopySequence(
  sourceFrom: string,
  sourceDays: number,
  repeatEach: number,
  targetStart: string,
): BlockPair[] {
  if (sourceDays < 1 || repeatEach < 1) {
    return []
  }
  const pairs: BlockPair[] = []
  for (let dayIndex = 0; dayIndex < sourceDays; dayIndex += 1) {
    for (let repeatIndex = 0; repeatIndex < repeatEach; repeatIndex += 1) {
      pairs.push({
        source: addDays(sourceFrom, dayIndex),
        target: addDays(targetStart, dayIndex * repeatEach + repeatIndex),
      })
    }
  }
  return pairs
}

/** Preset „2+2+2" z listu dietetyczki (01_PDF_AUDIT §6): 3 dni, każdy 2 razy. */
export const BLOCK_PRESET_2_2_2 = { sourceDays: 3, repeatEach: 2 } as const

/** Domyślne wartości dialogu bloku — źródło = wybrany dzień, cel = tydzień dalej. */
export function defaultBlockForm(sourceFrom: string): BlockCopyForm {
  return {
    sourceFrom,
    targetStart: addDays(sourceFrom, 7),
    ...BLOCK_PRESET_2_2_2,
  }
}

/** Poniedziałek tygodnia zawierającego „dziś" — punkt startowy widoku tygodnia. */
export function currentWeekStart(): string {
  return startOfWeek(isoDate(new Date()))
}
