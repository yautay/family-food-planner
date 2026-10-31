# UX09 Spiżarnia i produkty

Priorytet P1 · rozmiar M · zależności UX06 i UX07 · równolegle z UX08/UX10.

## Cel

Szybko sprawdzić zapasy i poprawić dane składników. Kontekst: SpizarniaPage, ProduktyPage, ProduktFormPage, pantryView, komponenty retail, katalog/units, reguły paginacji i decyzje D13/D15.

## Zadania

- [x] UX09.1 W spiżarni pokazać zwięzłe wiersze: produkt, ilość/jednostka i termin. Zachować filtry i istniejący wybór widoku. Sekcja „Wykorzystaj najpierw” wynika z rzeczywistych danych.
- [x] UX09.2 Nie obliczać liczby pilnych produktów z samej pierwszej strony. Jeśli API nie zwraca globalnej agregacji, pokazać uczciwy wycinek z linkiem do serwerowego filtra terminu, bez pozornego licznika całej spiżarni.
- [x] UX09.3 Ułatwić zmianę ilości i dodanie zapasu; zachować stan filtrów/paginacji po operacji. Brak daty nie znaczy „świeży”, a bliski termin nie jest gwarancją bezpieczeństwa produktu.
- [x] UX09.4 Przebudować bibliotekę i formularz produktu: nazwa, miara i podstawowe dane na początku, wartości, jednostki domowe oraz warianty sklepowe w czytelnych sekcjach. Zachować create-in-context i ostrzeżenia o niekompletności.
- [x] UX09.5 Zachować uprawnienia do usuwania, archiwizacji, miary i wagi sztuki oraz komunikaty 409. Produkty globalnego katalogu nie stają się prywatne przez nowy wygląd.

## Pliki

`pages/spizarnia/SpizarniaPage.vue`, `pages/produkty/{ProduktyPage,ProduktFormPage}.vue`, PantryItemCard/Row, ExpiryBadge, RetailProductsSection i testy. Kontrakty ProductPicker/ProductCreateDrawer współdzielone z UX08 — zmiany przez O. Nie dotykać SklepySection ani edytora kolejności kategorii (UX10). Bez nowego silnika wyszukiwania przepisów ze spiżarni.

## Kryteria i testy

Paginacja nie znika, aktualna pozycja i filtry zostają po edycji. Ilości typu 0,25 i jednostki domowe przechodzą istniejący pipeline; nie powstają lokalne przeliczniki. Etykiety terminów i braku daty są czytelne. Nieuprawniona zmiana miary nie staje się dostępna po przeniesieniu pola.

`task check`; `pantry.spec.ts`, `produkty.spec.ts`, właściwe scenariusze `retail-stores.spec.ts` i paginacji; kontrola 390/1024 px. Testować zachowanie i kompletność danych, nie wygląd liścia.

Skills: Required SKILL-FE, SKILL-CALC przy ilościach; SKILL-SEC przy uprawnieniach; Review SKILL-REVIEW i SKILL-SECREV dla zmian kontroli dostępu. Dokumentacja: grupowanie pól, paginacja i znaczenie sekcji pilnych zapasów.

## Odbiór 2026-10-31

Root `task check DB_TEST_RUNTIME=linux` final3 PASS675unit/300integration/
460API/852FE oraz wszystkie statyki/build/OpenAPI94/1220,53KiB.
Pełne `task test-e2e-linux` final2 PASS46/9 jawnych opt-in SKIP/2,6min.
Targeted3 PASS8/28,2s: wskazane istniejące scenariusze oraz inline create,
105partii/55produktów, rzeczywisty zapis0,25g, filtry/strony/fokus/coldreturn,
klawiatura i pełne komunikaty API w rozwinięciach. Source7d9039 i dodatkowa
zmiana recipe-inline zachowują wpisane wyszukiwanie przed debounce oraz
pozostały kontekst po usunięciu, bez focus na usuniętym ID; kontrolowany
RED→GREEN jest udokumentowany.

Finalvisual1 na6398901 PASS1/150PNG na360/390/768/1024/1440 oraz9PNG targeted.
Niezależny Sol obejrzał15zmienionych widoków i kontrolę. Odbiór tych PNG
pozostaje ważny dla7d9039: późniejszy diff zmienia wyłącznie linki/callback
usuwania i testy, bez zmian szablonów/CSS; zachowanie zostało ponownie
sprawdzone. Nie deklarujemy ponownego przebiegu macierzy7d.
Source/security/docs/visual review Sol według D35: bez otwartych P0–P3.

Dowody i wcześniejsze FAIL: `backend/data/ux09-results`; macierz
`backend/data/ux-baseline/screenshots-ux09-final1`. Podgląd terminów jest
ograniczonym wycinkiem serwera. Trzystronny budżet automatycznego odtwarzania
nie ogranicza ręcznej paginacji ani zachowanego cache. Brak nowych reguł
backendu, konwersji ilości, uprawnień lub zależności. Zastane alerty audytów
pozostają jawne w PROGRESS.
