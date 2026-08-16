# ADR-005 — Normalizacja jednostek do g/ml/szt; przeliczniki własnością produktu

Status: ACCEPTED (2026-08-16)

## Kontekst
Audyt PDF (01_PDF_AUDIT §5.2): ta sama jednostka domowa („łyżka", „sztuka",
„plaster") ma różną gramaturę zależnie od produktu, a nawet per wystąpienie
(jajko 50/60 g, łyżka mąki 5/12/15 g). Uniwersalna tabela przeliczników
jest niemożliwa.

## Decyzja
- Ilości przechowywane znormalizowane: masa → g, objętość → ml, sztuki →
  szt. z wagą sztuki produktu (`piece_weight_g`).
- Jednostki domowe = `product_unit_weights` per produkt (etykieta →
  gramy/jednostkę, source, samples_count); uczone z próbek importu
  (mediana), edytowalne przez użytkownika przy produkcie.
- Zapis ilości nieprzeliczalnej jednoznacznie jest odrzucany na poziomie
  serwisu — w danych nie istnieje ilość bez reprezentacji g/ml/szt.
- UI: wpis w dowolnej jednostce produktu, prezentacja ≥1000 g w kg
  (formatter, dane zawsze w g).

## Konsekwencje
+ Agregacja zakupowa i nutrition działają na jednej osi ilości.
− Dodanie składnika z nową jednostką domową wymaga podania gramatury
  (jednorazowo per produkt) — świadomy koszt poprawności.
