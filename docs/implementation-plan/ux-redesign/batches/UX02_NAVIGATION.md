# UX02 Nawigacja aplikacji

Priorytet P0 · rozmiar M · zależność UX01 · jeden wykonawca.

## Cel

Użytkownik odnajduje cztery główne obszary, a zmiana nazw grup nie zrywa istniejących adresów i sesji. Kontekst: `router.ts`, `lib/navigation.ts`, AppShell, architektura 05/06, ADR-003/006/010.

## Zadania

- [ ] UX02.1 Wprowadzić Plan / Przepisy / Zakupy / Spiżarnia w sidebarze i dolnej nawigacji.
- [ ] UX02.2 Dodać nawigację Planu: Dzień / Tydzień / Podsumowanie. Zachować datę i początek tygodnia przy przejściu między widokami; uzgodnić przekazywanie zakresu do generatora zakupów.
- [ ] UX02.3 Umieścić produkty jako Bibliotekę produktów, ustawienia przy koncie, administrację w osobnej grupie tylko dla ADMIN-a. Zapewnić dostęp do ustawień na telefonie.
- [ ] UX02.4 Zachować obecne adresy i nazwy tras, przekierowania po logowaniu oraz prawidłowo aktywną sekcję dla szczegółów i edytorów. Linki są RouterLink, nie przyciskami udającymi link.
- [ ] UX02.5 Sprawdzić scroll, dolne bezpieczne odstępy i fokus po nawigacji. Publiczna lista nie dostaje AppShell ani żądania sesji.

## Pliki

`frontend/src/layouts/AppShell.vue` i test, `lib/navigation.ts`, `router.ts`, `router.spec.ts`, nowe komponenty nawigacji w domenie, `e2e/smoke.spec.ts`. Wspólne teksty z wyłączną rezerwacją. Od UX03 zmiany tego kontraktu przechodzą przez O.

## Kryteria odbioru i testy

- Każdy stary głęboki link, także konkretny dzień i tydzień, nadal otwiera odpowiedni zasób.
- Cztery dolne przyciski mieszczą się na 360 px i nie zasłaniają ostatniego elementu strony.
- Zwykły użytkownik nie widzi administracji i nie uzyskuje dostępu przez bezpośredni adres.
- Anonimowa lista działa dla użytkownika bez sesji oraz już zalogowanego; nie ujawnia rodzinnego menu.
- `task check`; E2E smoke, logowanie/wylogowanie, stary link dnia/tygodnia, publiczny link. Sprawdzenie klawiaturą i zdjęcia 390/768/1024 px.

Po UX02 O zamraża API komponentów nawigacji i spis tras dla fali równoległej. Aktualizacje: 05_FRONTEND, 06_UIUX i rejestr programu.

Skills: Required SKILL-FE, SKILL-SEC przy guardach/sesji; Review SKILL-REVIEW i SKILL-SECREV dla zmian powierzchni dostępu. Nie zmieniać zasad autoryzacji przy okazji przenoszenia menu.
