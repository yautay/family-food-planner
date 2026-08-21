# 02 — Rejestr decyzji właściciela

Decyzje PRODUKTOWE/właścicielskie (techniczne trwałe → `docs/adr/`).
Status: OPEN dopóki właściciel nie zatwierdzi. Decyzja-bramka blokuje
wskazany batch — nie wolno go zlecić przed rozstrzygnięciem.

## Zatwierdzone

| # | Decyzja | Wynik | Data |
|---|---|---|---|
| D1 | Repo i nazwa | **ZATWIERDZONE**: nowe repo `C:\dev\family-food-planner`; stare repo GitHub = archiwum i źródło referencji | 2026-08-16 |
| D2 | Dane startowe | **ZATWIERDZONE: czysty start** — bez seedu z prototypu; treść wchodzi ręcznie + przez PDF importer. `data/reference/prototype.db` służy WYŁĄCZNIE jako referencja walidacyjna importera (84 przepisy / 592 składniki / 181 produktów). Konsekwencja: B15/B16 nie później niż po R3 | 2026-08-16 |
| D3 | Język UI | **ZATWIERDZONE**: wyłącznie polski, bez warstwy i18n (ADR-007) | 2026-08-16 |
| D4 | Zakres wartości odżywczych | **ZATWIERDZONE**: kcal, białko, tłuszcz, węglowodany, błonnik, cukry + **indeks glikemiczny produktu** (ŁG wyliczany per porcja/posiłek/dzień). Mikroelementy później przez rejestr nutrients (ADR-004) bez migracji łamiącej | 2026-08-16 |
| D12 | Sposób wdrożenia na Odroida | **ZATWIERDZONE: bez Ansistrano** — zostaje procedura z 09_DEPLOYMENT §4 (`git pull` → build obrazów → backup → `alembic upgrade head` → `compose up -d`), rollback przez tagowane obrazy. B18 implementuje ją jako skrypt, nie wprowadza dodatkowego narzędzia wdrożeniowego | 2026-08-16 |
| D5 | AI w imporcie PDF | **ZATWIERDZONE**: wolno wysyłać treść PDF-ów do Claude API („żaden sekret"); klucz server-side; AI tylko proponuje (ADR-011) | 2026-08-16 |
| D13 | Kto usuwa produkt kanoniczny (słownik globalny) — B04 | **ZATWIERDZONE: wyłącznie ADMIN**, i tylko gdy produkt nieużywany (409 `used_in` w przeciwnym razie). USER, także twórca produktu, dostaje 403 — może wyłącznie archiwizować. Uzasadnienie: katalog jest globalny (02 §3.1 pkt 3), więc usunięcie przez jednego użytkownika uderza we wszystkie rodziny; ścieżką odwracalną dla USERa jest `is_archived` (ADR-012). Konsument: macierz uprawnień w testach API B04 | 2026-08-16 |
| D14 | Nakładanie kategorii ZBOŻOWE vs PIECZYWO / MAKARONY-RYŻ-KASZE — B04 | **ZATWIERDZONE: dwie osobne kategorie — PIECZYWO i MAKARONY-RYŻ-KASZE; „ZBOŻOWE" nie wchodzi do słownika.** Uzasadnienie: kategorie niosą `perishability`, a te dwie mają różne wartości (pieczywo = fresh, makarony/ryż/kasze = durable) — wspólna kategoria „ZBOŻOWE" nie mogłaby unieść obu i zepsułaby tury silnika zakupowego (B10) | 2026-08-16 |

## Otwarte

| # | Decyzja | Rekomendacja | Blokuje |
|---|---|---|---|
| D6 | Backup off-device: dokąd kopiować backupy poza Odroida (NAS? chmura? który provider?) | rclone do dowolnego zdalnego storage (konfig w env); minimum: cotygodniowa kopia ręczna na inny dysk | **B18 (bramka konfiguracji)** |
| D7 | Domena/subdomena aplikacji + szczegóły istniejącego reverse proxy (nginx? porty? jak dokładany jest vhost) | subdomena dedykowana, proxy → 127.0.0.1:8080 | **B18 (bramka)** |
| D8 | 2FA logowania | **FUTURE** — nie w MVP; hasła argon2id + rate limit wystarczą na start; wrócić po wdrożeniu | — |
| D9 | Progi statusów żywieniowych (za mało/OK/za dużo) | 90–110% celu, konfigurowalne per użytkownik w ustawieniach; batch B06 może przyjąć bez osobnego zatwierdzenia | — |
| D10 | Retencja starych list zakupowych i planów | nic nie usuwamy automatycznie (historia = wartość); ręczne bulk delete dla właściciela; rewizja przy R4 | — |
| D11 | IG produktów — źródło danych | uzupełnianie ręczne przy produktach, gdzie ŁG ma znaczenie (tabele międzynarodowe IG jako źródło do przepisania ręcznego; bez bulk importu — prawa autorskie tabel); UI toleruje braki (flaga „niepełne dane") | — |
| D15 | Kto może zmienić `measure_kind` produktu kanonicznego i czy zmiana unieważnia weryfikację (ustalenie R1) | **Zbijać `verification_status` do UNVERIFIED** (+ wpis audytu `product.update`) przy każdej zmianie `measure_kind` na produkcie, który ma jakiekolwiek wartości odżywcze; ewentualnie dodatkowo zastrzec samą zmianę dla ADMIN-a. Powód: `measure_kind` decyduje, czy te same liczby znaczą „na 100 g" czy „na 100 ml" (ADR-004), więc dziś USER może cicho przestawić podstawę zweryfikowanych danych. **Stan po B05: rekomendacja WDROŻONA** (`catalog/service.py::update_product` zbija do UNVERIFIED i czyści `verified_at`; audyt `product.update` niesie `verification_status` w before/after; testy `tests/integration/recipes/test_recipes_service.py::test_d15_*`). Zastrzeżenie zmiany `measure_kind` dla ADMIN-a — NIE wdrożone, czeka na głos właściciela. **Stan po R2 (2026-08-21): review potwierdza wdrożenie i podtrzymuje rekomendację; decyzji właściciela NIE zastępuje — eskalacja w werdykcie.** Nowa informacja z audytu: zmiana `measure_kind` nie przelicza ilości JUŻ ZAPISANYCH w przepisach i w planie, więc stara ilość może stać się nieprzeliczalna na nową oś. Kod obsługuje to poprawnie (`recipes/service.py::_ingredient_values`, `planning/service.py::_product_values` — `complete=False` z komunikatem, nie 500), ale silnik zakupowy B10 musi zrobić to samo (wpisane do karty B10) | nic nie blokuje; do formalnego zatwierdzenia przez właściciela |
| D16 | Czy ADMIN widzi na ścieżkach użytkownika WSZYSTKIE encje scope'owane, czy tylko swoje (ustalenie R1) | **Zostawić stan faktyczny** (`ScopedQuery.visible_condition` → `true()` dla ADMIN-a, zgodnie z macierzą 08_TESTING §4, gdzie ADMIN ma 200 w każdym wierszu) i doprecyzować 04_API §3 pkt 2. Konflikt: 04_API §3 pkt 2 i 07_SECURITY §4 mówią „ADMIN nie jest wyjątkiem na ścieżkach użytkownika, do cudzych danych ma `/admin/*`" — i tak działa `member_profiles` (test `test_admin_nie_dostaje_wyjatku_na_sciezce_uzytkownika`), ale `ScopedQuery` robi odwrotnie. Zmiana jest tania w jednym miejscu (`app/core/scope.py:160`). **Stan po B05: bez odpowiedzi właściciela utrzymano stan faktyczny** (ADMIN widzi wszystko, macierz 08 §4) i zaasercjonowano go testem `tests/api/recipes/test_recipes_api.py::test_d16_admin_widzi_cudze_przepisy_na_sciezkach_uzytkownika` — decyzja jest widoczna w kodzie, nie domyślna; rozstrzygnięcie odwrotne zaczyna od zmiany `scope.py` i tego testu. **Stan po R2 (2026-08-21): koszt odwrócenia rośnie — warto zdecydować PRZED B08.** Zachowanie dziedziczy dziś pięć encji ze scope (`recipes`, `plan_days`, `day_templates`, `week_templates`, `week_cycles`), a B08–B11 dołożą spiżarnię, generacje zakupowe i listy. R2 nie rozstrzyga tego sam, bo konflikt jest między dokumentami NADRZĘDNYMI wobec review (08_TESTING §4 daje ADMIN-owi 200 w każdym wierszu macierzy, 04_API §3 pkt 2 i 07_SECURITY §4 mówią, że ADMIN nie jest wyjątkiem na ścieżkach użytkownika) — to wybór właściciela, nie implementacji | nic nie blokuje formalnie; od B06 każda encja planningu dziedziczy to zachowanie, od B08 dojdą kolejne |

## Procedura

1. Batch, który trafia na decyzję właściciela: zbiera pytania → wpisuje
   tu jako OPEN z rekomendacją → raportuje w Completion notes → NIE zgaduje.
2. Właściciel zatwierdza (tabela „Zatwierdzone" + data).
3. Agent zamykający decyzję aktualizuje dotknięte karty batchy i ADR/architekturę.
