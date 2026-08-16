# CLAUDE.md

**Faza projektu: BLUEPRINT — implementacja nie została rozpoczęta.**
Ten plik zostanie rozbudowany w BATCH_01 o kontrakt komend i kodu.

## Zasady obowiązujące już teraz

1. Implementację prowadzi się WYŁĄCZNIE batchami:
   `docs/implementation-plan/implementation_prompt.md` → procedura,
   `docs/implementation-plan/batches/` → karty, `PROGRESS.md` → statusy.
2. Architektura jest zaprojektowana (`docs/architecture/`, `docs/adr/`).
   Nie projektuj jej ponownie; konflikt rzeczywistości z dokumentem =
   pytanie do właściciela albo wpis w `02_DECISIONS.md`, nie cicha zmiana.
3. Decyzje właściciela: `docs/implementation-plan/02_DECISIONS.md`.
   Decyzja-bramka w statusie OPEN blokuje wskazany batch.
3a. Skille: karta batcha ma sekcję "Skills" — Required ładujesz na starcie
   sesji, Review uruchamiasz na diffie przed commitem. Manifest i mapa
   ID→skill: `docs/implementation-plan/03_AI_SKILLS.md`. Hierarchia przy
   konfliktach: właściciel > ADR/architektura > karta batcha > master
   prompt > CLAUDE.md > skille > ogólna wiedza. Skill NIGDY nie nadpisuje
   ADR (np. żadnego JWT, bo skill tak radzi — obowiązuje ADR-003).
4. Twarde zakazy (od pierwszej linii kodu):
   - float dla ilości/wartości odżywczych — zawsze Decimal/NUMERIC (ADR-008),
   - kopiowanie stanu serwera do Pinia — stan serwera żyje w TanStack Query (ADR-007),
   - endpoint zasobu bez testu macierzy uprawnień/scope (08_TESTING §4),
   - warstwa i18n — UI wyłącznie po polsku (D3, ADR-007),
   - sekrety w plikach śledzonych; `.env` nigdy w repo (07_SECURITY §7),
   - migracja z numerem „zarezerwowanym" — numer = pierwszy wolny,
     `down_revision` z `alembic heads` (ADR-002).
5. Jeden batch = jeden finalny commit `batch(XX): opis`; bez push.
6. Testy uruchamiaj realnie i raportuj faktyczne wyniki.
