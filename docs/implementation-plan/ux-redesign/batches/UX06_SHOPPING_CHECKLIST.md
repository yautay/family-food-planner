# UX06 Lista zakupów w sklepie

Priorytet P0 · rozmiar M · zależność UX05 · równolegle z UX04.

## Cel i kontekst

Czytelne zakupy jedną ręką przy zachowaniu poprawnej kolejki offline, publicznych list i druku. Kontekst: ListaZakupowPage, PublicznaListaPage, ShoppingItemRow, ShareListDialog, StorePicker, OfflineBanner, offlineQueue, ADR-009/010.

## Zadania

- [ ] UX06.1 Długie nazwy zawijają się, ilości mają własne miejsce, cały wiersz ma wygodne pole trafienia. Ograniczyć ozdobniki; nie zmniejszać obecnego dużego checkboxa.
- [ ] UX06.2 Ograniczyć wizualny ciężar kupionych pozycji przez zwijanie ich w obrębie kategorii. Zachować serwerową kolejność kategorii, rozróżnienie `checked` i `already_have` oraz dostępność pozycji do ponownej zmiany.
- [ ] UX06.3 Pokazać prawdziwy stan offline/synchronizacji/błędu. Zachować optimistic update, rollback, snapshot, restart aplikacji i semantykę `checked_at`. Reużywać istniejącej kolejki.
- [ ] UX06.4 Uporządkować Udostępnij / Drukuj / Sklep / Przyjmij do spiżarni. Potwierdzenie przyjęcia mówi co trafi do zapasów; zmiana sklepu i przyjęcie pozostają niedostępne offline z wyjaśnieniem.
- [ ] UX06.5 Zaktualizować publiczną stronę tymi samymi prymitywami wizualnymi, zachowując jej własny klient i zakres danych. Zamiast fikcyjnego „Zakończ zakupy” dać zgodny z istniejącymi danymi powrót do list lub jawne przyjęcie do spiżarni. Trwałe zakończenie jest w UX12.

## Pliki

`pages/zakupy/ListaZakupowPage.vue`, `pages/public/PublicznaListaPage.vue`, `components/domain/ShoppingItemRow.vue`, `ShareListDialog.vue`, `StorePicker.vue`, `OfflineBanner.vue` i testy. `assets/print.css` z wyłączną rezerwacją. Warstwa `lib/offline/**`, `stores/offlineQueue.ts` i klient publiczny tylko jeśli test ujawnia rzeczywistą konieczność — bez przepisywania dla nowego wyglądu.

## Kryteria i testy

Odhaczenie online i offline, odświeżenie offline, powrót sieci, cofnięcie checkboxa, odmowa/konflikt serwera oraz wygasły token mają kontrolowany wynik. Wylogowanie i zmiana rodziny nie pokazują cudzych danych. Publiczna strona nie otrzymuje profili, planów ani prywatnych pól przyjęcia do spiżarni. Dwa wywołania przyjęcia nie podwajają zapasu. Wydruk jest czarno-biały, bez menu i ozdób, a wiersze nie są ucięte.

`task check`; E2E `offline-lista.spec.ts`, `shopping-list-sharing.spec.ts`, właściwe scenariusze pantry. Sprawdzić rzeczywisty zbudowany wariant PWA zgodnie z istniejącą procedurą testu offline, nie tylko tryb Vite. Testy UI nie mogą zastępować realnej próby offline samym mockiem `navigator.onLine`.

Skills: Required SKILL-FE, SKILL-SEC; Review SKILL-REVIEW, SKILL-SECREV. Dokumentacja: offline, publiczny zakres, druk i znaczenie kupionych pozycji.
