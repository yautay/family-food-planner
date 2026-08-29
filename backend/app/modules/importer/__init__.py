"""Importer PDF: staging, deterministyczny parser i mapowanie na katalog (ADR-011).

Moduł powstaje w BATCH_15 i niesie PIERWSZĄ połowę importera — od uploadu pliku
do zaparsowanego stagingu z sugestiami EXACT. Ekran review, rozstrzyganie porcji,
mapowania i zatwierdzanie (`resolve`/`approve`/`reject`) należą do BATCH_16.

Niezmiennik, którego ten moduł nie ma prawa złamać (02_DOMAIN §13.6):
**import niczego nie zapisuje do danych aplikacji przed APPROVED** — wszystko,
co powstaje w B15, mieszka wyłącznie w czterech tabelach stagingu.
"""
