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
- Rate limit (slowapi): `/auth/login` 5/min/IP + wykładniczy backoff po
  10 nieudanych na konto (blokada 15 min, komunikat neutralny).

## 3. CSRF, CORS, nagłówki

- CSRF: double-submit cookie — `csrf_token` (nie-HttpOnly) + wymagany
  nagłówek `X-CSRF-Token` dla POST/PUT/PATCH/DELETE; porównanie
  `hmac.compare_digest`. Publiczne PATCH-e checkboxów (token listy) —
  wyłączone z CSRF (autoryzuje token w URL), ale rate-limited.
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
- Scope PRIVATE/HOUSEHOLD w serwisach przez `ScopedQuery` — każde zapytanie
  o encję cudzą kończy się 404 (nie 403 — nie potwierdzamy istnienia).
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
