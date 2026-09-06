# ADR-016 — Transfer jedynym importem i eksportem; importer PDF wycofany

Status: ACCEPTED (2026-09-06)

## Kontekst
Aplikacja miała dwie drogi wnoszenia danych: importer PDF (ADR-011 — parser
jadłospisów dietetyczki + asysta AI) i transfer (BATCH_14 — eksport/import
paczki ZIP). Importer kosztował moduł na ~3,9 k linii, dwie zależności
(pdfplumber, anthropic), sekret `ANTHROPIC_API_KEY`, endpoint uploadu 25 MB,
cztery tabele stagingu z pięcioma typami enumowymi i 12 MB dokumentów
zdrowotnych JEDNEJ osoby w repozytorium — a obsługiwał jeden format jednego
dostawcy. Właściciel rozstrzygnął to decyzją **D25** (2026-09-06).

## Decyzja
1. **Importer PDF zostaje usunięty w całości** — kod, testy, staging, ekrany,
   zależności, ustawienia, korpus i dokumenty. ADR-011 ma status
   `SUPERSEDED przez ADR-016`. Treść wniesiona importerem do dziś zostaje:
   to zwykłe encje domenowe, a migracja `0016` kasuje wyłącznie kolumny
   wiążące je ze stagingiem.
2. **Jedynym importem i eksportem aplikacji jest transfer.** Dla użytkownika
   nazywa się „kopia danych rodziny"; dla ADMIN-a istnieje druga, szersza
   droga — kopia całej instancji (`scope=instance`).
3. **Kryterium „co wchodzi do kopii rodziny" to `ScopedQuery.owned_condition`**
   (D26), a nie „wszystko, co ma `household_id` rodziny": encje własne
   członka (także `private`) + encje rodziny o `scope=household` + spiżarnia
   rodziny + profile członków + własne cele i oceny + te wiersze słowników
   globalnych, do których to wskazuje. Prywatne encje INNYCH członków oraz
   ich cele i oceny do pliku nie wchodzą (ADR-006).
4. **Wczytanie kopii SCALA.** Kolizje słowników rozstrzyga klucz naturalny,
   reużyty rodzic nie dostaje drugiego kompletu dzieci (D22), a dzień planu
   scala się po `UNIQUE(owner_user_id, day)` — raport DRY-RUN musi to
   POWIEDZIEĆ i policzyć `to_create` dokładnie (D24 + dług U21).
5. **Reguła na przyszłość: nowy import danych do aplikacji = rozszerzenie
   formatu `transfer`** (sekcja w `serializer.py` + klucz naturalny +
   `parent`, gdy sekcja jest kompozycją), nie nowy moduł ze staging area.
   Osobny moduł importu wolno założyć dopiero wtedy, gdy źródło wymaga
   review z decyzjami człowieka — i to jest wtedy nowa decyzja właściciela.

## Konsekwencje
+ Jedna droga danych zamiast dwóch: mniej kodu, mniej powierzchni ataku
  (znika parser plików binarnych w procesie, jedyne wychodzące wywołanie
  sieciowe i sekret `ANTHROPIC_API_KEY`), krótsza lista zmiennych w prod.
+ Kopia rodziny jest zarazem kopią zapasową i drogą przeniesienia instancji.
− Jadłospisu PDF nie da się wczytać automatycznie: każda nowa dieta wchodzi
  ręcznie (create-in-context) albo z kopii danych.
− `downgrade` migracji `0016` odtwarza PUSTE tabele stagingu — rozstrzygnięć
  review nie da się odzyskać. Przyjęte świadomie (D25).
− W pliku rodziny nie ma sekcji `users`, więc po wczytaniu wszystko należy do
  konta, które kopię wczytało. Pełne odwzorowanie kont ma wyłącznie kopia
  instancji ADMIN-a. UI mówi to wprost (D26).
