# UX08 Edytor przepisu

Priorytet P1 · rozmiar M · zależności UX04 i UX07 · równolegle z UX09/UX10.

## Cel

Przepis da się wygodnie zapisać bez przebijania się przez wszystkie opcje jednocześnie. Kontekst: PrzepisEdytorPage, schemat walidacji przepisu, ProductPicker/ProductCreateDrawer, ADR-006/007 i pipeline zdjęć.

## Zadania

- [x] UX08.1 Sekcje: nazwa/porcje/czas, składniki, przygotowanie; pola dodatkowe rozwijane. Zachować trudność, tagi, widoczność i oceniane wcześniej obowiązkowe pola; nie usuwać funkcji z powodu braku w makiecie.
- [x] UX08.2 Czytelne wiersze składników z ilością i jednostką. Długie nazwy, małe ekrany, produkt tworzony w kontekście i błąd walidacji nie gubią pozostałych danych.
- [x] UX08.3 Widoczne Zapisz i stan niezapisanych zmian; po błędzie fokus na właściwym polu, formularz zachowany. Zablokować przypadkowe opuszczenie brudnego formularza, ale po udanym zapisie nie pytać ponownie.
- [x] UX08.4 Uporządkować zdjęcie: brak, istniejące, przesyłanie i błąd. Zachować ograniczenia pipeline i serwerowe uprawnienia. Nie udawać zapisu zdjęcia przed utworzeniem identyfikatora przepisu.
- [x] UX08.5 Wyraźny tryb tylko do odczytu dla nieedytowalnego przepisu globalnego i działanie skopiowania go zgodnie z obecną domeną.

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

## Odbiór 2026-10-31

Root `task check DB_TEST_RUNTIME=linux` final3 PASS675unit/300integration/
460API/831FE oraz typy/lint/format/build/OpenAPI; precache91/1209,00KiB.
Pełne `task test-e2e-linux` final2 PASS45/9 jawnych opt-in SKIP/2,4min.
Targeted3 PASS5, w tym rzeczywisty USER read-only/kopia, inline create,
pozostanie w brudnym formularzu i prawdziwy zapis po kontrolowanych błędach.
Finalvisual4 PASS1/150PNG na360/390/768/1024/1440, otwarty/zamknięty edytor
i rzeczywiste zdjęcie; osobne8PNG błędów. Niezależny Sol source/security/docs/
visual według D35: brak otwartych P0–P3. Dwa ustalenia wizualne (zasłonięty
fokus i ucięte jednostki) naprawione i sprawdzone rzeczywistymi pomiarami.

Dowody i wcześniejsze FAIL: `backend/data/ux08-results`; finalne obrazy
`backend/data/ux-baseline/screenshots-ux08-final4`. Kalibracja pomiaru natywnej
strzałki i kontrolowany RED→GREEN są jawnie opisane w PROGRESS, bez retry-until-green.
Addytywny `ProductPicker.inputId` zachowuje pozostały kontrakt wyszukiwarki.
Brak zmian backendu, scope, zależności i pipeline zdjęć. Guard nie stanowi
trwałego szkicu. Zdjęcie zapisywane jest osobną operacją dla istniejącego ID.
Zastane alerty audytów zależności pozostają jawne w PROGRESS.
