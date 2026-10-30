# UX02 Nawigacja aplikacji

Priorytet P0 · rozmiar M · zależność UX01 · jeden wykonawca.

## Cel

Użytkownik odnajduje cztery główne obszary, a zmiana nazw grup nie zrywa istniejących adresów i sesji. Kontekst: `router.ts`, `lib/navigation.ts`, AppShell, architektura 05/06, ADR-003/006/010.

## Zadania

- [x] UX02.1 Wprowadzić Plan / Przepisy / Zakupy / Spiżarnia w sidebarze i dolnej nawigacji.
- [x] UX02.2 Dodać nawigację Planu: Dzień / Tydzień / Podsumowanie. Zachować datę i początek tygodnia przy przejściu między widokami; uzgodnić przekazywanie zakresu do generatora zakupów.
- [x] UX02.3 Umieścić produkty jako Bibliotekę produktów, ustawienia przy koncie, administrację w osobnej grupie tylko dla ADMIN-a. Zapewnić dostęp do ustawień na telefonie.
- [x] UX02.4 Zachować obecne adresy i nazwy tras, przekierowania po logowaniu oraz prawidłowo aktywną sekcję dla szczegółów i edytorów. Linki są RouterLink, nie przyciskami udającymi link.
- [x] UX02.5 Sprawdzić scroll, dolne bezpieczne odstępy i fokus po nawigacji. Publiczna lista nie dostaje AppShell ani żądania sesji.

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


## Implementacja i dowody 2026-10-30

Baza `90fd42d`; autor `89b2101`, delta rzeczywistego USER `7616e73`,
regresje dat `3a7e841`, portal print/gotowość SPA `f617e9e`.
NAV_ITEMS, PlanNavigation, AccountNavigation i stabilne helpery opisano
w arch05/06 oraz CONTRACTS. Stare URL-e/guardy pozostały; query
selectedDate/from/to jest kontraktem do UX03/05/07/10. Przejęcie zakresu
przez generator pozostaje UX05. Bez zmian API/obliczeń/offline.

Autor: 481 FE / typy / lint / format PASS. Niezależny review Sol zamknął
trzy P2: stara kotwica presetów, utrata offsetu w poniedziałek, druk portalu.
Regresje dat najpierw 3 FAIL, po poprawce 481 PASS. Pierwszy full O miał
29 PASS / 1 FAIL skiplink / 1 SKIP visual / 1 niewykonany; trace wykazał
Tab przy pustym app po reloadzie. Test czeka teraz na gotową SPA,
bez wymuszenia fokusu, sleep lub retry.

Po poprawkach full `e2e-final-2.log`: 31 PASS / 1 SKIP osobnego visual.
Prawdziwy USER: logowanie, auth/me, brak menu admin, guard i API403 PASS;
własne konto sprzątane przez API. Obie sesje publicznego URL nie wołają auth.
Visual Windows `visual-final.log`: 1 PASS / 100 PNG na360/390/768/1024/1440.
Osobne4PNG ADMINmobile/USERdesktop i ich CSS print: menu mieści się,
długa polska nazwa zawija, druk zachowuje treść bez menu. O + reviewer
obejrzeli dowody. Artefakty: backend/data/ux02-results oraz
backend/data/ux-baseline/screenshots-ux02. Stare overflow dnia nie są maskowane;
układ dnia pozostaje UX03. To nie odbiór wielostronicowego PDF.

Końcowy task check PASS: 590 unit / 292 integration / 443 API / 481 FE,
typy/lint/format/build/OpenAPI. Drugi kolejny full `e2e-final-3.log`: także
31 PASS / 1 opt-in SKIP. PWA75 wpisów1098,26KiB. Niezależny review kodu,
dokumentacji i PNG bez otwartych ustaleń. UX02 odebrane i utrwalane lokalnym
commitem `batch(UX02): uporzadkuj nawigacje i zachowaj kontekst planu`.
Następna fala UX03 + UX05 startuje z tej samej zintegrowanej bazy.
