"""Limity tempa endpointów UPLOADU (ustalenie REVIEW R4 pkt 3, karta B17).

Limit rozmiaru (`core/body_limit.py`, `save_image`, limit paczki transferu) i limit
częstości to dwie połowy tej samej ochrony: pojedynczy plik nie przekroczy
sufitu, a ich strumień nie zapełni dysku Odroida pętlą `curl` z przejętej sesji
(07_SECURITY §1 i §6). Limity logowania i ścieżki publicznej mieszkają przy
swoich routerach (`accounts/router.py`, `shopping/public_router.py`), bo mają
inne uzasadnienie (anty-enumeracja, skanowanie tokenów).

Licznik slowapi jest per PROCES: przy `UVICORN_WORKERS=2` realny sufit to
dwukrotność wartości (09_DEPLOYMENT §2) — wartości niżej to uwzględniają.
"""

from __future__ import annotations

#: Zdjęcia przepisów i wariantów sklepowych (≤ 10 MB każde). Człowiek dodaje
#: kilka zdjęć na minutę; 30 to zapas na wgrywanie serii po powrocie z zakupów.
PHOTO_UPLOAD_RATE_LIMIT = "30/minute"

#: Duże pliki: paczka transferu (≤ 100 MB). Kopię danych rodziny wczytuje się
#: kilka razy w roku; E2E wgrywa 3 paczki na przebieg.
FILE_UPLOAD_RATE_LIMIT = "10/minute"
