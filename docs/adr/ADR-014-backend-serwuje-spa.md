# ADR-014 — Backend serwuje SPA i uploady; jeden kontener aplikacyjny

Status: ACCEPTED (2026-08-16)

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
