# ADR-006 — Scope PRIVATE/HOUSEHOLD; jeden household na użytkownika

Status: ACCEPTED (2026-08-16); **rewizja 2026-10-03: przepisy dostają trzeci zakres `global`** (D32, BATCH_21 — patrz „Aneks” na końcu)

## Kontekst
Rodzina współdzieli przepisy, plany, szablony, listy i spiżarnię; część
danych bywa prywatna. Aplikacja domowa — bez skomplikowanych ACL.

## Decyzja
- Encje współdzielne mają `scope ∈ {PRIVATE, HOUSEHOLD}` + owner_user_id
  + household_id (wzorzec kolumn 03_DATABASE §4, egzekwowany mixinem
  `ScopedQuery` w jednym miejscu).
- Użytkownik należy do **maksymalnie jednej** rodziny (kolumna na users).
- Spiżarnia zawsze HOUSEHOLD (jeden stan domowy); edycja encji HOUSEHOLD
  przez każdego członka (zaufanie rodzinne + audit); zmiana scope
  i usunięcie — właściciel lub ADMIN.
- Słowniki (produkty kanoniczne, kategorie, tagi, sklepy, retail) —
  globalne per instancja.

## Konsekwencje
+ Autoryzacja to jedno zapytanie i jeden mixin; macierz testowa mała
  (08_TESTING §4).
− Przenosiny użytkownika między rodzinami zostawiają jego encje HOUSEHOLD
  w starej rodzinie (household_id nie podąża) — świadome, admin może
  przepiąć ręcznie; odnotować w dokumentacji admina.

## Aneks 2026-10-03 — zakres `global` dla przepisów (D32, BATCH_21)

Właściciel chce wgrywać przepisy dietetyka tak, żeby były dostępne dla KAŻDEJ
rodziny (decyzja **D32**). Decyzja ADR-006 „scope ∈ {PRIVATE, HOUSEHOLD}” zostaje
dla wszystkich encji współdzielnych **poza przepisami**; przepis dostaje trzecią
wartość.

- **Dwa enumy po stronie kodu, jeden typ w bazie.** `Scope` (`private`,
  `household`) obsługuje dni planu, szablony dni i tygodni, cykle, tury, generacje
  i listy zakupów; `RecipeScope` (`private`, `household`, `global`) — wyłącznie
  `Recipe`. W PostgreSQL oba mapują się na ten sam typ `entity_scope`, do którego
  migracja `0017` dodała wartość `global`. Odrzucone: dodanie `GLOBAL` do wspólnego
  `Scope` (każdy USER mógłby wysłać `scope:"global"` dla listy zakupów, a typ
  rozszedłby się po ~18 typach TS) oraz osobny typ PG (`ALTER COLUMN … USING`,
  większa i ryzykowniejsza migracja).
- **Widoczność:** `global` dopisuje do `visible_condition` wyłącznie
  `ScopedQuery(Recipe, …, allow_global=True)`; **nigdy do `owned_condition`** —
  na przynależności stoi eksport „kopii danych rodziny” (D26) i nie ma wciągać
  przepisów całej instancji.
- **Własność:** przepis `global` ma `household_id = NULL` (CHECK
  `ck_recipes_global_without_household`, migracja `0018`) — adres rodziny admina
  blokowałby jej usunięcie, a przy obniżeniu zakresu przepis wpadłby po cichu do
  tej rodziny. Pozostałe siedem tabel ze scope dostało CHECK `scope <> 'global'`.
- **Uprawnienia:** tworzy, edytuje treść i zdjęcie, zmienia zakres z/na `global`,
  archiwizuje i usuwa **wyłącznie ADMIN**, sprawdzany po ROLI (nie po
  `owner_user_id` — zdegradowany były admin nie ma prawa dalej zarządzać).
  Odmowa to **403**, bo przepis jest widoczny; cudzy PRYWATNY przepis zostaje 404.
  Zwykły użytkownik dostaje własną kopię (`POST /recipes/{id}/copy`).
- **Plany, szablony, cykle i listy zakupów** odwołują się do przepisu globalnego
  bezpośrednio, bez kopii. Obniżenie zakresu z `global`, gdy używają go wiersze
  spoza grona ADMIN-a (jego rodziny), to 409 z `used_in`; usunięcie używanego —
  409; wycofanie zużytego przepisu = archiwizacja.
- **Transfer:** import obcina `global` do `household`/`private` każdemu poza
  kopią INSTANCJI wczytaną przez ADMIN-a z właścicielem-ADMIN-em; eksport
  użytkownika dołącza przepisy globalne wskazane przez jego plany i szablony
  (zakres w pliku obcięty).
- **Koszty przyjęte świadomie:** `ADD VALUE` jest NIEODWRACALNE (PostgreSQL nie ma
  `DROP VALUE`); ocena przepisu globalnego liczy średnią ze wszystkich rodzin;
  zdjęcia nadal chroni wyłącznie sesja i nieodgadywalna ścieżka (07_SECURITY §6).
