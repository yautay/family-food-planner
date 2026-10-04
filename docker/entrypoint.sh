#!/bin/sh
# Paśnik — start aplikacji w obrazie prod (docker/Dockerfile, target `prod`).
#
# Flagi uvicorna, mapowanie LOG_LEVEL i opis zmiennych mieszkają w JEDNYM miejscu:
# `backend/scripts/serve.sh` (kopiowany do obrazu jako /app/scripts/serve.sh).
# Wołają je dwa środowiska — ten obraz i LXC (`pasnik.service`, B18a, ADR-017
# pkt 4) — więc rozjazd flag między dev-testem a produkcją jest niemożliwy.
# `exec` oddaje PID 1 skryptowi, a ten przez `exec` uvicornowi: SIGTERM
# z `docker stop` trafia prosto w serwer (graceful shutdown).
set -eu
exec sh /app/scripts/serve.sh
