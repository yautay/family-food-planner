# BATCH_14 — IMPORT_EXPORT

Klasa: PLAT · Zależności: R3 (istnieją wszystkie encje core: catalog,
recipes, planning, pantry, shopping) · Bramki decyzji: brak · Rozmiar: **M**
· Dozwolona równoległość: **B12 ∥ B13 ∥ B14** (osobne worktree, kolizje —
patrz Cross-Batch Impact).

## Goal

Dane należą do użytkownika: batch dostarcza pełny eksport logiczny (JSON
z wersją schematu + ZIP ze zdjęciami) i import z walidacją wersji, raportem
DRY-RUN i zastosowaniem w jednej transakcji, z mapowaniem kolizji po
`normalized_name`. USER eksportuje/importuje swoje dane (i rodziny), ADMIN —
całą instancję. Pełne odzyskanie danych bez SaaS (02_DOMAIN §11).

## Context

Batch zastaje (po R3):

- **B12 wszedł równolegle i ZOSTAWIA ŚLADY, o które trzeba zadbać przy merge'u**
  (00_MASTER §5): (a) migracja `0013_shopping_item_received_at` — jeśli ten
  batch startował z gałęzi sprzed B12, jego „pierwszy wolny numer" też wypadł
  na `0013`; po merge'u sprawdź `task db-heads` i przy dwóch głowach zrób
  migrację scalającą PRZED `task check`; (b) `frontend/package.json` +
  lockfile — B12 dołożył `idb` i `fake-indexeddb`, konflikt rozwiązuje się
  UNIĄ zależności, po czym `npm ci` w kontenerze frontendu; (c) pola
  `received_at` (pozycja listy) i `already_received` (odpowiedź
  `accept-to-pantry`) są w `frontend/src/api/generated.ts` — po merge'u
  przepuść `task fe-types` i zacommituj wynik zamiast ręcznie sklejać diff.

- Moduł `backend/app/modules/transfer/` — pusty szkielet (struktura
  z ADR-001); mapa API rezerwuje `A /transfer/export /transfer/import`
  (04_API §2) — UWAGA: eksport użytkownika wymaga rozszerzenia mapy o
  wariant `U` (ten batch dopisuje, patrz Backend).
- Wszystkie encje domenowe core (03_DATABASE §2–§8): catalog (produkty
  kanoniczne, kategorie, unit-weights, retail, sklepy, tagi), recipes,
  planning (dni/szablony/cykle), pantry, shopping (konfiguracje tur, listy),
  goals, member_profiles.
- **Kontrakt payloadu szablonów (stan faktyczny po B07)** — eksport i import
  MUSZĄ go respektować, bo payload to JSONB, a nie relacje:
  - `day_templates.payload`:
    `{v: 1, title: str|null, meals: [{name, kcal_target: str|null, position,
    items: [{recipe_id|product_id, amount: str|null, amount_unit: str|null,
    servings: str, position, servings_split: [{member_profile_id,
    multiplier: str}]}]}]}`,
  - `week_templates.payload`: `{v: 1, days: [{offset: 0..6, day: <payload dnia>}]}`,
  - `week_cycles`: `name`, `template_ids BIGINT[]` (kolejność = rotacja),
    `start_date DATE|null`.
  Wszystkie liczby w payloadzie są STRINGAMI dziesiętnymi (ADR-008) — import,
  który wpuści floaty, cicho zepsuje ilości. Schematy Pydantic do reużycia:
  `planning/schemas.py::{DayTemplatePayload, WeekTemplatePayload}` (walidują
  też przy odczycie, `extra="forbid"`, `v` jako `Literal[1]`).
  **Import MUSI przemapować id**: `recipe_id`/`product_id`/`member_profile_id`
  wewnątrz payloadu i `template_ids` w cyklach to referencje, których baza nie
  pilnuje FK — po remapowaniu trzeba je zwalidować, inaczej instancjacja
  szablonu padnie 422 (`_assert_references_alive`) albo zostawi cykl
  wskazujący w pustkę. Zmiana kształtu payloadu = `v: 2` + konwersja przy
  odczycie (nie ma jej jeszcze).
  **Doprecyzowanie review R2 (2026-08-21):** cykl z JEDNYM martwym
  `template_ids` jest niesprawny CAŁY, nie tylko w tygodniu, w którym ten
  szablon wypada — `TemplatesService.apply_cycle` sprawdza istnienie
  i widoczność wszystkich id z listy przed instancjacją i zwraca 422
  `CYCLE_TEMPLATES_UNKNOWN`. Import, który przepisze `template_ids` bez
  remapowania, zamieni więc cykl w encję nieużywalną, a nie „częściowo
  działającą". Walidację referencji rób w imporcie, nie licz na to, że
  instancjacja pominie brakujący tydzień.
- `audit_entries` (03_DATABASE §10) + serwis audytu z B03; storage uploadów
  `/data/uploads` (03_DATABASE §11) ze zdjęciami przepisów/produktów.
- Strony `UstawieniaPage` i `AdminPage` (05_FRONTEND §3).

Wymagane lektury: 02_DOMAIN §11 (kontrakt transferu) i §12 (audit),
03_DATABASE (pełny przegląd encji — co wchodzi do eksportu), 04_API §1–§2,
07_SECURITY §6 (upload ZIP!), 08_TESTING §2, ADR-012 (archiwizacja —
encje archiwalne też eksportujemy).

## Stages

1. **Format i serializacja** — definicja formatu (wersja `1`), eksport
   użytkownika do JSON; test round-trip serializacji na fabrykach.
2. **Eksport ZIP** — pakowanie JSON + zdjęcia (`photos/…`), streaming
   odpowiedzi; wariant ADMIN (cała instancja: + users bez haseł? NIE —
   patrz Implementation Notes).
3. **Import DRY-RUN** — walidacja wersji + raport kolizji/nowości bez
   żadnego zapisu.
4. **Import APPLY** — zastosowanie w jednej transakcji wg decyzji mapowania
   kolizji; wpis audit; rollback przy jakimkolwiek błędzie.
5. **UI** — Ustawienia (eksport/import własnych danych), Admin (instancja);
   ekran raportu dry-run z wyborami per kolizja.
6. **Testy + docs** — round-trip na czystej bazie; sekcja formatu dopisana
   do `docs/architecture/04_API_DESIGN.md`; PROGRESS.md.

## Database / migrations

**Brak nowych tabel** (eksport nie ma tabel — 03_DATABASE §10); import
loguje się w `audit_entries`. Jeśli okaże się potrzebna kolumna (np.
znacznik pochodzenia z importu) — decyzja do 02_DECISIONS, nie zgadywać
(B12/B13 idą równolegle; po merge'u `alembic heads` = jedna głowa).

## Backend

| Ścieżka | Metoda | Rola | Opis |
|---|---|---|---|
| `/api/v1/transfer/export` | POST | U | eksport danych użytkownika+rodziny → ZIP (stream) |
| `/api/v1/transfer/export?scope=instance` | POST | A | eksport całej instancji |
| `/api/v1/transfer/import` | POST | U/A | upload ZIP → `dry_run` raport (nic nie zapisuje) |
| `/api/v1/transfer/import/{import_id}/apply` | POST | U/A | zastosowanie z decyzjami kolizji |

Format (dokumentowany w 04_API — sekcja „Format eksportu transfer v1"):

- ZIP: `export.json` + `photos/<plik>` (ścieżki względne z DB).
- `export.json`: nagłówek `{schema_version: 1, app_version, exported_at,
  scope: "user"|"instance"}` + sekcje per encja (kolejność = kolejność
  importu, od słowników do zależnych): `product_categories`, `nutrients`,
  `tags`, `stores` (+`store_category_order`), `canonical_products`
  (+`product_unit_weights`, `product_nutrient_values`), `retail_products`,
  `recipes` (+ingredients, tags, ratings), `member_profiles`,
  `user_nutrition_goals`, `plan_days` (+meals+items+servings),
  `day_templates`, `week_templates`, `week_cycles`, `pantry_items`,
  `shopping_round_configs`, `shopping_lists` (+items; **bez**
  `public_token` — patrz Security). Scope `instance` dodatkowo: `users`
  (bez `password_hash`!), `households`, `audit_entries`.
- ID w pliku = oryginalne ID **jako referencje wewnętrzne** — import
  buduje mapę stary→nowy ID, nigdy nie wstawia ID wprost.
- Ilości/wartości jako stringi dziesiętne (04_API §1).

Serwis `transfer/service.py`:

- **Eksport U**: encje `owner_user_id = user` + household usera (scope
  wzorzec); słowniki globalne (produkty/kategorie/sklepy/tagi) — tylko
  te **referencjonowane** przez eksportowane encje (spójny, samowystarczalny
  plik). **Eksport A**: wszystko.
- **DRY-RUN**: parsowanie + walidacja `schema_version` (≠1 ⇒ 422
  z komunikatem „Plik pochodzi z nowszej/innej wersji aplikacji…"),
  wykrywanie kolizji po `normalized_name` (produkty kanoniczne, kategorie,
  sklepy, tagi — słowniki globalne) i po nazwie w scope (przepisy,
  szablony). Raport: `{to_create: {...liczby per encja}, collisions:
  [{entity, name, existing_id, default: "use_existing"}], warnings}`.
  Plik ZIP zapisany tymczasowo pod `import_id` (scratch w uploads,
  sprzątany po apply/24 h).
- **APPLY**: body = decyzje per kolizja (`use_existing` | `create_copy` —
  kopia dostaje sufiks „(import)" w nazwie i nowy normalized_name); całość
  w JEDNEJ transakcji; zdjęcia kopiowane pod nowe losowe nazwy; produkty
  tworzone z importu = `verification_status` zachowany z pliku (instancja)
  lub `unverified` (import cudzego pliku przez USERA); wpis
  `audit_entries` (action `transfer.import`, payload: liczby + decyzje).

## Frontend

- `UstawieniaPage` — sekcja „Twoje dane": przycisk „Eksportuj moje dane"
  (pobiera ZIP) + „Importuj z pliku" → `TransferImportDialog`.
- `AdminPage` — sekcja „Instancja": eksport instancji, import instancji
  (ten sam dialog, wariant admin).
- `src/components/domain/TransferImportDialog.vue`: krok 1 upload ZIP →
  krok 2 raport dry-run (tabela: encja / nowe / kolizje; per kolizja
  select „Użyj istniejącego" (default) / „Utwórz kopię") → krok 3
  potwierdzenie → apply → podsumowanie (liczby utworzonych). Błąd wersji =
  czytelny komunikat PL, bez stacktrace.
- Pobieranie eksportu: fetch z credentials → blob → download (nazwa
  `pasnik-export-YYYY-MM-DD.zip`); spinner na przycisku (06_UIUX §3.4).

## Security

- Upload ZIP: limit rozmiaru **100 MB** (nowy limit — dopisać do
  07_SECURITY §6), sniffing sygnatury ZIP (`PK\x03\x04`), zawartość
  czytana przez `zipfile` z twardymi limitami: max plików, max rozmiar po
  dekompresji (ochrona przed zip-bombą), **żadnych ścieżek z `..`/absolutnych**
  (path traversal) — wpisy spoza `export.json` i `photos/` odrzucane.
- Zdjęcia z ZIP re-enkodowane przez Pillow jak każdy upload (07_SECURITY §6).
- `public_token` list NIE jest eksportowany (odtworzenie tokenu = nowe
  udostępnienie); `password_hash` NIGDY nie opuszcza bazy.
- Autoryzacja: USER eksportuje/importuje wyłącznie w swoim scope
  (`ScopedQuery`); `scope=instance` za `require_admin`. Import USERA nie
  może tworzyć encji w cudzym household.
- Audit: eksport i import (dry-run apply) logowane z liczbami, bez treści.

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3. Required
ładowane na starcie sesji (master prompt krok 1f); Review uruchamiane na
diffie przed commitem (krok 11).

- **Required**: SKILL-BE, SKILL-SEC
- **Recommended**: SKILL-FE
- **Review**: SKILL-REVIEW, SKILL-SECREV

## Tests

- **Unit:** serializacja/deserializacja encji (fabryki → JSON → obiekty);
  wykrywanie kolizji po normalized_name; mapowanie stary→nowy ID
  (referencje przepis→produkt, plan→przepis zachowane).
- **Integration (krytyczne — 08_TESTING §2):**
  1. **Round-trip**: pełny seed (rodzina, produkty, przepisy ze zdjęciem,
     plan, spiżarnia, listy, cele) → eksport → **czysta baza** (druga baza
     testowa/truncate) → import (dry-run: 0 kolizji) → apply → porównanie
     liczności i kluczowych pól per encja (bez ID);
  2. kolizje: import do bazy z istniejącą „Cebulą" → dry-run raportuje,
     `use_existing` nie duplikuje, `create_copy` tworzy kopię z sufiksem;
  3. wersja niezgodna (`schema_version: 999`) ⇒ 422 z czytelnym
     komunikatem, zero zapisów;
  4. apply z błędem w środku (np. uszkodzona referencja) ⇒ rollback
     całości, baza nietknięta;
  5. duży ZIP: eksport/import ~50 MB zdjęć (wygenerowane) przechodzi,
     zip-bomba/path traversal odrzucone.
- **API:** macierz uprawnień (USER nie zrobi `scope=instance` ⇒ 403;
  anonim 401); dry-run niczego nie zapisuje (asercja na licznikach tabel).
- **vitest:** `TransferImportDialog` — kroki, render raportu, wybory kolizji.
- **E2E:** Ustawienia → eksport (plik pobrany) → import tego pliku →
  raport kolizji → apply → toast z podsumowaniem.

## Acceptance Criteria

1. „Eksportuj moje dane" zwraca ZIP z `export.json` (schema_version 1)
   i zdjęciami; plik otwiera się standardowym narzędziem.
2. ADMIN eksportuje całą instancję (w tym users bez haseł, households).
3. Import pokazuje raport DRY-RUN (co powstanie / co koliduje po
   normalized_name) **zanim** cokolwiek zapisze — weryfikowalne testem.
4. Kolizję można rozstrzygnąć per pozycja: użyj istniejącego / utwórz kopię.
5. Apply działa w jednej transakcji — błąd = zero zmian w bazie.
6. Round-trip eksport → czysta baza → import odtwarza dane (test integracyjny).
7. Plik z niezgodną wersją = czytelny polski komunikat, nie 500.
8. Import/eksport zapisują wpis w audit; `task check` zielony.
9. Format udokumentowany w 04_API_DESIGN (sekcja dopisana przez batch).

## Out of Scope

- Import selektywny (tylko przepisy / tylko plan) — FUTURE, po R4.
- Eksport do formatów obcych (CSV, PDF) — nie planowany.
- Backup fizyczny bazy (pg_dump) — to B17/B18 (09_DEPLOYMENT); transfer
  to eksport LOGICZNY, nie zastępuje backupu.
- Migracje formatu między wersjami schematu (dopóki jest tylko v1).
- Import PDF diet — B15/B16 (osobny moduł `importer`).

## Expected files/modules

- `backend/app/modules/transfer/schemas.py` (N — format v1),
  `serializer.py` (N — eksport), `importer.py` (N — dry-run/apply),
  `service.py` (N), `router.py` (N)
- `backend/app/core/config.py` (M — limit ZIP), `main.py` (M — router)
- `backend/tests/unit/test_transfer_serializer.py`,
  `backend/tests/integration/test_transfer_roundtrip.py`,
  `backend/tests/integration/test_transfer_collisions.py`,
  `backend/tests/api/test_transfer_api.py` (N)
- `frontend/src/pages/UstawieniaPage.vue` (M), `AdminPage.vue` (M),
  `frontend/src/components/domain/TransferImportDialog.vue` (N),
  `frontend/src/api/queryKeys.ts` (M)
- `frontend/e2e/transfer.spec.ts` (N)
- `docs/architecture/04_API_DESIGN.md` (M — endpointy + sekcja „Format
  eksportu transfer v1"), `docs/architecture/07_SECURITY_DESIGN.md`
  (M — limit ZIP w §6)

## Implementation Notes

- **Kolejność importu = kolejność sekcji** (słowniki → produkty → przepisy
  → plany → listy) — inaczej FK padają; trzymać jedną stałą listę
  w `schemas.py`, używaną przez eksport i import (symetria).
- Eksport instancji zawiera `users` **bez** `password_hash` — po imporcie
  instancji ADMIN nadaje hasła ręcznie (`task create-admin` + reset).
  To świadome: plik eksportu nie może być materiałem do credential stuffing.
- Ratings przy imporcie USERA: oceny innych użytkowników z pliku mapować
  na importującego LUB pomijać — decyzja implementującego (uzasadnić;
  rekomendacja: pomijać cudze, zachować własne).
- Zdjęcia: brak pliku w ZIP przy ścieżce w JSON = warning w raporcie,
  encja importowana bez zdjęcia (nie blocker).
- Streaming eksportu: budować ZIP do pliku tymczasowego (scratch), potem
  `FileResponse` — nie trzymać w RAM (Odroid H2!).
- `shopping_generations.params` eksportować — odtwarzalność historii
  generacji (03_DATABASE §8).

## Cross-Batch Impact

- **Cztery ustalenia REVIEW R3 (2026-08-22), wiążące dla serializera:**
  1. **`shopping_lists.public_token` NIE MOŻE wyjść w eksporcie.** To żywy
     token dostępu bez logowania (ADR-010), a plik eksportu ląduje na dysku,
     w mailu i w kopii zapasowej — wyeksportowany token jest wyciekiem, nawet
     gdy lista jest nieciekawa. Eksport pomija `public_token` i `token_revoked`,
     import zakłada listę BEZ linku (właściciel udostępnia ją ponownie, co
     i tak generuje nowy token). To samo dotyczy `sessions` (nie eksportujemy).
  2. **`shopping_generations.params` to wersjonowane WEJŚCIE silnika**
     (`{"v": 1, …}`), nie wynik. Eksport przenosi je dosłownie albo pomija
     generacje w całości — przepisywanie kluczy „po swojemu" da po imporcie
     409 z `ShoppingParamsError` przy pierwszym otwarciu generacji. Czytać
     wyłącznie przez `shopping.engine.load_input`.
  3. **Kolejność importu wymuszają FK z RESTRICT**: kategorie → produkty
     kanoniczne → sklepy → warianty retail → spiżarnia → tury → listy.
     `pantry_items.retail_product_id` MA constraint FK (od migracji `0011`,
     w modelu domknięte w R3), więc pozycja spiżarni wskazująca wariant, który
     jeszcze nie wszedł, wysadzi transakcję.
  4. **Rejestr liczników referencji do rodziny** (`households.service.
     register_household_reference_finder`, R3): encje wniesione importem
     natychmiast blokują usunięcie rodziny i pokazują się ADMIN-owi w
     `details.used_in`. Jeśli import dołoży NOWĄ tabelę ze `household_id`,
     musi dołożyć też jej licznik.
- **Kolizje równoległości (B12 ∥ B13 ∥ B14)**: wspólne pliki —
  `frontend/package.json`/lockfile, `src/api/queryKeys.ts`,
  `backend/app/main.py` (rejestracja routera — **B13 JEDNAK dodał router**
  `build_stats_router()` w `app/main.py`, a B12 nie; przy merge unia obu
  wpisów), `docs/architecture/04_API_DESIGN.md` (B13 dopisał `/stats/daily`
  do mapy zasobów i sekcję „Statystyki dzienne" — konflikt dokumentacyjny,
  rozwiązywany unią). B14 NIE dotyka `vite.config.ts`/`src/lib/offline/*`
  (B12) ani `StatystykiPage`/charts (B13) ani modułów shopping/planning.
- **Round-trip celów a statystyki (ustalenie B13, 2026-08-22)**: `GET
  /stats/daily` czyta cele przez `nutrition/service.goals_of` i wybiera cel
  dnia po `valid_from`, więc po imporcie na CZYSTEJ bazie widok Statystyki
  musi działać bez żadnej zmiany w B13 — pod warunkiem, że eksport zachowuje
  **całą historię** `user_nutrition_goals` (nie tylko cel bieżący) razem
  z datami `valid_from`. Utrata historii nie wysypie API, tylko po cichu
  przepisze statusy dni sprzed zmiany celu — dlatego wart osobnej asercji
  w teście round-trip (cel z dwiema datami ⇒ dwa różne cele dzienne po
  imporcie).
- **B15/B16 (importer PDF)**: encje stagingu (`import_jobs`, `staged_*`)
  NIE wchodzą do eksportu v1 (staging to nie dane domenowe); przepisy
  `source=pdf_import` eksportują się normalnie, ale `import_job_id`
  w pliku = null (job nie jest przenoszony). **Dopisać do karty B15**:
  format transfer v1 istnieje — nowe encje domenowe wymagają rozszerzenia
  serializera (decyzja przy R4).
- **B17/B18**: procedura restore ćwiczy też import logiczny jako ścieżkę
  awaryjną — odnotować w karcie B18.

## Implementation checklist

- [x] Format v1: schematy + stała kolejność sekcji
- [x] Eksport U (scope user+household, słowniki referencjonowane) → ZIP
- [x] Eksport A (instancja, users bez haseł)
- [x] Import DRY-RUN: walidacja wersji, kolizje po normalized_name, raport
- [x] Import APPLY: transakcja, mapa ID, decyzje kolizji, zdjęcia, audit
- [x] Zabezpieczenia ZIP: limit, sniffing, zip-bomba, path traversal
- [x] UI: Ustawienia + Admin + `TransferImportDialog` (3 kroki)
- [x] Testy: unit, round-trip, kolizje, wersja, rollback, duży ZIP, API
- [x] E2E eksport→import
- [x] 04_API (sekcja formatu) + 07_SECURITY (limit) zaktualizowane
- [x] PROGRESS.md wpis + edycja karty B15 (Cross-Batch Impact)

## Verification checklist

- [x] `task check` zielony (unit+int+api+fe-test+typecheck+lint)
- [x] `task test-e2e` zielony
- [x] Brak migracji (`task db-heads` = `0013`, jedna głowa — bez zmian)
- [x] Ręcznie: eksport własnych danych → import tego pliku → raport kolizji →
      apply → kopia widoczna (wykonane przez spec E2E `transfer.spec.ts`,
      który klika dokładnie tę ścieżkę w UI)
- [x] Dry-run nie zostawia śladów w DB (asercja na licznikach tabel
      w `tests/api/test_transfer_api.py::test_dry_run_nie_zostawia_sladu_w_bazie`)
- [x] Acceptance Criteria 1–9 odhaczone z dowodem (patrz Completion notes)
- [x] Dokumentacja zaktualizowana; commit `batch(14): …`

## Completion notes

**Wykonane.** Moduł `backend/app/modules/transfer/` (schemas / serializer /
importer / service / router) dostarcza format **transfer v1**: ZIP z `export.json`
(nagłówek + 30 sekcji w stałej kolejności) i katalogiem `photos/`. Eksport
użytkownika bierze encje NALEŻĄCE do konta plus dokładnie te wiersze słowników
globalnych, do których się odwołują; eksport instancji (ADMIN) dokłada
`households`, `users` (bez hasła) i `audit_entries`. Import ma dwa kroki:
`POST /transfer/import` (walidacja archiwum + raport DRY-RUN, ZERO zapisów
w bazie) i `POST /transfer/import/{id}/apply` (jedna transakcja, mapa
stary→nowy ID, decyzje kolizji, zdjęcia przez `core/uploads.save_image`, wpis
`transfer.import` w dzienniku). UI: sekcja „Twoje dane" w `/ustawienia`, nowa
strona `/admin/dane` (instancja) i wspólny `TransferImportDialog` (3 kroki).
Migracji brak — head nadal `0013`.

**Dowody Acceptance Criteria.**

1. ZIP z `export.json` (`schema_version: 1`) i zdjęciami, czytelny standardowym
   `zipfile` — `tests/api/test_transfer_api.py::test_uzytkownik_eksportuje_swoje_dane`
   oraz round-trip (asercja na wpisach `photos/…` w `namelist()`).
2. Eksport instancji z kontami bez haseł —
   `test_admin_eksportuje_instancje_i_dostaje_zip` (asercja `"password_hash"`
   nieobecne w CAŁYM dokumencie).
3. DRY-RUN przed zapisem — `test_dry_run_nie_zostawia_sladu_w_bazie` (liczniki
   `canonical_products`, `recipes`, `audit_entries` bez zmian) + vitest
   `TransferImportDialog` (`apply` nie leci przed potwierdzeniem).
4. Decyzja per kolizja — `test_use_existing_nie_duplikuje_produktu`,
   `test_create_copy_tworzy_kopie_z_sufiksem`, vitest (obie ścieżki decyzji).
5. Jedna transakcja — `test_uszkodzona_referencja_cofa_caly_import`.
6. Round-trip na CZYSTEJ bazie —
   `tests/integration/test_transfer_roundtrip.py::test_round_trip_odtwarza_dane_na_czystej_bazie`
   (pełny przekrój domeny: katalog, retail ze zdjęciem, przepis ze zdjęciem,
   plan z rozkładem porcji, szablony + cykl, spiżarnia, lista zakupowa, DWA cele
   z różnymi `valid_from`).
7. Niezgodna wersja — 422 po polsku
   (`test_plik_z_inna_wersja_konczy_sie_422_i_zerem_zapisow` + wariant HTTP dla
   pliku, który nie jest ZIP-em).
8. Audit — `test_apply_tworzy_dane_i_wpis_w_dzienniku` (payload ma liczby
   i decyzje, NIE ma nazw przenoszonych encji).
9. Format udokumentowany — `04_API_DESIGN.md`, sekcja „Format eksportu
   transfer v1".

**Odstępstwa i decyzje wykonawcze (wszystkie w granicach karty).**

1. **`shopping_generations` eksportujemy tylko w stanie `final`/`discarded`.**
   Implementation Notes każą przenieść `params`, a ustalenie R3 dopuszcza
   „dosłownie albo wcale". Generacja `preview` jest jedynym stanem EDYTOWALNYM
   (`_editable_generation`), a jej `params` wskazują żywe pozycje planu instancji
   źródłowej — po imporcie jej finalizacja tworzyłaby pozycje list
   z identyfikatorami produktów z cudzej bazy. Historia (`final`/`discarded`)
   jest wyłącznie przeliczana do podglądu, więc przenosi się bezpiecznie.
   `params` idą DOSŁOWNIE, bez przepisywania kluczy. Konsekwencja:
   `shopping_lists.generation_id` bez pokrycia w pliku wychodzi jako `null`
   (kolumna jest NULL-owalna, treść listy zostaje kompletna).
2. **`ScopedQuery.owned_condition` / `select_owned` (nowe w `app/core/scope.py`).**
   „Eksportuj MOJE dane" to przynależność, nie widoczność — `visible_condition`
   zwraca ADMIN-owi `true()` (D16), więc administrator klikający ten przycisk
   dostałby plik z encjami wszystkich rodzin w instancji. Dokładnie tę granicę
   ma już spiżarnia (`HouseholdScopedQuery.household_condition`), więc
   `ScopedQuery` dostał bliźniaczą metodę zamiast ręcznego filtra w serwisie
   (CLAUDE.md §4). `visible_condition` deleguje teraz do niej, więc zachowanie
   dla nie-ADMIN-a jest bit w bit to samo.
3. **Oceny przepisów: eksportujemy WYŁĄCZNIE własne** (rekomendacja karty).
   Cudza ocena jest opinią konkretnej osoby; po imporcie nie ma komu jej
   przypisać, a przepisanie jej na importującego byłoby sfałszowaniem danych.
4. **Scalanie `plan_days` przy powtórnym imporcie własnego pliku.** `plan_days`
   ma `UNIQUE(owner_user_id, day)`, więc import własnego eksportu na to samo
   konto (pierwsza rzecz, którą robi użytkownik: „czy mój backup się wczytuje?")
   trafiał w konflikt na pierwszym dniu. Wiersz **scala się** z istniejącym,
   a posiłki dopisują się do niego — dokładnie tak, jak instancjacja szablonu
   (`PlanningService.append_day_payload`, B07). Analogicznie wiersze niosące FAKT
   o rodzicu (`product_unit_weights`, `product_nutrient_values`, `recipe_ratings`,
   `user_nutrition_goals`) wchodzą `ON CONFLICT DO NOTHING`. Pozostałe konflikty
   UNIQUE dają **409** z instrukcją, nigdy 500.
5. **Martwa referencja w payloadzie szablonu USUWA pozycję** (z ostrzeżeniem),
   zamiast zostawić surowe id. Zostawienie go trafiłoby w nowej bazie w losowy
   przepis o tym numerze — cicha podmiana treści jest gorsza niż brak pozycji.
   Cykl gubi martwy wpis `template_ids`, a cykl bez żadnego żywego szablonu jest
   pomijany (R2: cykl z jednym martwym id jest niesprawny CAŁY).
6. **`audit_entries.entity_id` NIE jest remapowane** przy imporcie instancji —
   to historyczny ślad po encji, której w nowej bazie może już nie być;
   remapowanie kłamałoby o tym, czego wpis dotyczył.
7. **`frontend/src/api/queryKeys.ts` NIE został zmieniony** (karta wymieniała go
   w Expected files). Transfer nie ma ani jednego zapytania odczytowego: raport
   i podsumowanie to wyniki MUTACJI, a paczka po `apply` przestaje istnieć, więc
   klucz zapytania nie miałby czego identyfikować. Po imporcie dialog woła
   `invalidateQueries()` bez klucza — import dotyka niemal każdej encji, a lista
   kluczy „po jednym" byłaby listą do zapomnienia przy następnym batchu.
8. **Pliki poza listą Expected files**: `frontend/src/lib/download.ts` (zapis
   bloba na dysk — wydzielone, żeby strony dały się testować bez DOM-u i żeby
   `revokeObjectURL` było w jednym miejscu) oraz
   `frontend/src/pages/admin/AdminDanePage.vue` razem z trasą `admin/dane`
   i pozycją nawigacji „Dane". Karta mówi „AdminPage", a takiej pojedynczej
   strony w repo nie ma — 05_FRONTEND §3 zapowiada `/admin/*` z import/eksportem,
   a `navigation.ts` wprost dopuszcza dokładanie podsekcji administracji.
   Zaktualizowana została asercja `src/router.spec.ts` (nowa trasa w komplecie
   sekcji) — to zmiana STANU OCZEKIWANEGO, nie osłabienie testu.
9. **Eksport jest POST-em**, mimo że nie zmienia danych domenowych: buduje plik,
   zostawia wpis w dzienniku i nie ma prawa dać się wywołać z `<img src>`.
   Odpowiedź to `FileResponse` + `BackgroundTask` kasujący plik po wysyłce.
10. **Konwencja nazw w E2E**: encje specu transferu nazywają się
    `E2E transfer …` (prefiks NA POCZĄTKU). Pierwsza wersja specu użyła
    `Zupa E2E transfer`, czego `cleanupE2eData` (`byPrefix`) nie sprząta —
    i pozostałość natychmiast wywróciła `week-template-cycle.spec.ts`
    (trigramowa szukajka znalazła cudzy przepis, więc inline create zniknął —
    dokładnie dług U15 z review R2). To jest wiążące dla kolejnych specow.

**Ustalenia review na diffie (SKILL-REVIEW + SKILL-SECREV) — cztery naprawione,
jedno odnotowane.**

1. **`/code-review` + `/security-review` (HIGH): paczki transferu leżały
   w drzewie serwowanym przez `GET /uploads/*`.** Ten endpoint sprawdza WYŁĄCZNIE
   sesję (nie właściciela pliku), więc dowolny zalogowany użytkownik, który
   poznałby `import_id`, pobrałby `uploads/transfer/<id>.zip` — czyli KOMPLET
   danych cudzego konta. Naprawione: `app/core/uploads.py` ma teraz
   `PRIVATE_SUBDIRS = ("transfer",)`, a `resolve_upload_path` odrzuca te ścieżki
   identycznym 404 jak plik nieistniejący. Zdjęcia importu (`transfer-import/`)
   pozostają serwowane. Test: `test_katalog_paczek_transferu_nie_jest_serwowany`.
2. **`/code-review` (HIGH): eksport tworzył plik, który jego własny import
   odrzucał.** Pozycja planu może wskazywać przepis, którego `select_owned` już
   nie zwraca (członek rodziny przestawił swój przepis na `private` PO tym, jak
   trafił do cudzego planu — FK RESTRICT trzyma pozycję przy życiu). Taka
   referencja nie miała pokrycia w sekcji `recipes`, więc import padał 422,
   a wyeksportowanie cudzego prywatnego przepisu byłoby wyciekiem. Naprawione:
   pozycja wypada z pliku razem ze swoim rozkładem porcji. Test:
   `test_pozycja_planu_z_niewidocznym_przepisem_nie_psuje_pliku`.
3. **`/code-review` (MED): argon2 liczony na pętli zdarzeń.** `hash_password` dla
   kont z importu instancji szedł synchronicznie w `async def` — 60 kont to ~3 s
   zablokowanego procesu. Naprawione: `await run_in_threadpool(hash_password, …)`,
   jak w `accounts/service.py` (ADR-015).
4. **`/code-review` (MED): `downloadExport` omijał handler 401 i zegar serwera.**
   Eksport pobiera ZIP-a własnym `fetch` (bo `apiFetch` czyta JSON), więc wygasła
   sesja nie odsyłała na `/login`. Naprawione: `client.ts` eksportuje
   `observeResponse(response)` (zegar serwera + 401) i wołają je OBIE ścieżki.
5. **`/code-review` (LOW): zdjęcie obecne w archiwum, ale nieczytelne, ginęło bez
   śladu** — dry-run ostrzega tylko o zdjęciach BRAKUJĄCYCH. Naprawione: `apply`
   dokłada ostrzeżenie „Nie udało się wczytać zdjęcia …".

`/security-review` poza pkt 1 nie zgłosił ustaleń: nazwy kolumn przy zapisie
pochodzą wyłącznie ze stałych `SECTIONS` (plik nie wstrzyknie kolumny),
`sections_for(document.scope)` odsiewa sekcje `users`/`households`/`audit_entries`
z pliku użytkownika (brak eskalacji), a `IdMap` w imporcie użytkownika ma puste
mapy kont i rodzin, więc każda referencja właścicielska spada na konto
importującego (brak zapisu w cudzej rodzinie). Uwaga procesowa: skill
`/security-review` każe rozdzielić analizę na podzadania agentowe — konfiguracja
tej sesji zabrania używania narzędzia Agent bez prośby właściciela, więc analiza
została wykonana inline, w pełnym zakresie diffu.

**Follow-upy (poza zakresem tego batcha).**

- **U18 — import selektywny** („tylko przepisy", „tylko plan") jest w Out of
  Scope karty; format i mapa ID są na niego gotowe (wystarczy filtr sekcji),
  ale decyzja o UI należy do R4.
- **U19 — brak komendy CLI do eksportu/importu.** Restore awaryjny wymaga dziś
  działającej aplikacji i sesji ADMIN-a. B18 ćwiczy restore z `pg_dump`, więc
  to nie jest bloker, ale komenda offline („odtwórz z pliku na świeżej
  instalacji") byłaby tańsza niż logowanie się do na wpół wstałej instancji.
  Kandydat na B17/B18.
- **U20 — scratch importu sprząta się leniwie** (przy każdym dry-runie kasujemy
  paczki starsze niż 24 h). Instancja, na której nikt nie importuje, trzyma
  nieużytą paczkę bezterminowo. Job okresowy to temat B18 (tam jest już
  sprzątanie sesji).
- **U21 — `analyze` liczy `to_create` optymistycznie** dla sekcji wstawianych
  `ON CONFLICT DO NOTHING` (np. oceny przepisów): raport może pokazać 1, a
  podsumowanie policzy ten wiersz jako „użyto istniejącego". Różnica nie
  wprowadza w błąd co do skutków, ale dokładne liczenie wymagałoby odpytania
  bazy per wiersz w DRY-RUNIE.

**Pytania do właściciela: brak.** Batch nie miał bramki decyzyjnej i żadne
z powyższych odstępstw nie zmienia decyzji zapisanej w `02_DECISIONS.md`.
