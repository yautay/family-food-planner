# Architecture Decision Records

Rejestr trwałych decyzji architektonicznych. Cel: żadna kolejna sesja AI
nie podejmuje ponownie decyzji już rozstrzygniętej.

Zasady:
- Status: `ACCEPTED` | `SUPERSEDED przez ADR-xxx`. ADR-ów nie edytuje się
  merytorycznie po akceptacji — zmiana decyzji = nowy ADR z odniesieniem.
- Nowy ADR powstaje, gdy batch podejmuje decyzję o trwałych konsekwencjach
  (wykracza poza batch). Numer = pierwszy wolny.
- Decyzje PRODUKTOWE właściciela żyją w
  `docs/implementation-plan/02_DECISIONS.md` (rejestr D-numerowany);
  ADR-y to decyzje TECHNICZNE.

| ADR | Tytuł |
|---|---|
| 001 | Modularny monolit FastAPI, bez workerów i kolejek |
| 002 | ~~PostgreSQL w Dockerze, dane na bind mounts, Alembic~~ (SUPERSEDED przez 017) |
| 003 | Sesje server-side + cookie, argon2id, bez JWT i samorejestracji |
| 004 | Model wartości odżywczych: kolumny rdzenia + rejestr nutrients |
| 005 | Normalizacja jednostek do g/ml/szt; przeliczniki własnością produktu |
| 006 | Scope PRIVATE/HOUSEHOLD; jeden household na użytkownika |
| 007 | shadcn-vue + TanStack Query; Pinia tylko dla stanu UI; bez i18n |
| 008 | Silniki nutrition i shopping jako czyste funkcje na Decimal |
| 009 | PWA offline: IndexedDB + kolejka synchronizacji checkboxów |
| 010 | Publiczne linki list: token 256-bit, expiry, revoke, zero PII |
| 011 | ~~Importer PDF: parser deterministyczny + AI jako sugestia~~ (SUPERSEDED przez 016) |
| 012 | Usuwanie: blokada przy referencjach + archiwizacja, bez soft delete |
| 013 | Wykresy: własne prymitywy SVG, bez biblioteki wykresów |
| 014 | Backend serwuje SPA i uploady; jeden kontener aplikacyjny |
| 015 | Dostęp do bazy asynchronicznie: SQLAlchemy async + psycopg 3 |
| 016 | Transfer jedynym importem/eksportem; importer PDF wycofany |
| 017 | Produkcja w LXC przez ansistrano; PostgreSQL we współdzielonym klastrze |
| 018 | Prywatna lista offline: lokalny scope, generacje odpowiedzi i izolacja cache |
