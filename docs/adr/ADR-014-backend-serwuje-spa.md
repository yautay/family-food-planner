# ADR-014 — Backend serwuje SPA i uploady; jeden kontener aplikacyjny

Status: ACCEPTED (2026-08-16)

> **Doprecyzowane przez ADR-017 (2026-10-03, D29)**: decyzja rdzeniowa —
> backend serwuje `/api/v1/*`, SPA i `/uploads/*` z jednego originu — obowiązuje
> bez zmian. Na produkcji zmienia się wyłącznie OPAKOWANIE: zamiast obrazu
> z `dist` w środku jest katalog release w LXC (`frontend/dist` budowany
> lokalnie, `SPA_DIST_DIR` ustawiony w `pasnik.env`), a rollback przełącza
> symlink, nie tag obrazu.

## Kontekst
Prod = Odroid za istniejącym reverse proxy. Do rozstrzygnięcia: osobny
kontener nginx dla statyk czy serwowanie z FastAPI.

## Decyzja
Jeden kontener `app`: FastAPI serwuje `/api/v1/*`, SPA dist (StaticFiles
z fallbackiem index.html dla tras SPA) i `/uploads/*` (przez endpoint
z autoryzacją, nie surowe StaticFiles). Multi-stage Dockerfile buduje
frontend i wkłada dist do obrazu. TLS, HTTP/2, kompresja — na istniejącym
reverse proxy hosta.

## Konsekwencje
+ Jeden origin (brak CORS), jeden obraz do wdrożenia/rollbacku, prostszy
  compose.
− Uvicorn serwuje statyki wolniej niż nginx — bez znaczenia przy skali
  rodzinnej; gdyby trzeba, reverse proxy może dostać cache statyk (B18).
