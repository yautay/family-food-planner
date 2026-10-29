# UX09 Spiżarnia i produkty

Priorytet P1 · rozmiar M · zależności UX06 i UX07 · równolegle z UX08/UX10.

## Cel

Szybko sprawdzić zapasy i poprawić dane składników. Kontekst: SpizarniaPage, ProduktyPage, ProduktFormPage, pantryView, komponenty retail, katalog/units, reguły paginacji i decyzje D13/D15.

## Zadania

- [ ] UX09.1 W spiżarni pokazać zwięzłe wiersze: produkt, ilość/jednostka i termin. Zachować filtry i istniejący wybór widoku. Sekcja „Wykorzystaj najpierw” wynika z rzeczywistych danych.
- [ ] UX09.2 Nie obliczać liczby pilnych produktów z samej pierwszej strony. Jeśli API nie zwraca globalnej agregacji, pokazać uczciwy wycinek z linkiem do serwerowego filtra terminu, bez pozornego licznika całej spiżarni.
- [ ] UX09.3 Ułatwić zmianę ilości i dodanie zapasu; zachować stan filtrów/paginacji po operacji. Brak daty nie znaczy „świeży”, a bliski termin nie jest gwarancją bezpieczeństwa produktu.
- [ ] UX09.4 Przebudować bibliotekę i formularz produktu: nazwa, miara i podstawowe dane na początku, wartości, jednostki domowe oraz warianty sklepowe w czytelnych sekcjach. Zachować create-in-context i ostrzeżenia o niekompletności.
- [ ] UX09.5 Zachować uprawnienia do usuwania, archiwizacji, miary i wagi sztuki oraz komunikaty 409. Produkty globalnego katalogu nie stają się prywatne przez nowy wygląd.

## Pliki

`pages/spizarnia/SpizarniaPage.vue`, `pages/produkty/{ProduktyPage,ProduktFormPage}.vue`, PantryItemCard/Row, ExpiryBadge, RetailProductsSection i testy. Kontrakty ProductPicker/ProductCreateDrawer współdzielone z UX08 — zmiany przez O. Nie dotykać SklepySection ani edytora kolejności kategorii (UX10). Bez nowego silnika wyszukiwania przepisów ze spiżarni.

## Kryteria i testy

Paginacja nie znika, aktualna pozycja i filtry zostają po edycji. Ilości typu 0,25 i jednostki domowe przechodzą istniejący pipeline; nie powstają lokalne przeliczniki. Etykiety terminów i braku daty są czytelne. Nieuprawniona zmiana miary nie staje się dostępna po przeniesieniu pola.

`task check`; `pantry.spec.ts`, `produkty.spec.ts`, właściwe scenariusze `retail-stores.spec.ts` i paginacji; kontrola 390/1024 px. Testować zachowanie i kompletność danych, nie wygląd liścia.

Skills: Required SKILL-FE, SKILL-CALC przy ilościach; SKILL-SEC przy uprawnieniach; Review SKILL-REVIEW i SKILL-SECREV dla zmian kontroli dostępu. Dokumentacja: grupowanie pól, paginacja i znaczenie sekcji pilnych zapasów.
