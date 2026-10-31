import type { MemberProfile } from '@/api/households'
import type { PlanServingSplit, PlanServingSplitInput } from '@/api/planning'
import { isValidDecimal, normalizeDecimalInput, sumDecimals, toDecimalInput } from '@/lib/decimal'

/** Szkic formularza, nie odpowiedź HTTP. Zachowuje także historyczne profile. */
export interface PortionRow {
  id: number
  name: string
  active: boolean
  value: string
}

export function portionRows(profiles: MemberProfile[], split: PlanServingSplit[]): PortionRow[] {
  const stored = new Map(split.map((entry) => [entry.member_profile_id, entry]))
  const rows = profiles.map((profile) => ({
    id: profile.id,
    name: profile.name,
    active: profile.is_active,
    value: toDecimalInput(
      stored.get(profile.id)?.multiplier ??
        (split.length === 0 && profile.is_active ? profile.default_multiplier : '0'),
    ),
  }))
  for (const entry of split) {
    if (!rows.some((row) => row.id === entry.member_profile_id)) {
      rows.push({
        id: entry.member_profile_id,
        name: entry.member_name,
        active: false,
        value: toDecimalInput(entry.multiplier),
      })
    }
  }
  return rows
}

/** Waliduj PRZED sumDecimals/BigInt; limit jak NUMERIC API, bez floatów. */
export function validPortion(value: string, maximum: string, allowZero = false): boolean {
  if (!isValidDecimal(value, { decimalPlaces: 2 })) return false
  const normalized = normalizeDecimalInput(value)
  if (!allowZero && /^0+(\.0+)?$/.test(normalized)) return false
  return !sumDecimals([maximum, `-${normalized}`]).startsWith('-')
}

export function portionSplit(
  rows: PortionRow[],
): (PlanServingSplitInput & { multiplier: string })[] | null {
  if (rows.some((row) => row.value.trim() !== '' && !validPortion(row.value, '99.99', true)))
    return null
  return rows
    .filter(
      (row) => row.value.trim() !== '' && !/^0+(\.0+)?$/.test(normalizeDecimalInput(row.value)),
    )
    .map((row) => ({ member_profile_id: row.id, multiplier: normalizeDecimalInput(row.value) }))
}
