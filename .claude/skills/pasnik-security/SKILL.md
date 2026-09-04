---
name: pasnik-security
description: Reguły bezpieczeństwa Paśnika — sesje/CSRF/rate-limit, scope household, publiczne tokeny list, walidacja uploadów, higiena logów i sekretów. Ładuj przy batchach dotykających auth, tokenów, uploadów, eksportu danych lub deploymentu.
---

<!-- verified: 2026-08-16 (REVIEW R1 — uzgodnione z kodem po B01–B04; R3/R4 dalej)
     stack: FastAPI 0.141 · structlog 26 · argon2-cffi 25 · slowapi 0.1.10 · PG 17
     źródła nadrzędne: 07_SECURITY, ADR-003, ADR-006, ADR-010, ADR-011 -->

## Co już jest w kodzie (BATCH_01–04)

- Konfiguracja i sekrety: `app/core/config.py` + `.env.example`; `.env`
  w `.gitignore`. Brak wymaganej zmiennej = twardy błąd startu.
- Logi: `app/core/logging.py` — request id na każdym requeście, funkcja
  `mask_path()` maskuje `/public/lists/<token>` do `/public/lists/***`.
- Błędy: `app/core/errors.py` — użytkownik dostaje `{"error": {...}}`
  z `details.error_id`, stacktrace wyłącznie do logów.
- Compose dev publikuje porty tylko na 127.0.0.1; prod (B18) nie publikuje
  portów bazy w ogóle.
- **Sesje i hasła (B02)**: `app/core/security.py` (argon2id + rehash,
  `generate_token`, `tokens_match`, TTL 30 dni przesuwne, blokada konta
  10 porażek / 15 min), `app/core/cookies.py` (`pasnik_session` HttpOnly +
  `csrf_token` dla JS; `Secure` gdy `APP_ENV=prod`), `app/core/deps.py`
  (jedyne wejście autoryzacji). Logowanie: rate limit 5/min/IP, jeden
  komunikat 401 na wszystkie powody odmowy (anty-enumeracja).
- **CSRF i nagłówki (B02, NIE B17)**: `app/core/middleware.py` —
  `CsrfMiddleware` (`CSRF_EXEMPT_PREFIXES`: `/auth/login`, `/public/`) oraz
  `SecurityHeadersMiddleware` z CSP. B17 je PRZEGLĄDA, nie tworzy.
- **Scope (B03)**: `app/core/scope.py` — `ScopedQuery` (cudza encja = 404).
  Encje bez kolumn scope (`member_profiles`) filtruje się porównaniem
  `household_id` — identyczne 404 dla cudzego i nieistniejącego (04_API §2a).
- Do dostarczenia: publiczne tokeny list i rate limit `/public/*` (B11),
  uploady (B05 `core/uploads.py`), przegląd parametrów argon2/TTL i IP za
  reverse proxy (B17).

# Paśnik — kontrakt bezpieczeństwa

## Twarde zasady (łamanie = blokada review)

1. Żadnej własnej kryptografii — tylko `argon2-cffi`, `secrets`, `hmac`.
2. **Auth = sesje server-side + cookie** (ADR-003). NIE wprowadzaj JWT,
   OAuth2 bearer, python-jose, passlib — nawet jeśli „best practice"
   z ogólnej wiedzy to sugeruje. Cookie: HttpOnly+Secure+SameSite=Lax.
3. Sekrety wyłącznie z env; nowa zmienna → `.env.example` (placeholder,
   nie wartość). Klucz Anthropic tylko server-side. Żadnych haseł
   w seedach/testach commitowanych z realną wartością.
4. Hasła: argon2id; rehash przy logowaniu po zmianie parametrów; min. 10 zn.
   Blokada konta jest STAŁA (15 min po 10 porażkach), nie wykładnicza —
   parametry wracają do przeglądu w B17 (07_SECURITY §2 doprecyzowane w R1).

## CSRF / nagłówki / CORS

- Mutacje wymagają `X-CSRF-Token` (double-submit, `hmac.compare_digest`).
  Wyjątek: publiczne PATCH-e tokenowe (autoryzuje token, jest rate limit).
- Middleware nagłówków: nosniff, Referrer-Policy same-origin, X-Frame-Options
  DENY, CSP self (img: data:/blob:). CORS nie istnieje (jeden origin) —
  nie dodawaj CORSMiddleware „na zapas".

## Scope i IDOR

- Autoryzacja zasobów przez `ScopedQuery` — cudzy zasób zwraca **404**
  (nie 403: nie potwierdzamy istnienia). Admin nie jest wyjątkiem
  w ścieżkach użytkownika — ma własne endpointy `/admin/*`.
- KAŻDY nowy endpoint zasobu = test macierzy 08_TESTING §4 (anonim /
  obcy USER / członek rodziny / właściciel / ADMIN) w tym samym batchu.

## Publiczne tokeny list (ADR-010)

- `secrets.token_urlsafe(32)`; lookup po pełnym tokenie (unique index).
- Token pozwala WYŁĄCZNIE: odczyt listy + PATCH `checked`. Odpowiedź:
  nazwa listy, pozycje (label, ilość, kategoria, checked), expires_at —
  **test asercji białej listy pól** obowiązkowy (zero nazwisk/emaili/id).
- Wygasły/odwołany → **410**, nieznany token → **404**, token o złym kształcie
  → **422** (wzorzec `^[A-Za-z0-9_-]{43}$` odsiewa skanery przed zapytaniem).
  Komunikat we wszystkich trzech przypadkach jest IDENTYCZNY, a frontend mapuje
  404 i 410 na jeden ekran — różnica statusów jest świadomie przyjęta
  (07_SECURITY §5 pkt 8, audyt REVIEW R3), nie do „naprawiania" po cichu.
- Rate limit `/public/*` 60/min/IP na WSPÓLNYM liczniku całej ścieżki
  (`limiter.shared_limit`, scope `public-lists`) — nowy endpoint publiczny
  dołącza do tego scope, nie zakłada własnego. `/auth/login` 5/min/IP
  + blokada konta.
- Tokeny maskowane w logach (`/public/lists/***`) — dotyczy też access
  logów Uvicorna.

## Uploady (07_SECURITY §6)

- Limity: obraz ≤10 MB, PDF ≤25 MB. Typ po TREŚCI (Pillow verify / nagłówek
  %PDF), nigdy po rozszerzeniu. Losowa nazwa (uuid4), zapis poza web-rootem,
  serwowanie przez endpoint z autoryzacją — nigdy surowe StaticFiles.
- Obrazy re-enkodowane (strip EXIF); PDF parsowany tylko pdfplumberem
  z limitem czasu, nigdy renderowany server-side.

## Logi i błędy

- Nigdy w logach: hasła, tokeny (sesyjne/publiczne/API), pełne payloady
  z danymi osobowymi. User w logach po id, nie emailu.
- Użytkownik dostaje generyczny komunikat + id błędu; stacktrace tylko do
  logów. Audit log (operacje wrażliwe) ≠ logi techniczne.

## Proces

- Batch z sekcją Review Skills zawierającą SKILL-SECREV: uruchom
  `/security-review` na diffie PRZED commitem; ustalenia napraw albo
  jawnie odnotuj w Completion notes z uzasadnieniem.
- Zależności: `task audit` (pip-audit + npm audit) i `task secrets-scan`
  (gitleaks) w Review batchach i B17.
