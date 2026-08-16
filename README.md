# Family Food Planner

Prywatna, rodzinna aplikacja do planowania żywienia: przepisy, kalorie
i makroskładniki (+ indeks/ładunek glikemiczny), plany dnia i tygodnia,
skalowanie porcji dla rodziny, spiżarnia, inteligentne listy zakupowe
(tury, opakowania, resztki, QR, linki publiczne), PWA z listą offline,
import planów żywieniowych z PDF.

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
docs/adr/                 ADR-001…014 — trwałe decyzje techniczne
docs/implementation-plan/ master plan, audyt PDF, rejestr decyzji (D),
                          AI skills, PROGRESS, master prompt, batches/
data/source_pdfs/         8 PDF-ów dietetyczki (wejście importera + testy)
data/reference/           prototype.db — referencja walidacyjna importera
                          (dane z poprzedniego prototypu; NIE seed)
```
