# ADR-001 — Modularny monolit FastAPI, bez workerów i kolejek

Status: ACCEPTED (2026-08-16)

## Kontekst
Aplikacja domowa: kilku użytkowników, jeden mały serwer (Odroid H2),
priorytety: prostota, utrzymywalność, łatwy deployment i backup.

## Decyzja
Jeden proces FastAPI z modułami domenowymi (accounts, households, catalog,
recipes, nutrition, planning, pantry, shopping, importer, transfer, audit)
jako pakietami Pythona. Warstwy w module: router → service → models; moduły
komunikują się wyłącznie przez serwisy. Zero mikroserwisów, zero Redis,
zero Celery — operacje „ciężkie" (parsing PDF, eksport) wykonywane
synchronicznie z limitem czasu lub w wątku.

## Konsekwencje
+ Jeden obraz, jeden deployment, trywialny backup, spójne transakcje.
− Import bardzo dużego PDF blokuje request na sekundy — akceptowane
  (pojedynczy użytkownik-importer); gdyby przestało wystarczać, pierwszy
  krok to BackgroundTasks/wątek, nie kolejka.
Granice modułów utrzymywane dyscypliną code review (Review batche
sprawdzają zależności między modułami).
