"""Narzędzie `/pdf-extract` (BATCH_22, D31): jadłospis PDF → `spec.json` → paczka transferu.

Narzędzie deweloperskie POZA runtime aplikacji: `app/` nigdy go nie importuje
(kierunek zależności: skrypt → aplikacja; pilnuje tego test), a aplikacja nie dostaje
żadnej linii kodu importu PDF (D25/ADR-016). PDF czyta sesja agenta, nie ten pakiet.
"""
