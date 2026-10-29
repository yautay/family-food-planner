# UX01 Wspólny wygląd i komponenty

Priorytet P0 · rozmiar M · zależność UX00 · jeden wykonawca i reviewer.

## Cel i kontekst

Wprowadzić język wizualny „domowa książka kucharska”, opisany w DESIGN_SPEC, bez przepisywania całych stron. Kontekst: architektura 05/06, ADR-007, istniejące UI i `PlanningDialog.vue`.

## Zadania

- [ ] UX01.1 Przenieść paletę, serif nagłówków, skale odstępów i promieni do tokenów. Zachować Inter w treści i formularzach. Sprawdzić polskie znaki oraz stany kontrolek.
- [ ] UX01.2 Przygotować wspólne nagłówki, puste stany, komunikaty błędu z ponowieniem, obszar akcji i zwięzły panel podsumowania. Reużywać shadcn-vue/reka-ui; nie tworzyć drugiego zestawu przycisków.
- [ ] UX01.3 Przygotować komponent dekoracji nagłówka i zastępstwa zdjęcia przepisu: zioła/talerz/kłos, pastelowe powierzchnie i mała kratka. Ukrywać duże ozdoby na wąskich ekranach i wszystkie w druku.
- [ ] UX01.4 Ustalić wspólny dostępny panel akcji dla kolejnych kart: etykieta, opis kontekstu, stan pending, walidacja, fokus, Escape i powrót do wywołującego. Używać mechanizmów istniejącej biblioteki, nie ręcznego focus trap.
- [ ] UX01.5 Zweryfikować komponenty na rzeczywistych reprezentatywnych ekranach/testowych fixture'ach, nie tylko na pustym katalogu komponentów. Przekazać stabilne propsy i zdarzenia do UX02–UX10.

## Pliki i granice

Właściciel: `frontend/src/assets/tailwind.css`, `components/ui/**`, nowe komponenty w `components/domain/` oraz ich testy. Ewentualne `PlanningDialog.vue` zmieniać z zachowaniem kompatybilności do czasu migracji UX07. `main.ts` tylko jeśli wymaga importu stylów; istniejący lokalny font pozostaje.

Bez zmiany API, modeli, routera, kolejki offline i danych. Nie przenosić klasy `.pf-*` ani skryptu makiety do produkcji. Nie dodawać CDN, stockowych zdjęć ani animacji dla samej dekoracji.

## Kryteria odbioru i testy

- Nagłówek, dane i akcja główna zachowują hierarchię przy 360–1440 px; kontrolki nie zlewają się z ozdobami.
- Dekoracje nie mają fokusu, nie są ogłaszane czytnikowi i nie blokują kliknięć.
- Dialog przechodzi klawiaturą otwarcie → wypełnienie → błąd → zamknięcie → powrót fokusu. `pending` zapobiega podwójnemu wysłaniu.
- Sprawdzić kontrast rzeczywistych tokenów, powiększenie tekstu i druk. Zrzuty desktop/mobile mają pokazać również brak zdjęcia.
- Testować zachowanie wspólnego panelu i stanów; nie pisać snapshotów sprawdzających każdy kolor czy promień. `task check`; odpowiednie smoke E2E istniejącego UI po zmianie tokenów.

Skills: Required SKILL-FE; Review SKILL-REVIEW. Dokumentacja: 06_UIUX opisuje wprowadzone tokeny i wzorce; przyszłe zmiany ekranów nadal oznaczone jako planowane. Notatki: komponenty, kontrakty, wyniki i dowody wizualne.
