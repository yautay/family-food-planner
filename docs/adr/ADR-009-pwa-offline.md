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
