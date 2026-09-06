# ADR-011 — Importer PDF: parser deterministyczny + AI tylko jako sugestia

Status: SUPERSEDED przez ADR-016 (2026-09-06)

> Importer PDF został wycofany w całości decyzją właściciela **D25** i usunięty
> z kodu w BATCH_20. Treść poniżej zostaje jako zapis, na czym stała ta decyzja
> — nie opisuje stanu aplikacji.

## Kontekst
8 PDF-ów dietetyczki ma stabilną, zmierzoną strukturę (01_PDF_AUDIT), ale
zawiera anomalie wymagające człowieka (porcje, mapowanie nazw). Właściciel
zezwolił (2026-08-16) na wysyłanie treści PDF do Claude API.

## Decyzja
- Ekstrakcja: pdfplumber; parsing: deterministyczna maszyna stanów wg
  kontraktu 01_PDF_AUDIT (regexy, sumy kontrolne dnia).
- AI (Claude API, model konfigurowany w env, klucz server-side): wyłącznie
  propozycje — mapowanie nazw na produkty kanoniczne, wykrywanie duplikatów
  przepisów, opis anomalii. Wynik AI zawsze `match_kind=ai` + confidence,
  wymaga zatwierdzenia w review.
- Staging area (import_jobs/staged_*/import_issues — 03_DATABASE §9);
  do danych aplikacji trafia wyłącznie stan APPROVED; issues `blocker`
  (nieznana liczba porcji, niezmapowany produkt) blokują zatwierdzenie.
- Wartości odżywcze z PDF zapisywane jako metadane walidacyjne — prawdą
  są wartości wyliczane z produktów kanonicznych; rozjazd >10% ⇒ issue.
- Brak klucza API ⇒ importer działa w trybie czysto deterministycznym
  (AI to enhancement, nie zależność).

## Konsekwencje
+ Import powtarzalny i testowalny na realnym korpusie (8 plików + referencja
  prototype.db); AI nie może zepsuć danych kanonicznych.
− Ekran review jest niebanalny — dostaje własny batch (BATCH_16).

## Stan faktyczny (BATCH_15 + BATCH_16, 2026-08-29)

Decyzja wdrożona w całości. Cztery doprecyzowania, które wyszły z implementacji:

1. **Brak klucza to 503, nie 404 i nie 500.** `POST /import/jobs/{id}/ai-suggest`
   odpowiada `service_unavailable` z komunikatem po polsku; `GET .../staged`
   niesie `ai_available`, po którym UI chowa przyciski AI. Reszta flow —
   mapowania, porcje, scalenia, zatwierdzenie — działa bez zmian.
2. **Granica danych wysyłanych do modelu ma jedno miejsce w kodzie**:
   `importer/ai_assist.py` (funkcje `build_*_prompt`). Do Claude API idą
   wyłącznie surowe nazwy z PDF-a, nazwy dań, treść przygotowania i nazwy
   produktów z GLOBALNEGO katalogu — nigdy e-maile, rodziny ani identyfikatory
   kont. Pilnuje tego test, który czyta DOSŁOWNIE wysłane żądania.
3. **Odpowiedź niezgodna z kontraktem jest odrzucana po cichu**, nie kończy się
   błędem serwera: filtry odsiewają nazwę, o którą nie pytano, produkt spoza
   listy kandydatów i pewność poniżej progu 0,5.
4. **Model i limity są w env** (`ANTHROPIC_MODEL`, `ANTHROPIC_MAX_TOKENS`,
   `ANTHROPIC_TIMEOUT_S`), a `temperature` NIE jest wysyłana — parametry
   losowości zostały usunięte z API bieżących modeli i ich podanie kończy się
   błędem 400. Powtarzalność bierze się z wymuszonego schematu odpowiedzi
   i z tego, że każdą propozycję zatwierdza człowiek.
