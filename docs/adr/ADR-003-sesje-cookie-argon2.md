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

## Uszczegółowienia z implementacji (BATCH_02, 2026-08-16)

- Cookies: `pasnik_session` (HttpOnly) i `csrf_token` (czytelne dla JS),
  `SameSite=Lax; Path=/`; flaga `Secure` włączana przez `APP_ENV=prod`
  (na http://localhost nie ma TLS). Nazwy i atrybuty w `app/core/cookies.py`.
  **Od BATCH_17 (2026-09-05) w prod nazwy mają prefiks `__Host-`**
  (`__Host-pasnik_session`, `__Host-csrf_token`) — wiąże cookie z jednym
  hostem (wymaga `Secure`, zabrania `Domain`, wymusza `Path=/`), co zamyka
  podstawienie pary cookie+nagłówek przez subdomenę (07_SECURITY §3).
  Frontend sprawdza obie nazwy (`CSRF_COOKIE_CANDIDATES`), bo nie zna
  `APP_ENV`.
- TTL przesuwne działa po OBU stronach: przy przesunięciu `sessions.expires_at`
  (nie częściej niż raz na dobę) serwer wysyła ponownie oba cookies z nowym
  `Max-Age`. Bez tego przeglądarka kasowałaby cookie 30 dni po logowaniu
  niezależnie od aktywności.
- Blokada konta: kolumny `users.failed_login_count` i `users.locked_until`
  (10 porażek → 15 min). Stan w bazie, nie w pamięci procesu — restart
  aplikacji nie może zerować blokady.
- Nieistniejące konto, złe hasło, konto nieaktywne i konto zablokowane dają
  identyczną odpowiedź 401 z tym samym komunikatem; ścieżka „nie ma takiego
  konta" wykonuje pustą weryfikację argon2, żeby nie różnić się czasem.
- Zmiana hasła i dezaktywacja konta przez ADMIN-a kasują wszystkie sesje
  tego konta.
- `DELETE /admin/users/{id}` usuwa konto fizycznie; konto z powiązanymi
  danymi (FK RESTRICT z modułów domenowych) kończy się 409 z podpowiedzią
  „dezaktywuj zamiast usuwać" (spójne z ADR-012). Własnego konta nie można
  usunąć, zdegradować ani dezaktywować.

## Konsekwencje
+ Model prosty do audytu; wylogowanie/odwołanie = DELETE wiersza.
− Sesje w DB = zapytanie na request (znikome przy tej skali).
2FA świadomie poza zakresem (FUTURE — patrz 02_DECISIONS).
