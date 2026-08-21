/**
 * Progi wyróżnienia daty ważności w spiżarni (widok 6).
 *
 * Architektura nie definiuje tych progów — to decyzja implementacyjna BATCH_08
 * (karta, Implementation Notes pkt 2): **po dacie = czerwień, ≤ 7 dni =
 * bursztyn, dalej neutralnie**. Siedem dni to horyzont jednego cyklu zakupowego
 * (preset tur z 02_DOMAIN §9.2: niedziela + środa), więc „kończy się" znaczy
 * tu „nie doczeka następnych zakupów".
 *
 * Funkcja jest czysta i przyjmuje „dziś" parametrem — dzięki temu test nie
 * zależy od zegara maszyny.
 */

import { daysBetween } from '@/lib/dates'

/** Ile dni przed datą ważności pozycja jest już „kończąca się". */
export const EXPIRY_SOON_DAYS = 7

export type ExpiryStatus = 'none' | 'expired' | 'soon' | 'ok'

/** Status pozycji: brak daty / po terminie / kończy się / w porządku. */
export function expiryStatus(expiryDate: string | null, today: string): ExpiryStatus {
  if (expiryDate === null) {
    return 'none'
  }
  const daysLeft = daysBetween(today, expiryDate)
  if (daysLeft < 0) {
    return 'expired'
  }
  return daysLeft <= EXPIRY_SOON_DAYS ? 'soon' : 'ok'
}
