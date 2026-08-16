# ADR-010 — Publiczne linki list: token 256-bit, expiry, revoke, zero PII

Status: ACCEPTED (2026-08-16)

## Kontekst
Lista zakupowa udostępniana przez link (WhatsApp/SMS/QR) osobom bez konta;
nie wolno ujawnić żadnych innych danych rodziny.

## Decyzja
- Token: `secrets.token_urlsafe(32)` (256 bitów), unique index, lookup
  tylko po pełnym tokenie; URL `/l/{token}`.
- Uprawnienia tokenu: odczyt listy + PATCH `checked` pozycji. Nic więcej.
- Expiry = `expires_at` listy (default +7 dni, wybierane przy udostępnieniu);
  revoke ustawia `token_revoked`. Po wygaśnięciu/odwołaniu: 410 + przyjazny
  ekran „Ta lista zakupowa już wygasła lub została usunięta."
- Odpowiedź publiczna: nazwa listy, pozycje (label, ilość, kategoria,
  checked), expires_at — zero nazwisk/emaili/id.
- Rate limit `/public/*` 60/min/IP; tokeny maskowane w logach.
- Udostępnianie: Web Share API + kopiuj link + QR (render kliencki).
  Bez płatnych integracji.

## Konsekwencje
+ Bezpieczne przy entropii 256 bit; brute force niepraktyczny + rate limit.
− Link raz wysłany żyje do expiry/revoke — kontrolka „Odwołaj link"
  widoczna przy liście.
