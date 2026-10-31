/**
 * Wysyłka pojedynczego odhaczenia z kolejki offline i klasyfikacja wyniku (ADR-009).
 *
 * Ten moduł jest CZYSTĄ warstwą transportu: nie zna Pinii, nie zna TanStack
 * Query i nie decyduje, kiedy flush ma się odbyć. Odpowiada na jedno pytanie —
 * „co zrobić z tym wpisem po próbie wysłania" — bo od tej odpowiedzi zależy,
 * czy kolejka posuwa się do przodu, czy kręci się w kółko.
 *
 * Wyniki i uzasadnienie każdego:
 *
 * - `sent` — serwer przyjął (albo świadomie odrzucił po LWW, bo znacznik był
 *   starszy). W obu przypadkach wpis jest ZAŁATWIONY: odpowiedź 200 niesie stan
 *   aktualny, a ponawianie starszej decyzji nigdy jej nie „przepchnie".
 * - `offline` — żądanie w ogóle nie doszło do serwera (błąd sieci, status 0).
 *   Wpis zostaje **bez zwiększania licznika prób**: telefon w sklepie bywa bez
 *   zasięgu kwadrans, a licznik prób jest zabezpieczeniem przed ŻĄDANIEM,
 *   którego serwer nie chce — nie karą za brak sieci. Liczenie tych prób
 *   kasowałoby odhaczenia po kilku minutach bez sygnału, czyli dokładnie
 *   w scenariuszu, dla którego ta kolejka istnieje.
 * - `retry` — serwer ODPOWIEDZIAŁ, ale przejściowo odmówił: 429 albo 5xx. Wpis
 *   zostaje, flush się zatrzymuje, licznik prób rośnie. 429 jest tu kluczowe —
 *   limit 60/min/IP jest WSPÓLNY dla GET i PATCH całej ścieżki publicznej
 *   (ustalenie R3), więc kolejka z 40 odhaczeniami plus odświeżenia listy
 *   wejdzie w limit przy normalnej pracy. Traktowanie tego jak porażki
 *   gubiłoby zakupy.
 * - `gone` — 404/410. Lista wygasła, została odwołana albo usunięta. Nie ma
 *   dokąd wysyłać: kolejka dla TEGO adresata idzie do kosza, a strona pokazuje
 *   ekran „lista wygasła". Ponawianie byłoby pętlą bez końca (AC 6).
 * - `dropped` — 400/403/422 albo wyczerpane próby. Żądanie jest trwale
 *   niepoprawne; zostawienie go w kolejce zablokowałoby wszystkie następne wpisy,
 *   bo flush jest SEKWENCYJNY.
 * - `session-changed` — odpowiedź należy do wcześniejszej generacji sesji.
 *   Nie potwierdza ani nie odrzuca bieżącej intencji: wpis i licznik prób
 *   zostają, a kolejny flush musi ponownie potwierdzić aktualną sesję.
 *
 * Sekwencyjność nie jest szczegółem implementacji, tylko wymogiem 07_SECURITY §5:
 * równoległy flush wystrzeliłby całą kolejkę w limit rate limitu naraz.
 */

import { ApiError } from '@/api/client'
import {
  PublicListUnavailableError,
  PublicListRequestError,
  checkPublicListItem,
} from '@/api/publicList'
import { updateShoppingListItem } from '@/api/shoppingLists'
import { StaleSessionResponseError } from '@/lib/sessionGeneration'

import type { QueuedCheck } from '@/lib/offline/db'

/**
 * Po tylu ODMOWACH SERWERA wpis znika — inaczej blokowałby kolejkę na zawsze.
 *
 * Licznik rośnie wyłącznie przy wyniku `retry` (serwer odpowiedział 429/5xx).
 * Brak sieci nie jest odmową i prób nie zlicza — patrz nagłówek pliku.
 */
export const MAX_ATTEMPTS = 8

export type SyncOutcome = 'sent' | 'offline' | 'retry' | 'gone' | 'dropped' | 'session-changed'

/** Statusy, po których ponowienie ma sens: przejściowe, nie „złe żądanie". */
function isTransient(status: number): boolean {
  return status === 429 || status >= 500
}

/**
 * Wyślij jedno odhaczenie. Nie rzuca — każdą awarię zamienia na wynik.
 *
 * Ścieżkę wybiera `target`: zalogowana idzie przez `apiFetch` (cookie + CSRF),
 * publiczna przez własny, lekki klient bez cookies (`publicList.ts`). Mieszanie
 * ich byłoby wysłaniem sesji rodziny pod publiczny link.
 */
export async function sendQueued(entry: QueuedCheck): Promise<SyncOutcome> {
  if (entry.attempts >= MAX_ATTEMPTS) {
    return 'dropped'
  }
  try {
    if (entry.target.kind === 'list') {
      await updateShoppingListItem(entry.target.listId, entry.itemId, {
        checked: entry.checked,
        checked_at: entry.checkedAt,
      })
    } else {
      await checkPublicListItem(entry.target.token, entry.itemId, entry.checked, entry.checkedAt)
    }
    return 'sent'
  } catch (error) {
    return classify(error)
  }
}

/** Mapowanie błędu na decyzję o wpisie — jedyne miejsce, które zna te reguły. */
export function classify(error: unknown): SyncOutcome {
  if (error instanceof StaleSessionResponseError) {
    return 'session-changed'
  }
  // Ścieżka publiczna: 404 i 410 mają wspólny typ, bo dla użytkownika to jeden
  // stan („już nie działa"), a rozróżnianie ich zdradzałoby istnienie tokenu.
  if (error instanceof PublicListUnavailableError) {
    return 'gone'
  }
  if (error instanceof PublicListRequestError) {
    return error.status === 0 ? 'offline' : isTransient(error.status) ? 'retry' : 'dropped'
  }
  if (error instanceof ApiError) {
    if (error.status === 0) {
      return 'offline'
    }
    if (error.status === 404 || error.status === 410) {
      return 'gone'
    }
    return isTransient(error.status) ? 'retry' : 'dropped'
  }
  // Nieznany wyjątek (np. błąd w kodzie klienta) — nie ponawiamy w nieskończoność.
  return 'dropped'
}
