# UX05 Zapisane listy i generowanie zakupów

Priorytet P0 · rozmiar M · zależność UX02 · wykonawca B równolegle z UX03.

## Cel i kontekst

Ekran Zakupy zaczyna się od zapisanych list, które nie znikają po wyjściu ze strony. Kontekst: ZakupyPage, ZakupyPreview, RoundConfigSection, api/shoppingLists, api/shopping, shoppingDraft, B10/B11/B12.

## Zadania

- [x] UX05.1 Podłączyć istniejące `fetchShoppingLists` do TanStack Query z paginacją. Pokazać prawdziwą nazwę, sklep, datę i licznik odhaczonych. Zastąpić zależność od lokalnego `createdLists` jako jedynego wejścia do list.
- [x] UX05.2 Ustalić neutralne widoki „Zapisane listy”/„Wszystkie” i ewentualne filtry zgodne z `active/expired`. Nie nazywać wygaśnięcia ukończeniem zakupów. Nie udawać pojedynczej aktywnej listy, jeśli serwer nie zapisuje takiego wyboru; wyróżnienie najnowszej nazwać „Ostatnia lista”.
- [x] UX05.3 Przebudować generator: zakres dat i jawny wybór spiżarni → podgląd → utworzenie. Konfigurację tur przenieść do niższego poziomu; nowy użytkownik bez tur ma widoczną drogę utworzenia pierwszej.
- [x] UX05.4 Zachować wszystkie rozstrzygnięcia podglądu: braki, blokery, ostrzeżenia, warianty sklepowe, opakowania, ilości i resztki. Szczegóły można rozwijać, ale nie ukrywać blokera przed finalizacją.
- [x] UX05.5 Przejąć zakres planu zgodnie z kontraktem UX02. Po finalizacji odświeżyć indeks list; gdy powstaje kilka tur, pokazać wszystkie listy. Błąd nie usuwa wybranego zakresu i odpowiedzi podglądu.

## Pliki i granice

`pages/zakupy/ZakupyPage.vue`, `ZakupyPreview.vue`, `RoundConfigSection.vue`, `stores/shoppingDraft.ts`, ich testy, ewentualne nowe komponenty generatora. `api/shoppingLists.ts` już obsługuje indeks; bez nowej bazy i bez modyfikacji silnika zakupów. Klucze/teksty przez O. Nie dotykać stron konkretnej listy, offline ani publicznego klienta — właściciel UX06.

## Kryteria i testy

- Po utworzeniu, zmianie strony i pełnym odświeżeniu lista nadal jest w katalogu. Wszystkie strony list osiągalne, błąd doładowania nie kasuje wyników.
- `use_pantry` domyślnie false i nie odtwarza się jako domyślna zgoda przy następnej generacji.
- Jedna tura i kilka tur dają prawdziwe listy; błąd finalizacji nie pokazuje sukcesu ani nie resetuje formularza.
- Wygaśnięta lista nie jest usuwana i nie otrzymuje etykiety „zakończona” bez faktu domenowego.
- Vitest stanów i invalidacji; E2E `shopping-generate.spec.ts`, odświeżenie indeksu, wielostronicowy katalog. `task check`; odbiór 390/1024 px.

Skills: Required SKILL-FE; SKILL-CALC tylko jeśli zakres faktycznie dotyka liczenia — preferować istniejące odpowiedzi serwera. Review SKILL-REVIEW. Aktualizować 05_FRONTEND i 06_UIUX; zapewnić kontrakt indeksu dla UX06.
