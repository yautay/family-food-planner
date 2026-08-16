---
name: ffp-security
description: Reguły bezpieczeństwa Family Food Planner — sesje/CSRF/rate-limit, scope household, publiczne tokeny list, walidacja uploadów, higiena logów i sekretów. Ładuj przy batchach dotykających auth, tokenów, uploadów, eksportu danych lub deploymentu.
---

<!-- verified: 2026-08-16 (blueprint; R1/R3/R4 uzgadniają z kodem)
     źródła nadrzędne: 07_SECURITY, ADR-003, ADR-006, ADR-010, ADR-011 -->

# FFP — kontrakt bezpieczeństwa

## Twarde zasady (łamanie = blokada review)

1. Żadnej własnej kryptografii — tylko `argon2-cffi`, `secrets`, `hmac`.
2. **Auth = sesje server-side + cookie** (ADR-003). NIE wprowadzaj JWT,
   OAuth2 bearer, python-jose, passlib — nawet jeśli „best practice"
   z ogólnej wiedzy to sugeruje. Cookie: HttpOnly+Secure+SameSite=Lax.
3. Sekrety wyłącznie z env; nowa zmienna → `.env.example` (placeholder,
   nie wartość). Klucz Anthropic tylko server-side. Żadnych haseł
   w seedach/testach commitowanych z realną wartością.
4. Hasła: argon2id; rehash przy logowaniu po zmianie parametrów; min. 10 zn.

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
- Wygasły/odwołany/nieistniejący → 410 + przyjazny ekran (nigdy stacktrace).
- Rate limit `/public/*` 60/min/IP; `/auth/login` 5/min/IP + blokada konta.
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
