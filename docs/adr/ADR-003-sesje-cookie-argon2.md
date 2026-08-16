# ADR-003 — Sesje server-side + cookie, argon2id, bez JWT i samorejestracji

Status: ACCEPTED (2026-08-16)

## Kontekst
Aplikacja publicznie dostępna z Internetu; użytkowników tworzy zaufany
administrator (rodzina). SPA i API na tym samym originie.

## Decyzja
- Hasła: argon2id (argon2-cffi). Sesje: rekord w PG, id 256-bit w cookie
  `HttpOnly; Secure; SameSite=Lax`; TTL przesuwne 30 dni.
- CSRF: double-submit cookie + nagłówek `X-CSRF-Token`.
- Bez JWT: nic nie wymaga bezstanowości, a odwołanie sesji ma działać
  natychmiast. Bez samorejestracji: konta tworzy ADMIN; pierwszy admin
  przez CLI (`task create-admin`), nigdy seed z hasłem w repo.
- Rate limit logowania (slowapi) + blokada konta po serii porażek.

## Konsekwencje
+ Model prosty do audytu; wylogowanie/odwołanie = DELETE wiersza.
− Sesje w DB = zapytanie na request (znikome przy tej skali).
2FA świadomie poza zakresem (FUTURE — patrz 02_DECISIONS).
