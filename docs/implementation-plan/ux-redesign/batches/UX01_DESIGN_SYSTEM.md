# UX01 Wspólny wygląd i komponenty

Priorytet P0 · rozmiar M · zależność UX00 · jeden wykonawca i reviewer.

## Cel i kontekst

Wprowadzić język wizualny „domowa książka kucharska”, opisany w DESIGN_SPEC, bez przepisywania całych stron. Kontekst: architektura 05/06, ADR-007, istniejące UI i `PlanningDialog.vue`.

## Zadania

- [x] UX01.1 Przenieść paletę, serif nagłówków, skale odstępów i promieni do tokenów. Zachować Inter w treści i formularzach. Sprawdzić polskie znaki oraz stany kontrolek.
- [x] UX01.2 Przygotować wspólne nagłówki, puste stany, komunikaty błędu z ponowieniem, obszar akcji i zwięzły panel podsumowania. Reużywać shadcn-vue/reka-ui; nie tworzyć drugiego zestawu przycisków.
- [x] UX01.3 Przygotować komponent dekoracji nagłówka i zastępstwa zdjęcia przepisu: zioła/talerz/kłos, pastelowe powierzchnie i mała kratka. Ukrywać duże ozdoby na wąskich ekranach i wszystkie w druku.
- [x] UX01.4 Ustalić wspólny dostępny panel akcji dla kolejnych kart: etykieta, opis kontekstu, stan pending, walidacja, fokus, Escape i powrót do wywołującego. Używać mechanizmów istniejącej biblioteki, nie ręcznego focus trap.
- [x] UX01.5 Zweryfikować komponenty na rzeczywistych reprezentatywnych ekranach/testowych fixture'ach, nie tylko na pustym katalogu komponentów. Przekazać stabilne propsy i zdarzenia do UX02–UX10.

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


## Implementacja i dowody 2026-10-30

Baza `1512a09`; kandydaty autora `e3ade07`, `3db3d59`, `559ecae`, `258ebb0`.
Tokeny, komponenty i kontrakty opisano w architekturze 05/06. Nowe PageHeader
oraz RecipeImage mają rzeczywistych konsumentów w dniu i RecipeCard.
PlanningDialog jest kompatybilnym adapterem Reka ActionPanel, pięć paneli
wiąże kontrolki przez scoped formId; AmountInput.form jest addytywny.
Bez zmian API, modeli, routera, kolejki, lockfile ani obliczeń.

Niezależny review Sol zamknął trzy P2: kradzież fokusu przez walidację,
kompozycję formularzy pickera i rozciągane przyciski. Wszystkie mają regresje.
Kontrast niezależnie sprawdzony: tekst pomocniczy/nagłówek 4,79:1,
primary/card 7,28:1, input 3,03–3,46:1. O oraz reviewer obejrzeli realne PNG
nagłówka, obrazów zastępczych, panelu błędu/pending i większego tekstu.
100 PNG na 360/390/768/1024/1440: `backend/data/ux-baseline/screenshots-ux01/`.
10 PNG panelu/siatki: `backend/data/ux01-results/test-results-foundation-fixed/`.

Końcowy `task check` PASS: 590 unit / 292 integration / 443 API / 449 FE,
typy, lint, format, build i OpenAPI. Precache 85 wpisów / 1040,25 KiB
(UX00 68 / 947,89 KiB): nowy modal Reka, ikony i style, bez nowej biblioteki.
Smoke i panel Windows PASS; full Linux 24 PASS / 1 opt-in SKIP.
Drugi full z dodanym testem druku: 25 PASS / 1 opt-in SKIP. Druk CSS
sprawdzony w przeglądarce i na foundation-print.png (O + niezależny reviewer):
czarny nagłówek pozostaje, nawigacja i dekoracja ukryte. Paginowany wydruk
list i pełny browserzoom nadal należą do UX06/UX11.

UX01 odebrane. Finalny lokalny commit: `batch(UX01): wprowadz domowy system wizualny i dostepne panele akcji`.

Windows Chromium dwukrotnie nie pobrał modułu bootstrapu. Zastosowano
opisany w arch08 stabilny target test-e2e-linux dla tej samej suity i danych,
bez alpha i nadpisywania flagów. Visual pozostał na Windows, aby porównywać
z tą samą bazą PNG. Znane stare przepełnienia i hierarchia całej strony
pozostają zadaniami UX02–UX10; odbiór fundamentu nie zamyka tych kart.
