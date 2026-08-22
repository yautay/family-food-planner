# ADR-009 — PWA offline: IndexedDB + kolejka synchronizacji checkboxów

Status: ACCEPTED (2026-08-16)

## Kontekst
Lista zakupowa musi działać w sklepie bez zasięgu; wymóg: bez przesadnie
skomplikowanego systemu realtime.

## Decyzja
- vite-plugin-pwa (Workbox): precache shella SPA; `/api/*` NetworkFirst.
- Otwarta lista zapisywana do IndexedDB (idb). Odhaczenia offline →
  lokalna kolejka mutacji; po odzyskaniu sieci PATCH per pozycja.
- Konflikt: last-write-wins per pozycja po `checked_at` (timestamp
  klienta korygowany o przesunięcie zegara z nagłówka Date serwera).
- Dotyczy widoku zalogowanego i publicznego `/l/:token`.
- Bez WebSocketów; współdzielona lista odświeża się pollingiem przy
  focusie karty (TanStack Query refetchOnWindowFocus).

## Konsekwencje
+ Dwie osoby z tą samą listą mogą rzadko nadpisać sobie checkbox — koszt
  akceptowany (skala rodzinna), UX zawsze responsywny.
− Kolejka offline wymaga testów vitest (scenariusze: offline→online,
  podwójne odhaczenie, wygaśnięcie tokenu w trakcie).

## Stan wdrożenia (BATCH_12, 2026-08-22)

Decyzja zrealizowana w całości; szczegóły techniczne trzyma 05_FRONTEND §6.
Trzy rzeczy, których ADR nie przewidział, a które okazały się częścią kontraktu:

1. **429 to stan przejściowy, nie porażka mutacji.** Limit 60/min/IP jest
   WSPÓLNY dla GET i PATCH całej ścieżki publicznej (ustalenie R3), więc
   kolejka z kilkudziesięcioma odhaczeniami wchodzi w niego przy normalnej
   pracy. Flush jest sekwencyjny i zatrzymuje się z backoffem, zamiast gubić
   zmiany.
2. **`checked_at` z przyszłości trzeba przycinać.** Bez tego telefon
   z zegarem spieszącym o godziny zabetonowałby pozycję: żadna późniejsza
   decyzja nie byłaby od jego znacznika młodsza. Próg: 5 minut.
3. **Zmiana sklepu nie wchodzi do kolejki.** Kolejność sekcji składa serwer
   z profilu `store_category_order`, więc offline nie da się jej przeliczyć bez
   złamania reguły „jedna lista = jedna kolejność na ekranie, w druku i pod
   linkiem" (B11).
