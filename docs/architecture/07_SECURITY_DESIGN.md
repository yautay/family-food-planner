# 07 — Projekt bezpieczeństwa

Aplikacja wystawiona do Internetu ⇒ bezpieczeństwo jest wymaganiem
podstawowym, nie dodatkiem. Zasada: nie implementujemy własnej kryptografii;
biblioteki standardowe (argon2-cffi, secrets, hmac).

## 1. Model zagrożeń (realny, domowy)

Aktorzy: (a) internetowy skaner/bot, (b) osoba z publicznym linkiem listy,
(c) błąd członka rodziny. NIE bronimy się przed targeted APT — bronimy się
przed masowym skanowaniem, credential stuffing, wyciekiem danych przez
publiczne linki i błędami aplikacyjnymi (IDOR/XSS/CSRF/upload).

## 2. Uwierzytelnianie (ADR-003)

- Hasła: **argon2id** (argon2-cffi, parametry domyślne biblioteki,
  rehash przy logowaniu gdy parametry wzrosną). Minimalna długość 10.
- Sesje: server-side w PG (`sessions`), id = `secrets.token_urlsafe(32)`;
  cookie: `HttpOnly; Secure; SameSite=Lax; Path=/`; TTL 30 dni przesuwne;
  logout = delete row. Bez JWT (nic tu nie wymaga bezstanowości, a odwołanie
  sesji ma być natychmiastowe).
- Brak samorejestracji; konta tworzy ADMIN. Pierwszy admin: CLI
  `task create-admin` (nigdy seed z hasłem w repo — lekcja netQArnera).
- Rate limit (slowapi): `/auth/login` 5/min/IP + blokada konta po 10 nieudanych
  próbach (komunikat neutralny — identyczny jak przy złym haśle).
  Stan faktyczny (BATCH_02, `app/core/security.py`): blokada jest **stała,
  15-minutowa**, a licznik porażek zeruje się w momencie założenia blokady —
  nie ma backoffu wykładniczego. Wystarcza na model zagrożeń z §1 (≈10 prób
  na 15 min na konto, przy jednoczesnym limicie 5/min/IP); zaostrzenie
  parametrów wraca do przeglądu w BATCH_17 razem z parametrami argon2 i TTL.

## 3. CSRF, CORS, nagłówki

- CSRF: double-submit cookie — `csrf_token` (nie-HttpOnly) + wymagany
  nagłówek `X-CSRF-Token` dla POST/PUT/PATCH/DELETE; porównanie
  `hmac.compare_digest`. Publiczne PATCH-e checkboxów (token listy) —
  wyłączone z CSRF (autoryzuje token w URL), ale rate-limited.
  Drugi wyjątek (BATCH_02, `CSRF_EXEMPT_PREFIXES`): **`POST /auth/login`** —
  przed zalogowaniem nie istnieje jeszcze cookie `csrf_token`, z którym można
  by porównać nagłówek. Żądanie chroni rate limit i blokada konta (§2);
  ryzykiem jest wyłącznie „login CSRF" (wmuszenie ofierze cudzej sesji), a bez
  samorejestracji i przy jednym origin jest ono w tym modelu zagrożeń pomijalne.
- CORS: brak (SPA serwowana z tego samego origin). Nie włączamy „na zapas".
- Nagłówki (middleware): `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: same-origin`, `X-Frame-Options: DENY`,
  CSP: `default-src 'self'; img-src 'self' data: blob:; style-src 'self'
  'unsafe-inline'` (Tailwind inline styles), bez zewnętrznych źródeł.
  HSTS ustawia reverse proxy.
  Jedyny wyjątek (BATCH_02): CSP nie jest wysyłane dla `/api/docs`
  i `/api/openapi.json`, bo Swagger UI ładuje skrypty z CDN. W prod te
  ścieżki nie istnieją (`docs_url=None`), więc wyjątek jest tam martwy.

## 4. Autoryzacja

- Role ADMIN/USER na dependency (`require_admin`).
- Scope PRIVATE/HOUSEHOLD w serwisach przez `ScopedQuery` — zapytanie USERA
  o encję cudzą kończy się 404 (nie 403 — nie potwierdzamy istnienia).
- **ADMIN jest wyjątkiem w ODCZYCIE encji ze scope** (`visible_condition` →
  `true()`): decyzja właściciela **D16, zatwierdzona 2026-08-21**, zgodna
  z macierzą 08_TESTING §4. Uzasadnienie: administrator tej instalacji i tak
  ma dostęp do bazy i do `/admin/*`, więc udawanie, że nie widzi, dawałoby
  pozorne bezpieczeństwo, a utrudniałoby wsparcie użytkowników. Granice tego
  wyjątku:
  - **nie rozciąga się na MUTACJE reguł właścicielskich** — zmiana scope
    i usunięcie encji przechodzą przez `ScopedQuery.assert_can_manage`;
  - **nie rozciąga się na zasoby adresowane „moją rodziną"** —
    `/households/my` i profile członków pokazują ADMIN-owi WŁASNĄ rodzinę,
    do cudzych ma `/admin/households/*` (04_API §3 pkt 2a);
  - **nie rozciąga się na dane osobowe w odpowiedziach publicznych**
    (§5) ani na hasła i tokeny (nigdy w logach — §8).
  Konsekwencja dla batchy: każda nowa encja ze `ScopedMixin` dziedziczy to
  zachowanie automatycznie i MA je zaasercjonować w macierzy uprawnień
  (wzorzec: `tests/api/recipes/test_recipes_api.py::test_d16_admin_widzi_cudze_przepisy_na_sciezkach_uzytkownika`).
- Testy anty-IDOR obowiązkowe w każdym batchu z nowym zasobem: user B nie
  odczyta/nie zmieni zasobu usera A (macierz w 08_TESTING §4).

## 5. Publiczne tokeny list (ADR-010)

256-bit `token_urlsafe(32)`; lookup po unique index (stała czasowo równość
nieistotna — token nieodgadywalny); expiry (default 7 dni, konfigurowalne
przy udostępnieniu), revoke, 410 z przyjaznym ekranem; odpowiedź bez PII
(tylko pozycje listy); rate limit 60/min/IP na `/public/*`; tokeny nie
logowane (filtr w logach — ścieżka maskowana do `/public/lists/***`).

## 6. Uploady

Dotyczy zdjęć (przepisy/produkty) i PDF-ów importu:
- limity: obraz ≤ 10 MB, PDF ≤ 25 MB; MIME sniffing po treści (Pillow
  verify / nagłówek %PDF), nie po rozszerzeniu;
- zapis pod losową nazwą na bind mount, poza web-rootem; serwowanie przez
  endpoint z autoryzacją (nie StaticFiles bez auth);
- obrazy re-enkodowane przez Pillow (strip EXIF, usunięcie payloadów),
  miniatury generowane; PDF nigdy nie jest renderowany server-side poza
  pdfplumber (parsing w try/except z limitem czasu).

## 7. Sekrety i konfiguracja

Wyłącznie env (pydantic-settings): `DATABASE_URL`, `SECRET_KEY` (sesje/CSRF),
`ANTHROPIC_API_KEY` (importer). `.env` w .gitignore od pierwszego commita;
`.env.example` z placeholderami. W prod: plik env na hoście `chmod 600`
lub docker secrets. Klucz API Anthropic używany wyłącznie server-side.

Skan repo: `task secrets-scan` (gitleaks w kontenerze). Konfiguracja
`.gitleaks.toml` (od review R2, 2026-08-21) zachowuje WSZYSTKIE domyślne
reguły (`useDefault = true`) i wycisza wyłącznie dwa literały haseł testowych
(`haslo-testowe-2026`, `nowe-haslo-2026`) — wyciszenie jest po WZORCU, nie po
ścieżce, więc każdy inny sekret w tych samych plikach nadal wywala skan.
Bez tego skan zwracał 14 trafień, wszystkie na te dwa literały, i kończył się
kodem 1 na czystym repo, czyli przestawał być użyteczną bramką. Hasła testowe
nie otwierają żadnego środowiska: konta powstają komendą `task create-admin`
(prompt albo `FFP_ADMIN_*`), a w repozytorium nie ma działającego hasła (§2).

## 8. Logowanie i błędy

structlog: request id, user id (nie email), ścieżka, status, czas. NIGDY:
hasła, tokeny (sesyjne/publiczne/API), pełne payloady z danymi. Wyjątki:
stacktrace do logów, użytkownik dostaje generyczny komunikat + id błędu.
Audit log (02 §12) osobno od logów technicznych.

## 9. Zależności i baza

- `uv lock` + `npm lockfile`; podbicia zależności przy Review batchach
  (`pip-audit` / `npm audit` jako krok Review).
- PG: osobny user aplikacyjny bez SUPERUSER; port nie wystawiony poza
  sieć docker compose; hasło z env.

## 10. Checklisty bezpieczeństwa w procesie

Każdy batch ma sekcję Security (co dotyka i jak chroni). Review batche
uruchamiają `/security-review` (skill Claude Code) na całości zmian od
poprzedniego review. BATCH_17 (hardening) = pełny przegląd przed wdrożeniem.
