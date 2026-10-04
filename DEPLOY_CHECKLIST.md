# Checklista wdrożenia na produkcję (stan: 2026-10-04, po `batch(22)`)

Dla **właściciela** — komendy wykonuje człowiek, nie agent AI (CLAUDE.md §3: produkcja jest poza zasięgiem
sesji AI). Szczegóły i runbooki: `deploy/README.md`, `deploy/lxc/README.md` (w drzewie jako praca B18, jeszcze
niezacommitowana), a docelowo `docs/OPERATIONS.md` (B18b, jeszcze nie istnieje).

## Co jedzie na produkcję

| Zmiana | Skąd | Uwagi |
|---|---|---|
| Migracje **`0017`** (`ADD VALUE 'global'`) i **`0018`** (CHECK-i) | B21 | `0017` jest **NIEODWRACALNA** (PostgreSQL nie ma `DROP VALUE`) — `downgrade` to no-op; wycofanie = restore z dumpu |
| Zakres „Wszyscy” dla przepisów, kopiowanie, archiwizacja | B21 | UI + API |
| Rozwijana podpowiedź w `/admin/dane` | B22 | jedyna zmiana runtime z B22 |
| Narzędzie `/pdf-extract`, `data/diet-imports/` | B22 | **NIE jedzie** (poza białą listą rsynca: tylko `backend/` bez testów, `frontend/dist/`, `VERSION`) |
| Infrastruktura: LXC, ansistrano, backup | B18 | **nie ma jej w commicie** — patrz Etap 0 |

---

## Etap 0 — bramki przed deployem (laptop)

- [ ] **B18 jest zacommitowane.** `deploy/`, `docker/`, `Taskfile.yml` (targety deployu), `serve.sh`,
      `test_deploy_config.py` i reszta B18 leżą dziś w drzewie roboczym; commit `da09281` (B22) ich nie zawiera.
      Bez nich nie ma czego wdrażać, a `task deploy` używa `git describe --dirty` jako wersji release'u.
- [ ] Repo ma **remote** i wypchnięty `master` (dziś: brak remote'a — `git remote add origin <url>`, `git push -u origin master`).
- [ ] `git status` czysty; `git log -3` zawiera `batch(21)`, `batch(22)` i commit B18.
- [ ] `task check` zielony na tym commicie (ostatni zielony: unit 572, integration 292, api 443, vitest 409 — na drzewie
      z B18 w trakcie).
- [ ] Maszyna operatora: Docker Desktop, `uv`, Node 22+, `go-task`, **WSL (Ubuntu) z `ansible-core>=2.16,<2.18` z pipa**
      w `~/.venvs/ansible` (nie z `apt`); `task deploy-galaxy` wykonane (role ansistrano).
- [ ] Vault z sekretami **poza repo**: `~/pasnik-prod.yml` (`vault_db_password`, `vault_secret_key`). Nigdy w czacie
      ani w plikach śledzonych.
- [ ] `deploy/group_vars/prod.yml`: `ct_ip` i `bridge_gateway` bez `CHANGE_ME`.

## Etap 1 — czy maszyna już stoi?

Jeśli **to pierwsze wdrożenie** (kontener LXC `pasnik` na .121 nie istnieje) — najpierw `deploy/lxc/README.md` §1–4
(`create-incus.sh` → `SAMOTEST: OK`, reguły `DOCKER-USER`, klucz hosta), potem:

- [ ] `task provision` (raz na maszynę; kanał root; prosi o hasło do vaulta).

Jeśli maszyna już działa — pomiń provision (zmiana konfiguracji to provision, nie deploy).

## Etap 2 — kopia bezpieczeństwa PRZED deployem

Migracja `0017` jest nieodwracalna, więc kopia jest jedyną drogą powrotu schematu.

- [ ] Hook `before-symlink` robi dump automatycznie (zestaw w `shared/backups`) — **ale** zrób też własny, ręczny
      punkt kontrolny (`pasnik-backup` / `task backup`-odpowiednik z `docs/OPERATIONS.md`, gdy będzie) i potwierdź, że
      plik dumpu jest niepusty.
- [ ] Zapisz, gdzie leży dump sprzed migracji (potrzebny przy rollbacku z migracją).

## Etap 3 — próba na sucho

- [ ] `task deploy -- --check --diff` — sprawdza kanał root, prawa, bazę i rsync (rola ansistrano pominięta; wymaga
      ukończonego provisionu). Przeczytaj diff: czy w release'ie jest tylko biała lista i brak `.env`.

## Etap 4 — deploy

- [ ] `task deploy` → `fe-build` → `secrets-scan` → ansistrano: guard stechłego dista, rsync, `uv sync --frozen --no-dev`,
      import-smoke, **dump bazy**, `alembic upgrade head` (`0017`, `0018`), symlink `current`, restart,
      health z asercją na treść.
- [ ] Wynik deployu bez błędów; asercja zdrowia przeszła (`status: ok`, `version` = release, `migrations: ok`).

## Etap 5 — weryfikacja po wdrożeniu

- [ ] `https://pasnik.cpt-sztos.com/api/v1/health` → `{"status":"ok", ...}`, `version` = ten release, `migrations: ok`, dysk ok.
- [ ] `/api/docs` → 404 (dokumentacja API nie jest publiczna).
- [ ] Logowanie na konto ADMIN działa; ekran „Przepisy” się ładuje.
- [ ] Przepis z zakresem „Wszyscy” (jeśli już jakiś jest): widoczny dla zwykłego użytkownika **innej rodziny**,
      z przyciskiem „Kopiuj do mojej rodziny” zamiast „Edytuj”.
- [ ] `/admin/dane` → „Co to jest kopia instancji i kiedy jej użyć?” rozwija podpowiedź (klik, także na telefonie).
- [ ] Logi (`journalctl -u pasnik`) bez błędów 5xx i bez tokenów/haseł.
- [ ] Gdy Caddy jeszcze nie przełączony (D7): blok `pasnik.cpt-sztos.com` w `/etc/caddy/Caddyfile` podmień na ten
      z `task deploy-caddy-vhost`, potem `caddy validate --config /etc/caddy/Caddyfile && sudo systemctl reload caddy`.
- [ ] Pierwsze konto ADMIN (tylko przy świeżej bazie):
      `wsl -d Ubuntu-22.04 -- ssh -t -p 2223 root@192.168.2.121 /usr/local/bin/pasnik-cli -- python -m app.cli create-admin`.

## Etap 6 — wgranie jadłospisu 0001 (osobno od deployu, ręcznie, z UI)

Paczka to **zwykły import** — nic nie dotyka bazy poza aplikacją. Zrób to **po** udanym deployu.

1. [ ] **Nie importuj do bazy z seedem demo** (`task db-seed-demo`): Cebula, Pomidor (PIECE vs MASS w demo) i Oliwa
       (MASS vs VOLUME w demo) zostałyby reużyte z definicji demo i zapisane ilości by się nie przeliczały.
2. [ ] **Sprawdź kolizje z produktami założonymi ręcznie:** pobierz eksport instancji z `/admin/dane` i na laptopie:
       `task pdfx-index -- data/diet-imports/0001-dieta-2000/spec.json --instance-export <export.zip>` — konflikt miary
       z istniejącym produktem zatrzyma (nie obchodź; rozstrzygnij ręcznie).
3. [ ] **Kopia przed wgraniem** (dump / „Kopia danych rodziny” z `/admin/dane`).
4. Wybierz wariant:
   - **Przepisy rodzinne (domyślnie):** `data/diet-imports/0001-dieta-2000/export.zip` (z repo, `scope=user`, bez
     e-maili). Wgraj: Ustawienia → „Kopia danych rodziny” → plik → **Sprawdź plik** → przeczytaj podgląd → **Wczytaj**.
   - **Przepisy „Wszyscy” (ADMIN):** zbuduj lokalnie (nie commituj — zawiera Twój e-mail):
     `task pdfx-package -- data/diet-imports/0001-dieta-2000/spec.json --recipe-scope global --owner-email <Twój e-mail ADMIN-a> --out <ścieżka-poza-repo>.zip`.
     Wgraj w `/admin/dane` → „Wczytaj kopię instancji” **z tego samego konta (ten sam e-mail)**.
5. [ ] W podglądzie DRY-RUN: **`users` NIE może być w „Nowe”** (inaczej e-mail nie pasuje do konta — przerwij);
       kategorie i tagi systemowe `reużyte`, nowe są produkty (44), przepisy (12), tag „podwieczorek”.
6. [ ] Po wczytaniu: 12 przepisów, 44 produkty; produkty mają status „niezweryfikowane” — zweryfikuj w `/admin/weryfikacja`.
7. [ ] Ponowne wczytanie tej samej paczki niczego nie dubluje (produkty i przepisy po nazwie) — nie musisz tego robić,
       ale jest bezpieczne.

---

## Rollback

| Sytuacja | Postępowanie |
|---|---|
| Deploy padł **przed** migracją | nic nie zmienione w bazie; popraw przyczynę i `task deploy` ponownie |
| Nowy release działa źle, **migracja się wykonała** | `systemctl stop pasnik` → `restore.sh` z dumpu sprzed migracji (`/usr/local/lib/pasnik/restore.sh`, jako `pasnik`; dump z `shared/backups`) → dopiero `task rollback`. `task rollback` sam **nie cofa** migracji, a `0017` nie ma `downgrade` |
| Konkretne wydanie | `task rollback -- -e ansistrano_rollback_to_release=<timestamp>` |
| Zły import jadłospisu | przywróć kopię z Etapu 6 pkt 3 (lub usuń przepisy/produkty z UI — produkty użyte w przepisach blokuje 409 `used_in`) |

## Czego NIE robić

- Nie wgrywaj paczki przez bazę ani SQL-em — tylko import z UI (przechodzi przez serwisy, audyt, walidację).
- Nie commituj paczki `global` z e-mailem ani PDF-ów (`data/source_pdfs/`, `docs/dieta.pdf` są w `.gitignore`).
- Nie odpalaj `pdfx-roundtrip` na produkcji — działa wyłącznie na lokalnej bazie `*_test` i robi `TRUNCATE`.
- Sekretów (`vault_db_password`, `vault_secret_key`) nie wklejaj do czatu ani do plików w repo.
