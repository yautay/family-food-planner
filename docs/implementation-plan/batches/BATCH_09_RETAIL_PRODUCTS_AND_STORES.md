# BATCH_09 — RETAIL_PRODUCTS_AND_STORES

Klasa: SHOP · Zależności: BATCH_04 + R2 (bez bramek decyzyjnych) · Rozmiar: M

Równoległość: batch MOŻE iść równolegle z BATCH_08 w **osobnym git worktree**
(00_MASTER_PLAN §5). Przed startem sprawdzić „Pliki wspólne z BATCH_08"
(Context) i ustalić kolejność merge'ów; batch mergowany jako drugi wykonuje
rekoncyliację (down_revision, regeneracja typów, konflikty w main.py).

## Goal

Po tym batchu istnieją produkty sklepowe (retail) powiązane obowiązkowo
z produktem kanonicznym (marka, sklep, wielkość opakowania, zdjęcie) oraz
sklepy z profilami kolejności kategorii (kolejność fizycznego przejścia po
sklepie). Użytkownik zarządza produktami sklepowymi z karty produktu
kanonicznego, a sklepami — w Ustawieniach (drag&drop kolejności kategorii
z fallbackiem strzałek). Powstaje komponent inline create produktu
sklepowego, gotowy do użycia w preview zakupów (B10/B11).

## Context

Co już istnieje (stan po R2):
- `backend/app/modules/catalog/` — `canonical_products`, `product_categories`
  (z `perishability` i `position`), jednostki, wyszukiwarka trigram,
  wzorzec blokady usuwania ADR-012 (409 + `details.used_in`).

  Konkrety z B04, których ten batch NIE powtarza: moduł `catalog` już istnieje
  (models/schemas/service/router) — `retail_products` i `stores` DOKŁADASZ do
  niego, a nie tworzysz drugiego modułu. `retail_products.canonical_product_id`
  ma FK RESTRICT, więc `RetailProduct` musi zarejestrować licznik referencji:
  `catalog.service.register_product_reference_finder(finder)` z
  `finder(session, product_id) -> Sequence[UsedInRef]` (typy w
  `app/core/deletion.py`) — inaczej 409 przy usuwaniu produktu kanonicznego
  wyjdzie bez czytelnej listy użyć. Wielkości opakowań i ilości to `Decimal`
  w bazie i **stringi dziesiętne** w JSON (`DecimalString` z `app/core/schemas.py`).
- Infrastruktura uploadu zdjęć z BATCH_05 — do PONOWNEGO UŻYCIA, nie
  kopiowania. Konkretne API (`backend/app/core/uploads.py`):
  `save_image(data: bytes, *, uploads_root: Path, subdir: str) -> SavedImage
  (path, thumbnail_path)` — limit 10 MB (413), sniffing Pillow (422),
  re-encode do JPEG (strip EXIF), miniatura `<nazwa>_thumb.jpg` ≤512 px;
  `delete_image(path, *, uploads_root)` (usuwa też miniaturę, idempotentne);
  `thumbnail_path_for(path)`. Funkcje są synchroniczne — serwis woła je przez
  `run_in_threadpool` (wzór: `recipes/service.py::set_photo`). Katalog =
  `Settings.uploads_dir` (env `UPLOADS_DIR`); dla retail użyj własnego
  `subdir` (np. `"retail"`). Serwowanie już istnieje: `GET /uploads/{path}`
  (poza `/api/v1`, wymaga sesji — `app/main.py::build_uploads_router`);
  URL w odpowiedzi buduje się jak w `recipes/router.py::_photo_urls`.
- `ProductPicker` + wzorzec create-in-context (05_FRONTEND §4);
  `UstawieniaPage` (cele, profile rodziny, konto).

Wymagane lektury przed startem:
- `docs/architecture/02_DOMAIN_MODEL.md` §4.4 (RetailProduct), §4.5
  (Store/StoreProfile), §4.6 (usuwanie/archiwizacja), §3.1 pkt 3–4
  (retail i sklepy globalne, edytowalne przez USER)
- `docs/architecture/03_DATABASE_DESIGN.md` §1 (migracje), §3 (schemat
  catalog — WIĄŻĄCY: `stores`, `store_category_order`, `retail_products`)
- `docs/architecture/04_API_DESIGN.md` §1–2 (`/retail-products`, `/stores`,
  `/stores/{id}/category-order`)
- `docs/architecture/06_UIUX_PRINCIPLES.md` §2 (drag&drop tylko z alternatywą
  przyciskową), §3 (wzorce obowiązkowe)
- `docs/architecture/07_SECURITY_DESIGN.md` §6 (uploady)
- `docs/adr/ADR-012-usuwanie-archiwizacja.md`

Pliki wspólne z BATCH_08 (kolizje!):
- `backend/app/main.py`, `backend/migrations/versions/` (łańcuch
  `down_revision` — po merge'u `alembic heads` = JEDNA głowa),
- `frontend/src/api/queryKeys.ts`, `frontend/src/api/generated.ts`,
- `frontend/src/router/index.ts` (B09 nie dodaje nowej strony top-level,
  ale rozszerza `/produkty/:id/edytuj` i `/ustawienia`),
- `backend/tests/factories.py`.
Uwaga: B08 tworzy `pantry_items.retail_product_id` — jeśli B08 zmergował
się pierwszy BEZ constraintu FK (patrz karta B08, nota 1), ten batch
w migracji dodaje constraint `FK RESTRICT` na tę kolumnę.

## Stages

1. **DB**: migracja `stores`, `store_category_order`, `retail_products`
   (+ ewentualny odroczony FK z B08); up/down/up na kopii bazy.
2. **Backend — sklepy**: CRUD `/stores` + `/stores/{id}/category-order`
   (GET/PUT pełna podmiana); blokada usuwania; testy.
3. **Backend — retail**: CRUD `/retail-products` + upload zdjęcia
   (infrastruktura B05); walidacje opakowania; testy.
4. **Frontend — sklepy**: sekcja „Sklepy" w Ustawieniach; edytor kolejności
   kategorii (drag&drop + strzałki); `StorePicker` z inline create.
5. **Frontend — retail**: sekcja „Produkty sklepowe" na karcie produktu
   kanonicznego; `RetailProductCreateDrawer` (komponent wielokrotnego
   użytku — kontrakt dla B10/B11).
6. **Testy + docs**: komplet testów, `task check`, PROGRESS.md,
   propagacja Cross-Batch Impact.

## Database / migrations

Dokładnie schemat z 03_DATABASE §3 (plus `created_at`/`updated_at`):

```sql
stores (id, name UNIQUE, color TEXT NULL, is_archived BOOL DEFAULT false)
store_category_order (store_id FK CASCADE, category_id FK CASCADE,
       position INT, PRIMARY KEY(store_id, category_id))
retail_products (id, canonical_product_id FK RESTRICT, name, brand NULL,
       store_id FK NULL SET NULL, package_amount NUMERIC(8,2),
       package_unit ENUM(g,ml,piece), pieces_per_package INT NULL,
       photo_path TEXT NULL, is_archived BOOL)
```

- Indeks: `retail_products(canonical_product_id)` (03 §3).
- Numer migracji = pierwszy wolny; `down_revision` = `alembic heads`.
- Jeśli kolumna `pantry_items.retail_product_id` istnieje bez FK
  (rekoncyliacja z B08) — dodać constraint w tej migracji.

## Backend

Rozszerzenie modułu `catalog` (retail i sklepy to część słownika instancji
— 02 §1) albo podmoduły `catalog/retail.py` / `catalog/stores.py`; bez
nowego modułu top-level.

| Ścieżka | Metoda | Rola | Opis |
|---|---|---|---|
| `/api/v1/stores` | GET, POST | U | lista/utworzenie sklepu (globalny słownik; inline create dostępny dla USER) |
| `/api/v1/stores/{id}` | PATCH, DELETE | U | edycja; DELETE z blokadą referencyjną (409 + `used_in`) |
| `/api/v1/stores/{id}/category-order` | GET | U | uporządkowana lista kategorii profilu |
| `/api/v1/stores/{id}/category-order` | PUT | U | pełna podmiana kolejności (lista `category_id` w kolejności) |
| `/api/v1/retail-products` | GET, POST | U | lista (`?canonical_product_id=`, `?store_id=`, `?q=`, `?include_archived=`), utworzenie |
| `/api/v1/retail-products/{id}` | PATCH, DELETE | U | edycja / usunięcie z blokadą 409; alternatywa `is_archived` |
| `/api/v1/retail-products/{id}/photo` | PUT, DELETE | U | upload/usunięcie zdjęcia (infrastruktura B05, limity 07 §6) |

Walidacje serwisowe (422, komunikaty PL):
- `canonical_product_id` WYMAGANE (02 §4.4) — retail bez kanonicznego nie istnieje;
- `package_amount > 0`; `package_unit` zgodny z `measure_kind` produktu
  kanonicznego (`g`↔mass, `ml`↔volume, `piece`↔piece);
- `pieces_per_package ≥ 1` gdy podane (opakowania wielosztukowe, np. jajka 10 szt.);
- `position` w profilu sklepu: spójna permutacja bez duplikatów (PUT waliduje całość).

Usuwanie (ADR-012):
- retail product użyty gdziekolwiek (docelowo: `pantry_items`,
  `shopping_list_items`) → 409 z listą użyć; alternatywa `is_archived`
  (znika z pickerów, zostaje w danych historycznych);
- store: fizyczne usunięcie tylko gdy nieużywany — w tym batchu sprawdzenie
  referencji `retail_products.store_id`; tabela `shopping_lists` powstaje
  w B10 i rozszerzenie sprawdzenia o profile list wykona B11 (patrz
  Cross-Batch Impact). Profil kolejności (`store_category_order`) kasuje
  się kaskadą — nie blokuje.

## Frontend

- **Ustawienia → „Sklepy"** (`frontend/src/pages/ustawienia/` — nowa sekcja/
  zakładka): lista sklepów (nazwa, kolor), dodaj/edytuj/usuń (dialog
  konsekwencji, 409 → „Używane w: …"); edytor profilu sklepu:
  uporządkowana lista kategorii zakupowych z **drag&drop** + obowiązkowym
  fallbackiem strzałek góra/dół (06 §2 — mobile/dostępność); zapis = PUT
  całej kolejności.
- **Karta produktu kanonicznego** (`/produkty/:id/edytuj`, widok 8):
  nowa sekcja „Produkty sklepowe" — lista wariantów retail (nazwa, marka,
  sklep, opakowanie sformatowane `formatAmount`, miniatura zdjęcia) +
  „+ Dodaj produkt sklepowy" otwierający drawer.
- **`RetailProductCreateDrawer.vue`** (`components/domain/`) — komponent
  wielokrotnego użytku (KONTRAKT dla B10/B11): props
  `{ canonicalProductId, prefillName? }`, emit `created(retailProduct)`;
  minimalny formularz: nazwa, marka, sklep (`StorePicker` z inline create),
  `package_amount` + jednostka (zawężona do `measure_kind`),
  `pieces_per_package`, zdjęcie (opcjonalne). Po zapisie auto-wybór
  i powrót do przerwanego flow (06 §3 pkt 1).
- **`StorePicker.vue`** — picker sklepu z `+ Dodaj sklep "…"` (wzorzec
  create-in-context obowiązkowy dla sklepów — 05 §4).
- Composables: `useStores`, `useStoreCategoryOrder`, `useRetailProducts`
  (TanStack Query + mutacje z invalidate); klucze w `queryKeys.ts`.

## Security

- Sesja + CSRF na mutacjach; zasoby globalne — brak scope household,
  ale wymagana sesja (401 dla anonima); edycja dozwolona dla USER
  (02 §3.1 pkt 3–4), bez operacji admin-only.
- Upload zdjęcia: limity ≤10 MB, MIME sniffing po treści, re-encode Pillow
  (strip EXIF), losowa nazwa na bind mount, serwowanie wyłącznie przez
  endpoint z autoryzacją (07 §6) — użyć istniejącej infrastruktury B05,
  nie pisać własnej ścieżki zapisu.
- Blokada usuwania (ADR-012) chroni integralność danych historycznych.

## Skills

Mapa ID → skill: `docs/implementation-plan/03_AI_SKILLS.md` §3. Required
ładowane na starcie sesji (master prompt krok 1f); Review uruchamiane na
diffie przed commitem (krok 11).

- **Required**: SKILL-BE, SKILL-FE
- **Review**: SKILL-REVIEW

## Tests

- **Integration**:
  - retail wymaga kanonicznego (brak/nieistniejący `canonical_product_id`
    → błąd); FK RESTRICT nie pozwala usunąć kanonicznego użytego w retail;
  - kolejność kategorii per sklep: PUT podmienia całość, kolejność trwała,
    duplikat `category_id` → 422; dwa sklepy mają niezależne profile;
  - usunięcie sklepu z profilem → profil znika kaskadą; sklep użyty
    w `retail_products` → 409 z `used_in`;
  - archiwizacja retail: znika z listy domyślnej, widoczny
    z `include_archived`;
  - migracja up/down/up.
- **API**:
  - macierz uprawnień: anonim 401; USER tworzy/edytuje retail i sklepy (200);
  - walidacje opakowania (amount ≤ 0, jednostka niezgodna z `measure_kind`,
    `pieces_per_package = 0`) → 422;
  - upload zdjęcia: poprawny obraz 200, nie-obraz → 422, >10 MB → 413/422;
  - DELETE retail użytego (fixture z pozycją spiżarni, jeśli B08 zmergowany)
    → 409.
- **Frontend** (vitest): edytor kolejności — strzałki przesuwają pozycję
  i emitują nową kolejność; `RetailProductCreateDrawer` emituje `created`
  po zapisie; `StorePicker` pokazuje `+ Dodaj sklep`.
- **E2E**: z karty produktu kanonicznego dodanie produktu sklepowego
  (z inline create sklepu) → wariant widoczny na karcie; zmiana kolejności
  kategorii w profilu sklepu strzałkami → kolejność zapisana po odświeżeniu.

## Acceptance Criteria

1. USER tworzy produkt sklepowy wyłącznie powiązany z produktem kanonicznym;
   próba bez powiązania kończy się 422.
2. Produkt sklepowy ma markę, opcjonalny sklep, wielkość opakowania
   (ilość + jednostka + opcjonalnie sztuki w opakowaniu) i opcjonalne
   zdjęcie (upload przez infrastrukturę B05).
3. Sklepy można tworzyć (także inline z pickera), edytować; usunięcie
   sklepu użytego przez produkty retail zwraca 409 z listą użyć.
4. Profil sklepu = trwała kolejność kategorii; edycja drag&drop ORAZ
   strzałkami; dwa sklepy mają niezależne kolejności.
5. Karta produktu kanonicznego pokazuje sekcję produktów sklepowych
   z możliwością dodania w drawerze bez opuszczania karty.
6. `RetailProductCreateDrawer` działa jako samodzielny komponent
   z udokumentowanym kontraktem props/emit (gotowy dla B10/B11).
7. `alembic heads` = jedna głowa (także po merge'u z B08); `task check` zielony.

## Out of Scope

- Użycie retail w silniku zakupowym (dobór opakowań, resztki) → BATCH_10.
- Inline create retail z preview zakupów (UŻYCIE komponentu) → BATCH_10/11.
- Sortowanie listy zakupowej wg profilu sklepu → BATCH_11.
- Rozszerzenie blokady usuwania sklepu o `shopping_lists` → BATCH_11.
- Wybór retail w formularzu spiżarni → B10/R3 (patrz karta B08).
- Automatyczne zamienniki produktów (02 §9.3 — poza zakresem programu).
- Ceny produktów sklepowych (brak w modelu domenowym).

## Expected files/modules

Nowe:
- `backend/app/modules/catalog/{retail_models.py lub models.py rozszerzone}`,
  `retail_schemas/service/router` + `stores_service/router` (wg konwencji
  modułu catalog z B04 — decyzja implementującego, patrz Implementation Notes)
- `backend/migrations/versions/<pierwszy_wolny>_retail_and_stores.py`
- `backend/tests/integration/test_retail_products.py`, `test_stores.py`
- `backend/tests/api/test_retail_api.py`, `test_stores_api.py`
- `frontend/src/components/domain/{RetailProductCreateDrawer.vue,StorePicker.vue,StoreCategoryOrderEditor.vue}`
- `frontend/src/pages/ustawienia/SklepySection.vue` (lub zakładka)
- `frontend/src/composables/{useStores.ts,useRetailProducts.ts}`
- `frontend/e2e/retail-stores.spec.ts`

Zmieniane (⚠ = wspólne z B08):
- ⚠ `backend/app/main.py`, ⚠ `backend/tests/factories.py`
- ⚠ `frontend/src/api/queryKeys.ts`, ⚠ `frontend/src/api/generated.ts` (regen)
- `frontend/src/pages/produkty/ProduktEdytujPage.vue` (sekcja retail)
- `frontend/src/pages/ustawienia/UstawieniaPage.vue` (nowa sekcja)

## Implementation Notes

1. Struktura plików w module `catalog`: dostosować się do konwencji
   zastanej po B04 (jeden `models.py` vs pliki per obszar) — uzasadnić
   wybór w Completion notes; NIE tworzyć modułu top-level `retail`.
2. ROZSTRZYGNIĘTE na etapie planu (2026-08-16): `stores` MA kolumnę
   `is_archived` (03 §3 zaktualizowane) — obowiązuje standardowy wzorzec
   ADR-012: blokada 409 przy referencjach + archiwizacja jako alternatywa.
3. Drag&drop: wybrać lekkie rozwiązanie (native HTML5 DnD albo mała
   biblioteka) — uzasadnić; strzałki są obowiązkowe niezależnie od DnD.
4. PUT `category-order`: przyjąć pełną listę `category_id`; kategorie
   spoza listy = poza profilem (silnik/lista w B11 umieści je na końcu).
5. Kolejność merge'ów z B08: patrz reguła w Context; po merge'u
   OBOWIĄZKOWO `alembic heads` i `task check`.

## Cross-Batch Impact

- **BATCH_10**: silnik doboru opakowań czyta warianty retail per produkt
  kanoniczny (`package_amount`, `package_unit`, `pieces_per_package`);
  preview używa `RetailProductCreateDrawer` — kontrakt props/emit
  udokumentować w Completion notes i zaktualizować kartę B10, jeśli różny.
- **BATCH_11**: sortowanie listy wg `store_category_order`; rozszerzenie
  blokady usuwania sklepu o referencje `shopping_lists.store_id` —
  dopisane w karcie B11 (Backend).
- **BATCH_08/R3**: ewentualna migracja rekoncyliacyjna FK
  `pantry_items.retail_product_id` (patrz Database) — odnotować w PROGRESS.

## Implementation checklist

- [ ] Migracja `stores` + `store_category_order` + `retail_products`
      (+ odroczony FK z B08, jeśli dotyczy)
- [ ] Serwisy + walidacje (kanoniczny wymagany, zgodność jednostek, permutacja profilu)
- [ ] Routery `/stores`, `/stores/{id}/category-order`, `/retail-products` (+photo)
- [ ] Blokada usuwania 409 + archiwizacja retail (ADR-012)
- [ ] Testy integration + API
- [ ] Sekcja „Sklepy" w Ustawieniach + edytor kolejności (DnD + strzałki)
- [ ] Sekcja retail na karcie produktu + `RetailProductCreateDrawer` + `StorePicker`
- [ ] Testy frontend + E2E
- [ ] PROGRESS.md + aktualizacja kart B10/B11 (kontrakt drawera)

## Verification checklist

- [ ] `task check` zielony (unit+int+api+fe-test+typecheck+lint)
- [ ] `alembic upgrade head` + `downgrade -1` + `upgrade head`;
      `alembic heads` = 1 głowa (także po merge'u z B08)
- [ ] Acceptance Criteria 1–7 sprawdzone
- [ ] Upload zdjęcia przechodzi przez infrastrukturę B05 (bez nowej ścieżki zapisu)
- [ ] Dokumentacja i karty przyszłych batchy zaktualizowane
- [ ] Commit `batch(09): …`, `git status` czysty w zakresie batcha

## Completion notes

(wypełnia agent wykonujący)
