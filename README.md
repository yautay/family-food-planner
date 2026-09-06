# Paśnik

Prywatna, rodzinna aplikacja do planowania żywienia: przepisy, kalorie
i makroskładniki (+ indeks/ładunek glikemiczny), plany dnia i tygodnia,
skalowanie porcji dla rodziny, spiżarnia, inteligentne listy zakupowe
(tury, opakowania, resztki, QR, linki publiczne), PWA z listą offline,
kopia danych rodziny do pliku i z powrotem.

**Stan: faza blueprint (2026-08-16). Implementacja nie została rozpoczęta.**

## Stack

Backend: Python 3.13 · FastAPI · SQLAlchemy 2 · Alembic · Pydantic v2 ·
PostgreSQL 17. Frontend: Vue 3 · TypeScript · Vite · Tailwind CSS ·
shadcn-vue · Pinia · TanStack Query. Testy: pytest · vitest · Playwright.
Deployment: Docker Compose na Odroid H2, za istniejącym reverse proxy.

## Jak zacząć implementację

1. Przeczytaj `docs/implementation-plan/implementation_prompt.md`.
2. Otwórz nową sesję Claude (Opus), wklej szablon z tego pliku, wskaż
   `docs/implementation-plan/batches/BATCH_01_PROJECT_SCAFFOLD_AND_DEV_LOOP.md`.
3. Status i kolejność batchy: `docs/implementation-plan/PROGRESS.md`
   i `docs/implementation-plan/00_MASTER_PLAN.md`.

## Mapa dokumentacji

```
docs/architecture/        01–09: przegląd, domena, DB, API, frontend, UX,
                          security, testy, deployment+backup
docs/adr/                 ADR-001…016 — trwałe decyzje techniczne
docs/implementation-plan/ master plan, rejestr decyzji (D), AI skills,
                          PROGRESS, master prompt, batches/
```
