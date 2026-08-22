/**
 * Rejestracja service workera i prompt aktualizacji (ADR-009, karta B12).
 *
 * `registerType: 'autoUpdate'` w `vite.config.ts` znaczy „nowy SW przejmuje
 * kontrolę, gdy tylko będzie gotowy". Sam w sobie jest to jednak zły UX dla
 * TEJ aplikacji: podmiana zasobów w trakcie odhaczania listy przeładowuje
 * stronę i gubi to, co użytkownik właśnie robił w sklepie. Dlatego zamiast
 * cichej podmiany pytamy — jednym `confirm()`, bo to zdarzenie rzadkie, poza
 * jakimkolwiek kontekstem domenowym, i nie zasługuje na własny komponent
 * w widoku krytycznym mobilnym.
 *
 * Import jest DYNAMICZNY: `virtual:pwa-register` to moduł wirtualny wtyczki,
 * który istnieje wyłącznie w buildzie z aktywnym `VitePWA`. W środowisku
 * testowym (vitest, jsdom) go nie ma i statyczny import wysadzałby każdy test
 * importujący `main.ts`.
 */

/** Komunikat po polsku (D3) — bez i18n, jak reszta aplikacji. */
const UPDATE_PROMPT = 'Dostępna jest nowa wersja aplikacji. Odświeżyć teraz?'

export function registerServiceWorker(): void {
  if (typeof window === 'undefined' || !('serviceWorker' in navigator)) {
    return
  }
  void import('virtual:pwa-register')
    .then(({ registerSW }) => {
      const updateSW = registerSW({
        onNeedRefresh() {
          if (window.confirm(UPDATE_PROMPT)) {
            void updateSW(true)
          }
        },
      })
    })
    .catch(() => {
      // Brak modułu (dev bez SW) albo odmowa rejestracji — aplikacja działa
      // wtedy jak zwykłe SPA. Cicho, bo to nie jest awaria dla użytkownika.
    })
}
