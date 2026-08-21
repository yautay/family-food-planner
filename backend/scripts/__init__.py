"""Skrypty operacyjne uruchamiane przez Taskfile (`python -m scripts.<nazwa>`).

Katalog jest PAKIETEM, a nie zbiorem luźnych plików, od BATCH_10: snapshot
silnika zakupowego importuje stałe seedu demo (`scripts.seed_demo`), żeby dane
testu i dane komendy `task db-seed-demo` nie istniały w repo dwa razy. Bez tego
pliku mypy widzi ten sam plik pod dwiema nazwami modułu (`seed_demo`
i `scripts.seed_demo`) i przerywa sprawdzanie.
"""
