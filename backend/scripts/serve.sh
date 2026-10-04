#!/bin/sh
# Paśnik — start aplikacji: JEDYNE źródło flag uvicorna (B18a, ADR-017 pkt 4).
#
# Wołają go dwa środowiska i żadne nie kopiuje flag:
#   * obraz prod  — `docker/entrypoint.sh` → `sh /app/scripts/serve.sh`,
#   * LXC         — `pasnik.service` → `/bin/sh .../current/backend/scripts/serve.sh`
#                   (PATH jednostki zaczyna się od `backend/.venv/bin`, więc
#                   `uvicorn` to ten z venv release'u).
#
# Plik leży w `backend/scripts/`, bo tylko ten katalog jedzie i do obrazu, i do
# release'u (rsync wyklucza `docker/` i `deploy/`).
#
# Dlaczego skrypt, a nie CMD w formie exec: liczba workerów i poziom logów mają
# przychodzić z env (09_DEPLOYMENT §2, karta B17 AC6), a exec-form CMD nie
# rozwija zmiennych. `exec` na końcu oddaje PID 1 uvicornowi, więc SIGTERM
# z `docker stop` trafia prosto w serwer (graceful shutdown, `stop_grace_period`).
#
# Zmienne (wszystkie opcjonalne):
#   PASNIK_VERSION_FILE  plik z wersją release'u (LXC: .../current/VERSION). Gdy
#                        ustawiony i czytelny, jego pierwsza linia staje się
#                        APP_VERSION — pole `version` w health = wdrożony release,
#                        a `pasnik.env` NIE niesie wersji (zmieniałaby się z każdym
#                        deployem, a plik powstaje raz). Obraz prod ustawia
#                        APP_VERSION sam i tej zmiennej nie używa.
#   UVICORN_WORKERS      liczba workerów (domyślnie 2 — 09_DEPLOYMENT §7)
#   LOG_LEVEL            poziom logów aplikacji I uvicorna (domyślnie INFO)
#   FORWARDED_ALLOW_IPS  adresy proxy, którym ufamy w X-Forwarded-For/-Proto;
#                        czyta je sam uvicorn (domyślnie 127.0.0.1). Za Caddym
#                        w compose połączenie przychodzi z bramy sieci dockera. W LXC
#                        (D29) to 192.168.2.121 — adres Caddy'ego; `*` jest
#                        ZABRONIONE (07_SECURITY §7).
#
# Migracji tu NIE MA (ADR-017 pkt 6): robi je hook deployu PRZED przełączeniem
# `current` (w obrazie testowym: `docker compose run --rm app alembic upgrade head`).
set -eu

: "${UVICORN_WORKERS:=2}"
: "${LOG_LEVEL:=INFO}"

if [ -n "${PASNIK_VERSION_FILE:-}" ] && [ -r "$PASNIK_VERSION_FILE" ]; then
    APP_VERSION=$(head -n 1 "$PASNIK_VERSION_FILE")
    export APP_VERSION
fi

# Aplikacja rozumie każdy poziom stdlib (`WARN`, `FATAL`…), uvicorn tylko
# critical|error|warning|info|debug|trace — nieznana wartość to natychmiastowy
# exit i pętla restartów. Mapujemy synonimy, reszta spada do `info`.
case "$(printf '%s' "$LOG_LEVEL" | tr '[:upper:]' '[:lower:]')" in
    critical|fatal) uvicorn_level=critical ;;
    error) uvicorn_level=error ;;
    warning|warn) uvicorn_level=warning ;;
    debug) uvicorn_level=debug ;;
    trace) uvicorn_level=trace ;;
    *) uvicorn_level=info ;;
esac

# --timeout-worker-healthcheck: supervisor uvicorna pinguje workery i ZABIJA te,
# które nie odpowiedzą w czasie (domyślnie 5 s), a worker importujący aplikację
# (SQLAlchemy, Pillow) na obciążonym albo wolnym CPU (Odroid) potrafi
# tyle nie odpowiadać. Objaw z drilla B17: pętla „Child process [n] died" bez
# tracebacku. 30 s to zapas, nie tolerancja na zawieszony proces.
exec uvicorn app.main:create_app --factory \
    --host 0.0.0.0 --port 8000 \
    --workers "$UVICORN_WORKERS" \
    --timeout-worker-healthcheck "${UVICORN_WORKER_HEALTHCHECK_S:-30}" \
    --proxy-headers \
    --log-level "$uvicorn_level" \
    --no-server-header
