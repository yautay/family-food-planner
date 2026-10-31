# UX06 Lista zakupów w sklepie

Priorytet P0 · rozmiar M · zależność UX05 · równolegle z UX04.

## Cel i kontekst

Czytelne zakupy jedną ręką przy zachowaniu poprawnej kolejki offline, publicznych list i druku. Kontekst: ListaZakupowPage, PublicznaListaPage, ShoppingItemRow, ShareListDialog, StorePicker, OfflineBanner, offlineQueue, ADR-009/010.

## Zadania

Ustalenia wykonawcze z UX00 (wznowienie 2026-10-30): zastane wyścigi
enqueue/flush i usuwanie nowszej decyzji tego samego klucza naprawiono przed
przebudową UI, z deterministycznymi regresjami w `offlineQueue.spec.ts`.
Zachować pobudkę po nowym zapisie, atomowe potwierdzanie wersji IDB,
sekwencyjność i backoff. Nie zastępować tej kolejki dla samego wyglądu.
Rzeczywiste zdjęcia dev korzystają z dodanego proxy Vite `/uploads`;
backend nadal egzekwuje sesję. Dowody i awarie zastane: `../BASELINE.md`.

Preflight O przed UX06: test buildu musi objąć także ponowne uruchomienie
prywatnej listy bez sieci i zmianę konta/rodziny w tym samym profilu
przeglądarki. Do sprawdzenia hipoteza z odczytu kodu: `authGuard` wymaga
`ensureLoaded()` po reloadzie, `/auth/*` jest wykluczone z cache SW, a klucze
prywatnego snapshotu/kolejki to obecnie `list:{id}`. Nie uznawać działającej
otwartej karty za dowód restartu i izolacji cache. Najpierw rzeczywisty test;
ewentualną wąską naprawę dostępu/storage przydziela O i obejmuje review Sol.

- [x] UX06.1 Długie nazwy zawijają się, ilości mają własne miejsce, cały wiersz ma wygodne pole trafienia. Ograniczyć ozdobniki; nie zmniejszać obecnego dużego checkboxa.
- [x] UX06.2 Ograniczyć wizualny ciężar kupionych pozycji przez zwijanie ich w obrębie kategorii. Zachować serwerową kolejność kategorii, rozróżnienie `checked` i `already_have` oraz dostępność pozycji do ponownej zmiany.
- [x] UX06.3 Pokazać prawdziwy stan offline/synchronizacji/błędu. Zachować optimistic update, rollback, snapshot, restart aplikacji i semantykę `checked_at`. Reużywać istniejącej kolejki.
- [x] UX06.4 Uporządkować Udostępnij / Drukuj / Sklep / Przyjmij do spiżarni. Potwierdzenie przyjęcia mówi co trafi do zapasów; zmiana sklepu i przyjęcie pozostają niedostępne offline z wyjaśnieniem.
- [x] UX06.5 Zaktualizować publiczną stronę tymi samymi prymitywami wizualnymi, zachowując jej własny klient i zakres danych. Zamiast fikcyjnego „Zakończ zakupy” dać zgodny z istniejącymi danymi powrót do list lub jawne przyjęcie do spiżarni. Trwałe zakończenie jest w UX12.

## Pliki

`pages/zakupy/ListaZakupowPage.vue`, `pages/public/PublicznaListaPage.vue`, `components/domain/ShoppingItemRow.vue`, `ShareListDialog.vue`, `StorePicker.vue`, `OfflineBanner.vue` i testy. `assets/print.css` z wyłączną rezerwacją. Warstwa `lib/offline/**`, `stores/offlineQueue.ts` i klient publiczny tylko jeśli test ujawnia rzeczywistą konieczność — bez przepisywania dla nowego wyglądu.

## Kryteria i testy

Odhaczenie online i offline, odświeżenie offline, powrót sieci, cofnięcie checkboxa, odmowa/konflikt serwera oraz wygasły token mają kontrolowany wynik. Wylogowanie i zmiana rodziny nie pokazują cudzych danych. Publiczna strona nie otrzymuje profili, planów ani prywatnych pól przyjęcia do spiżarni. Dwa wywołania przyjęcia nie podwajają zapasu. Wydruk jest czarno-biały, bez menu i ozdób, a wiersze nie są ucięte.

`task check`; E2E `offline-lista.spec.ts`, `shopping-list-sharing.spec.ts`, właściwe scenariusze pantry. Sprawdzić rzeczywisty zbudowany wariant PWA zgodnie z istniejącą procedurą testu offline, nie tylko tryb Vite. Testy UI nie mogą zastępować realnej próby offline samym mockiem `navigator.onLine`.

Skills: Required SKILL-FE, SKILL-SEC; Review SKILL-REVIEW, SKILL-SECREV. Dokumentacja: offline, publiczny zakres, druk i znaczenie kupionych pozycji.

## Ustalenia odbioru 2026-10-31

- Układ wiersza ma 48 px checkbox i osobną ilość; kupione są zwijane w
  kategorii bez zmiany kolejności serwera i pozostają w DOM do druku.
  Fokus po odhaczeniu przechodzi na rozwinięcie kategorii.
- Błąd terminalnego dropped pozostaje widoczny także przy pustej kolejce.
  Atomowe porównanie wersji intencji nie usuwa nowszego zapisu; przyjęcie do
  spiżarni wymaga udanego reconciliation GET i ma dostępne ponowienie.
- Rzeczywisty preflight ujawnił historyczny wyciek cache między kontami
  i brak prywatnego cold restart. Techniczna naprawa oraz jej granice są
  opisane w ADR-018: shell SW bez API/uploadów, nieautoryzujący namespace,
  kwarantanna legacy, generacje odpowiedzi i osobne QueryClient dla sesji.
  To nie dodaje offline planów ani odtwarzania uprawnień z localStorage.
- `test-pwa` potwierdza cold prywatny/publiczny, kolejkę po restarcie i
  logoutA→B z rzeczywistą odmową404. `test-pwa-advanced` potwierdza dwie
  karty listy/planu, zmianę rodziny i upgrade prawdziwego starego workera.
- `test-shopping-print` tworzy rzeczywiste prywatne/publiczne PDF A4
  z 50 długimi pozycjami. Osobny odbiór obejmuje wszystkie strony PNG,
  ilości, tekst i zakaz przecięcia wiersza. Puste pola do odhaczenia
  ołówkiem pozostają zgodne z arch06; `Mam już w domu` zachowuje tekst.
- Zastępstwo builtin review jest jawnie review Sol zgodnie z D35. Audyty
  zależności raportują zastane alerty, bez zmiany lockfiles; nie są zielone.
- Końcowy check O:675unit/300integration/460API/765FE PASS, pełne normalne
  E2E42PASS/9 jawnych opt-in SKIP, basic PWA3PASS i advanced4PASS wykonane
  oddzielnie. Potwierdzony błąd upgrade RED3→GREEN3 po zachowaniu bezpiecznego
  next w guardzie; poprzednie czerwone przebiegi pozostają w rejestrze.

Rzeczywiste finalne wyniki, otwarte bramki i commit integracji: PROGRESS.md.
