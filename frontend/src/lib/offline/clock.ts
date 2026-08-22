/**
 * Korekta zegara klienta względem serwera (ADR-009, karta B12 §Frontend).
 *
 * Po co: `checked_at` z kolejki offline rozstrzyga konflikt dwóch telefonów
 * (last-write-wins per pozycja). Telefon z zegarem spóźnionym o 10 minut
 * przegrywałby KAŻDY konflikt, a telefon spieszący się o 10 minut wygrywałby
 * każdy — niezależnie od tego, kto naprawdę odhaczył później. Znacznik musi
 * więc być wyrażony w czasie SERWERA, a nie telefonu.
 *
 * Jak: każda odpowiedź HTTP niesie nagłówek `Date` (RFC 9110 wymaga go od
 * serwerów pochodzenia). Różnica `serverDate − clientNow` to przesunięcie,
 * które doliczamy przy stemplowaniu. Nie potrzebujemy do tego NTP ani osobnego
 * endpointu: pierwsze wejście na listę jest online, więc przesunięcie znamy
 * zanim sieć zniknie.
 *
 * Czego to NIE robi: nie ustawia zegara systemowego i nie próbuje mierzyć
 * opóźnienia sieci (RTT). Przy skali „rodzina w sklepie" sekundy nie mają
 * znaczenia — chodzi o minuty i godziny rozjazdu.
 */

/** Przesunięcie w ms: dodatnie = zegar klienta SPÓŹNIA się względem serwera. */
let skewMs = 0
let known = false

/**
 * Zapamiętaj przesunięcie na podstawie nagłówka `Date` odpowiedzi.
 *
 * Nagłówek ma rozdzielczość jednej sekundy, więc szum rzędu sekundy jest
 * wbudowany — ignorujemy go świadomie (patrz nagłówek pliku).
 */
export function recordServerDate(header: string | null | undefined): void {
  if (!header) {
    return
  }
  const serverMs = Date.parse(header)
  if (Number.isNaN(serverMs)) {
    return
  }
  skewMs = serverMs - Date.now()
  known = true
}

/** Aktualny czas w zegarze SERWERA — tym stemplujemy pozycje kolejki. */
export function nowWithSkew(): Date {
  return new Date(Date.now() + skewMs)
}

/** Wykryte przesunięcie w ms (0, dopóki nie było żadnej odpowiedzi z `Date`). */
export function clockSkewMs(): number {
  return skewMs
}

/** Czy znamy już czas serwera. Diagnostyka i testy — UI tego nie pokazuje. */
export function isClockSkewKnown(): boolean {
  return known
}

/** Reset stanu modułu; wyłącznie dla testów (moduł jest singletonem). */
export function resetClockSkew(): void {
  skewMs = 0
  known = false
}
