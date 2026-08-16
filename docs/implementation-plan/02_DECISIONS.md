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

## Otwarte

| # | Decyzja | Rekomendacja | Blokuje |
|---|---|---|---|
| D6 | Backup off-device: dokąd kopiować backupy poza Odroida (NAS? chmura? który provider?) | rclone do dowolnego zdalnego storage (konfig w env); minimum: cotygodniowa kopia ręczna na inny dysk | **B18 (bramka konfiguracji)** |
| D7 | Domena/subdomena aplikacji + szczegóły istniejącego reverse proxy (nginx? porty? jak dokładany jest vhost) | subdomena dedykowana, proxy → 127.0.0.1:8080 | **B18 (bramka)** |
| D8 | 2FA logowania | **FUTURE** — nie w MVP; hasła argon2id + rate limit wystarczą na start; wrócić po wdrożeniu | — |
| D9 | Progi statusów żywieniowych (za mało/OK/za dużo) | 90–110% celu, konfigurowalne per użytkownik w ustawieniach; batch B06 może przyjąć bez osobnego zatwierdzenia | — |
| D10 | Retencja starych list zakupowych i planów | nic nie usuwamy automatycznie (historia = wartość); ręczne bulk delete dla właściciela; rewizja przy R4 | — |
| D11 | IG produktów — źródło danych | uzupełnianie ręczne przy produktach, gdzie ŁG ma znaczenie (tabele międzynarodowe IG jako źródło do przepisania ręcznego; bez bulk importu — prawa autorskie tabel); UI toleruje braki (flaga „niepełne dane") | — |

## Procedura

1. Batch, który trafia na decyzję właściciela: zbiera pytania → wpisuje
   tu jako OPEN z rekomendacją → raportuje w Completion notes → NIE zgaduje.
2. Właściciel zatwierdza (tabela „Zatwierdzone" + data).
3. Agent zamykający decyzję aktualizuje dotknięte karty batchy i ADR/architekturę.
