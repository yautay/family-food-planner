# ADR-011 — Importer PDF: parser deterministyczny + AI tylko jako sugestia

Status: ACCEPTED (2026-08-16)

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
