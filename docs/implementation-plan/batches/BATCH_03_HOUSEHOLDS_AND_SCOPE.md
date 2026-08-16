# BATCH_03 — HOUSEHOLDS_AND_SCOPE

Klasa: FOUND · Zależności: BATCH_02 · Szacunek rozmiaru: S/M

## Goal

Po tym batchu istnieją rodziny (households) z profilami członków, użytkownik
należy do maksymalnie jednej rodziny, a w core działa przetestowany mixin
`ScopedQuery` — jedno miejsce egzekwowania widoczności PRIVATE/HOUSEHOLD dla
wszystkich przyszłych encji współdzielnych. Powstaje też fundament audit
logu (serwis append + przegląd dla admina). ADMIN zarządza rodzinami,
użytkownik ogląda swoją rodzinę i edytuje profile członków w Ustawieniach.

## Context

Zastaje: auth z B02 — `users`/`sessions` w DB, `core/deps.py`
(`current_user`, `require_admin`), CSRF + nagłówki, `/admin/users`,
AppShell z nawigacją (Ustawienia i Admin jako placeholdery), authStore.
`users` NIE ma jeszcze `household_id` (dodaje ten batch). `/auth/me`
zwraca `household: null` (kontrakt do wypełnienia).

Konkrety z wykonanego B02 (2026-08-16) — czytaj przed pisaniem kodu:

- **Autoryzacja**: `app/core/deps.py` → `CurrentUser` / `AdminUser`
  (aliasy `Annotated[User, Depends(...)]`) i `require_admin`. Nowe routery
  ich UŻYWAJĄ, nie duplikują odczytu cookie. `ScopedQuery` (ten batch)
  dokładasz obok, w `app/core/`, nie w module domenowym.
- **Migracja**: pierwsza wolna to `0003`, `down_revision = "0002"`
  (potwierdź `task db-heads`). `users.household_id` dokładasz ALTER-em;
  typ enumowy usuwany jest w `downgrade` jawnie (wzór: `0002`).
- **Rejestr modeli**: nowy moduł z tabelami = jedna linia w
  `backend/app/models.py`, inaczej Alembic nie widzi schematu.
- **Testy z bazą**: fixture'y `db_session` (serwisy) i `db_client` (HTTP)
  w `tests/conftest.py`; dopisz swoje tabele do stałej `DB_TABLES`
  (TRUNCATE między testami). Fabryki: `tests/factories.py`
  (`create_user`, `create_admin`, `create_session`), pomocnicze logowanie
  i nagłówek CSRF: `tests/helpers.py` (`login`, `csrf_headers`).
- **Mutacje w testach API wymagają nagłówka CSRF** — bez niego 403.
- **`/auth/me`**: pole `household` jest w `CurrentUser`
  (`app/modules/accounts/schemas.py`) jako `None`; podmieniasz typ na realny
  schemat rodziny i regenerujesz `task fe-types`.
- **Frontend**: `src/stores/auth.ts` (jedyny stan sesji), guard
  `authGuard` w `src/router.ts`, nawigacja w `src/lib/navigation.ts`
  (dodanie pozycji = jeden wpis), teksty PL w `src/lib/texts.ts`,
  strona admina: `src/pages/admin/AdminUsersPage.vue` (sekcję rodzin
  dokładasz obok, wg karty).
- **Nowa zależność frontendu wymaga odświeżenia node_modules w kontenerze**
  (`docker compose ... exec frontend npm ci` + restart) — wolumen nazwany
  nie aktualizuje się sam.

Wymagane lektury przed startem:

- `docs/implementation-plan/implementation_prompt.md` + PROGRESS.md
  (statusy B01–B02, dziennik może korygować tę kartę).
- `docs/architecture/02_DOMAIN_MODEL.md` §3 (Households, MemberProfile,
  scope — reguły 3.1 WIĄŻĄCE), §12 (Audit — zakres).
- ADR-006 (scope PRIVATE/HOUSEHOLD, jeden household na usera,
  konsekwencja przenosin między rodzinami).
- `docs/architecture/03_DATABASE_DESIGN.md` §2 (households,
  member_profiles, users.household_id), §4 (wzorzec kolumn scope —
  WIĄŻĄCY), §10 (audit_entries).
- `docs/architecture/04_API_DESIGN.md` §2 (/admin/households,
  /households/my, /households/my/profiles, /audit), §3 (scope w serwisach,
  cudze = 404).
- `docs/architecture/07_SECURITY_DESIGN.md` §4 (autoryzacja, anty-IDOR).
- `docs/architecture/08_TESTING_STRATEGY.md` §4 (macierz uprawnień —
  testowana tu na encji przykładowej).
- `docs/architecture/05_FRONTEND_ARCHITECTURE.md` §3 (trasa /ustawienia,
  /admin/*).

## Stages

1. **DB**: moduł `households` (modele Household, MemberProfile) + moduł
   `audit` (model AuditEntry) + migracja: `households`, `member_profiles`,
   `audit_entries`, `users.household_id` (FK NULL, ON DELETE SET NULL).
2. **ScopedQuery w core**: `app/core/scope.py` — mixin/helper serwisowy
   implementujący wzorzec 03_DATABASE §4: kolumny `owner_user_id`,
   `household_id`, `scope ENUM(private,household)`; filtr „widoczne dla
   mnie"; reguły mutacji (edycja HOUSEHOLD: każdy członek; zmiana scope
   i delete: właściciel lub ADMIN; cudze → 404). Walidacja: user bez
   rodziny nie może nadać scope household.
3. **Encja testowa**: `tests/` dostaje przykładowy model `ScopedNote`
   (tabela tworzona wyłącznie w bazie testowej — patrz Notes) konsumujący
   ScopedQuery; na nim pełna macierz testów §4. Żadna encja produkcyjna
   jeszcze nie konsumuje mixinu.
4. **Audit fundament**: `audit/service.py` — `record(action, entity_type,
   entity_id, payload, user_id)` (append-only, wywoływane przez inne
   serwisy); `GET /api/v1/audit` (ADMIN, paginacja limit/offset, filtry
   `?action=&entity_type=&user_id=`). Zapisy podpinane od razu: operacje
   admina na kontach (B02 uzupełnić wstecznie: create/update/delete usera)
   i na rodzinach.
5. **API households**: `/admin/households` CRUD + przypisywanie userów;
   `/households/my` (odczyt własnej rodziny + członkowie);
   `/households/my/profiles` CRUD profili członków (każdy członek rodziny
   może edytować — zaufanie rodzinne, audit rejestruje kto).
6. **Frontend**: `/admin/rodziny` (lista, tworzenie, edycja nazwy,
   przypisywanie/odpinanie użytkowników — select z kont), rozszerzenie
   `/auth/me` → authStore o `household`; `/ustawienia` przestaje być
   placeholderem: sekcja „Moja rodzina" (nazwa, członkowie) + profile
   członków (imię, mnożnik domyślny, cel kcal, aktywność) z inline
   add/edit; pusty stan „Nie należysz do rodziny — poproś administratora".
7. **Testy** (sekcja Tests), regeneracja fe-types, living docs
   (macierz w 08 potwierdzona), PROGRESS.md, commit `batch(03): ...`.

## Database / migrations

Wg 03_DATABASE §2, §10 (WIĄŻĄCE):

- `households`: id, name, created_at/updated_at.
- `member_profiles`: id, household_id FK→households CASCADE NULL,
  owner_user_id FK→users NULL, name, default_multiplier NUMERIC(4,2)
  DEFAULT 1.0, kcal_goal NUMERIC(6,0) NULL, is_active BOOL,
  created_at/updated_at. Profil może istnieć bez konta (dzieci).
- `users.household_id`: FK→households NULL, ON DELETE SET NULL (ALTER).
- `audit_entries`: id, user_id FK→users NULL ON DELETE SET NULL, action
  TEXT, entity_type TEXT, entity_id BIGINT NULL, payload JSONB,
  created_at. Indeks (entity_type, entity_id) + created_at DESC.
- NIE powstaje: `user_nutrition_goals` (B06) ani żadna produkcyjna tabela
  z kolumnami scope (pierwsza: `recipes` w B05).
- Migracja: numer = pierwszy wolny, `down_revision` = `alembic heads`;
  up/down/up zweryfikowane. Tabela encji testowej NIE wchodzi do migracji
  produkcyjnych (tworzona przez metadata w conftest bazy testowej).

## Backend

| Ścieżka | Metoda | Rola | Opis |
|---|---|---|---|
| `/api/v1/admin/households` | GET, POST | ADMIN | lista (paginacja), tworzenie rodziny |
| `/api/v1/admin/households/{id}` | GET, PATCH, DELETE | ADMIN | szczegóły+członkowie, zmiana nazwy, usunięcie (tylko pusta — bez userów i profili; inaczej 409 used_in) |
| `/api/v1/admin/households/{id}/members` | PUT | ADMIN | przypisanie/odpięcie userów (users.household_id) |
| `/api/v1/households/my` | GET | USER | moja rodzina + członkowie + profile; 200 z null gdy brak rodziny |
| `/api/v1/households/my/profiles` | GET, POST | USER (członek) | profile członków mojej rodziny |
| `/api/v1/households/my/profiles/{id}` | PATCH, DELETE | USER (członek) | edycja/dezaktywacja profilu |
| `/api/v1/audit` | GET | ADMIN | dziennik: paginacja, filtry action/entity_type/user_id |

- `ScopedQuery` (core): metody w stylu `visible_for(user)`,
  `get_or_404(id, user)`, `assert_can_delete(entity, user)` — dokładna
  sygnatura = decyzja implementującego, ale użycie musi być jednolinijkowe
  w serwisach konsumujących (to jest produkt tego batcha).
- Serwis households: user bez rodziny → `/households/my` zwraca strukturę
  pustą (nie 404 — to stan legalny); profile dostępne tylko dla członków
  danej rodziny (obcy → 404).
- Audit: wpisy dla create/update/delete household, przypisań członków,
  CRUD profili, operacji na kontach (dopięcie do serwisu accounts z B02).

## Frontend

- `src/pages/admin/AdminHouseholdsPage.vue` (`/admin/rodziny`): lista
  rodzin, tworzenie (dialog), szczegóły z listą członków, przypisywanie
  userów (select kont bez rodziny + odpinanie). Nawigacja Admin dostaje
  podsekcje (Użytkownicy / Rodziny / dalsze w przyszłych batchach).
- `src/pages/UstawieniaPage.vue` (`/ustawienia`): sekcja „Moja rodzina" —
  nazwa, lista członków (konta) i profili; CRUD profili inline (imię,
  mnożnik `AmountInput`-podobny z walidacją dziesiętną, cel kcal,
  przełącznik aktywności). Puste stany wg 06_UIUX §3.2.
- authStore: `household` z `/auth/me` (id, name) — nadal tylko stan sesji.
- Query keys: `households.my`, `households.profiles`, `admin.households`,
  `admin.audit` w `src/api/queryKeys.ts`; mutacje z invalidateQueries.
- (Opcjonalnie, jeśli tanio) `/admin/audit` — prosta tabela dziennika;
  jeśli pominięte, endpoint zostaje bez UI do B04 (odnotować w Notes).

## Security

- Scope = serce autoryzacji danych na resztę projektu: egzekwowany
  WYŁĄCZNIE w serwisach przez ScopedQuery (04_API §3); cudza encja → 404,
  nie 403 (nie potwierdzamy istnienia — 07 §4).
- Anty-IDOR: profile członków — user spoza rodziny nie odczyta/nie zmieni
  (testy macierzy). `/admin/*` za `require_admin`.
- Audit append-only: brak endpointów edycji/usuwania wpisów; payload bez
  haseł (przy operacjach na kontach logować id/email zmienionego pola,
  nigdy hash/hasło).
- Wszystkie nowe mutacje pod CSRF (dziedziczą z middleware B02).

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3. Required
ładowane na starcie sesji (master prompt krok 1f); Review uruchamiane na
diffie przed commitem (krok 11).

- **Required**: SKILL-BE, SKILL-SEC
- **Recommended**: SKILL-FE
- **Review**: SKILL-REVIEW, SKILL-SECREV

## Tests

- **Unit**: walidacje profilu (mnożnik > 0, NUMERIC(4,2); kcal_goal
  dodatni), reguła „user bez rodziny nie nada scope household" (czysta
  logika ScopedQuery).
- **Integration** (na encji testowej ScopedNote — pełna macierz
  08_TESTING §4):
  - odczyt PRIVATE: obcy USER → brak (404 w serwisie), członek rodziny →
    brak, właściciel → OK, ADMIN → OK;
  - odczyt/edycja HOUSEHOLD: członek → OK, obcy → brak;
  - zmiana scope / delete: członek nie-właściciel → 403, właściciel → OK,
    ADMIN → OK;
  - scope household bez household_id → odrzucone (CHECK/serwis);
  - `users.household_id` SET NULL po usunięciu rodziny; kaskada
    member_profiles.
- **API**:
  - macierz na `/households/my/profiles` (anonim 401, obcy 404,
    członek 200);
  - `/admin/households` USER → 403; DELETE rodziny z członkami → 409
    z `details.used_in`;
  - `/audit`: USER → 403; ADMIN → 200; wpis pojawia się po operacji
    admina (create user, create household, edycja profilu) — asercja
    zawartości action/entity_type/user_id;
  - `/auth/me` zawiera household po przypisaniu.
- **Frontend (vitest)**: UstawieniaPage — render profili, walidacja
  formularza profilu; authStore z household.
- **E2E**: rozszerzenie smoke — admin tworzy rodzinę, przypisuje usera,
  user widzi rodzinę w Ustawieniach i dodaje profil członka.

## Acceptance Criteria

1. ADMIN tworzy rodzinę i przypisuje do niej użytkownika na
   `/admin/rodziny`; user po ponownym wejściu widzi rodzinę w Ustawieniach
   i w `/auth/me`.
2. Członek rodziny dodaje/edytuje profile (imię, mnożnik, cel kcal);
   profil bez konta (dziecko) działa.
3. Pełna macierz scope z 08_TESTING §4 przechodzi na encji testowej —
   realne wyniki testów integracyjnych.
4. Operacje admina (konta, rodziny) i edycje profili zostawiają wpisy
   w `audit_entries`; `GET /api/v1/audit` (ADMIN) pokazuje je
   z paginacją.
5. Usunięcie rodziny z członkami → 409 z czytelną listą `used_in`;
   pustej — działa, `users.household_id` czyszczone.
6. User bez rodziny: Ustawienia pokazują stan pusty z instrukcją; próba
   nadania scope household (test serwisowy) odrzucona.
7. `task check` zielony; migracja odwracalna.

## Out of Scope

- Pierwsza produkcyjna encja ze scope (recipes) → BATCH_05; spiżarnia
  (scope zawsze household) → BATCH_08.
- `user_nutrition_goals` i cele żywieniowe → BATCH_06 (profile mają tylko
  kcal_goal jako atrybut skalowania rodzinnego).
- Audit wpisów nutrition before/after → BATCH_04 (tam pierwsze użycie
  payloadu before/after).
- Przenosiny usera między rodzinami z przepinaniem jego encji HOUSEHOLD —
  świadomie NIE (ADR-006, konsekwencje); admin przepina ręcznie
  w przyszłości.
- Rozkład rodzinny porcji w planie (plan_item_servings) → BATCH_06/07.

## Expected files/modules

- `backend/app/modules/households/{models,schemas,service,router}.py`
- `backend/app/modules/audit/{models,schemas,service,router}.py`
- `backend/app/core/scope.py` (ScopedQuery)
- `backend/app/modules/accounts/service.py` (dopięcie audit do operacji
  admina), `app/modules/accounts/router.py` (`/auth/me` + household)
- `backend/migrations/versions/<pierwszy-wolny>_households_audit.py`
- `backend/tests/integration/test_scope_matrix.py` (+ model testowy
  ScopedNote w conftest), `tests/api/test_households*`, `test_audit*`,
  `tests/factories.py` (HouseholdFactory, MemberProfileFactory)
- `frontend/src/pages/UstawieniaPage.vue`,
  `src/pages/admin/AdminHouseholdsPage.vue`, `src/stores/auth.ts`
  (household), `src/api/queryKeys.ts`, `src/api/generated.ts`, router
- `docs/implementation-plan/PROGRESS.md`

## Implementation Notes

- Encja testowa: model SQLAlchemy zdefiniowany w `tests/` na wspólnej
  Base (lub osobnej Base testowej) i tworzony `create_all` w conftest
  bazy testowej — NIE w migracjach. Alternatywy (osobny metadata):
  decyzja implementującego, uzasadnić. Kryterium: `alembic upgrade head`
  na produkcyjnej bazie nie może tworzyć tabel testowych.
- ScopedQuery projektować pod konsumentów B05+ (recipes, plany, listy):
  minimalny interfejs, bez spekulacyjnych opcji. Pantry (B08) ma wariant
  „zawsze household / fallback na usera bez rodziny" — zostawić miejsce,
  nie implementować.
- Kolejność: migracja → scope + testy macierzy (najpierw! to produkt
  batcha) → audit → API households → FE.
- `PUT /admin/households/{id}/members` operuje na `users.household_id`;
  pilnować, by user mógł być tylko w jednej rodzinie (kolumna to
  gwarantuje) i by odpięcie nie kasowało jego member_profile bez potrzeby
  (profil wisi na household — decyzja: przy odpięciu konta profil
  zostaje w rodzinie; uzasadnić w Completion notes jeśli inaczej).
- Audit `record()` wywoływany w tej samej transakcji co operacja
  (spójność: brak wpisu = brak operacji).

## Cross-Batch Impact

- **B04**: audit before/after przy edycji nutrition używa
  `audit.service.record` z payloadem `{before, after}`; wzorzec 409
  `used_in` z DELETE rodziny to prototyp serwisowej blokady usuwania.
- **B05–B11**: KAŻDA encja współdzielna (recipes, plan_days, szablony,
  pantry, shopping) konsumuje ScopedQuery + kolumny wzorca §4 — bez
  wyjątków i bez własnych filtrów widoczności; macierz §4 powtarzana
  w testach API każdego zasobu.
- **B06**: profile członków (default_multiplier, kcal_goal) zasilają
  rozkład rodzinny porcji.
- **B14/B16**: audit rozszerzany o eksport/import i zatwierdzenia PDF.
- Po zakończeniu: dopisać do kart B04/B05 faktyczny import i przykład
  użycia ScopedQuery (żeby świeża sesja nie zgadywała API mixinu).

## Implementation checklist

- [ ] Migracja: households, member_profiles, users.household_id,
      audit_entries (up/down/up OK)
- [ ] core/scope.py — ScopedQuery z regułami 02 §3.1 / 03 §4
- [ ] Encja testowa ScopedNote + pełna macierz integracyjna §4
- [ ] audit/service.record + GET /audit (ADMIN, paginacja, filtry)
- [ ] Audit dopięty do operacji admina na kontach (wstecznie do B02)
- [ ] /admin/households CRUD + members; 409 used_in przy niepustej
- [ ] /households/my + /households/my/profiles CRUD
- [ ] /auth/me zwraca household; authStore zaktualizowany
- [ ] FE: /admin/rodziny, Ustawienia z sekcją rodziny i profilami
- [ ] fe-types zregenerowane; query keys dopisane
- [ ] Testy unit/int/api/fe + rozszerzony E2E
- [ ] PROGRESS.md + propagacja do kart B04/B05

## Verification checklist

- [ ] `task check` zielony
- [ ] `alembic heads` = 1; upgrade → downgrade → upgrade OK; tabele
      testowe NIE powstają z migracji
- [ ] Macierz scope §4: komplet przypadków, realne wyniki w raporcie
- [ ] Testy anty-IDOR na profiles (obcy → 404) przechodzą
- [ ] Wpisy audit weryfikowane asercjami, nie ręcznie
- [ ] Acceptance Criteria 1–7 potwierdzone
- [ ] Living docs + karty przyszłych batchy zaktualizowane;
      commit `batch(03): ...`, status czysty

## Completion notes

(wypełnia agent wykonujący)
