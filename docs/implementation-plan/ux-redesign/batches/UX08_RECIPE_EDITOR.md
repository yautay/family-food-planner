# UX08 Edytor przepisu

Priorytet P1 · rozmiar M · zależności UX04 i UX07 · równolegle z UX09/UX10.

## Cel

Przepis da się wygodnie zapisać bez przebijania się przez wszystkie opcje jednocześnie. Kontekst: PrzepisEdytorPage, schemat walidacji przepisu, ProductPicker/ProductCreateDrawer, ADR-006/007 i pipeline zdjęć.

## Zadania

- [ ] UX08.1 Sekcje: nazwa/porcje/czas, składniki, przygotowanie; pola dodatkowe rozwijane. Zachować trudność, tagi, widoczność i oceniane wcześniej obowiązkowe pola; nie usuwać funkcji z powodu braku w makiecie.
- [ ] UX08.2 Czytelne wiersze składników z ilością i jednostką. Długie nazwy, małe ekrany, produkt tworzony w kontekście i błąd walidacji nie gubią pozostałych danych.
- [ ] UX08.3 Widoczne Zapisz i stan niezapisanych zmian; po błędzie fokus na właściwym polu, formularz zachowany. Zablokować przypadkowe opuszczenie brudnego formularza, ale po udanym zapisie nie pytać ponownie.
- [ ] UX08.4 Uporządkować zdjęcie: brak, istniejące, przesyłanie i błąd. Zachować ograniczenia pipeline i serwerowe uprawnienia. Nie udawać zapisu zdjęcia przed utworzeniem identyfikatora przepisu.
- [ ] UX08.5 Wyraźny tryb tylko do odczytu dla nieedytowalnego przepisu globalnego i działanie skopiowania go zgodnie z obecną domeną.

## Pliki

`pages/przepisy/PrzepisEdytorPage.vue` i jego testy, `lib/schemas/recipe.ts`, komponenty edytora wydzielone w domenie. ProductPicker/ProductCreateDrawer są wspólne z UX09: zachować kontrakt; zmiany tylko po rezerwacji O. Nie zmieniać scope API, globalnych tokenów ani katalogu przepisów należącego do UX04.

Kontrakt przekazany przez UX04: oba wyjścia edytora (Zapisz → rzeczywisty
szczegół oraz Wróć → katalog) zachowują `catalogQuery(route.query)` z filtrami
`q/tag/scope/prep_time_max` i kontekstem `selectedDate/from/to`. Nie przenosić
arbitralnych `next/offset`. Zachować regresje create/edit × save/back oraz datę
wspólnego panelu po wizycie w edytorze. Nowe zabezpieczenie brudnego formularza
nie może kasować tego kontekstu ani przejmować udanego zapisu.

## Kryteria i testy

Dodanie/edycja składnika i nowego produktu zachowują formularz. Błąd 422/403/409 jest czytelny. Nawigacja z niezapisanymi zmianami pozwala zostać; zapis poprawny zdejmuje ostrzeżenie. Refresh lub awaria przeglądarki nie jest opisywana jako bezpieczna — prawdziwe trwałe szkice są poza kartą.

`task check`; istniejące testy edytora, `recipe-inline-create.spec.ts` i `recipe-global.spec.ts`; scenariusz brudnego formularza klawiaturą, zrzut 390/1024 px. Nie dodawać testów samych dekoracji.

Skills: Required SKILL-FE, SKILL-SEC dla zakresów i uploadu; Review SKILL-REVIEW, SKILL-SECREV przy zmianie obsługi tych obszarów. Dokumentacja: pola podstawowe/dodatkowe i rzeczywiste zabezpieczenie zmian, bez obietnicy autosave.
