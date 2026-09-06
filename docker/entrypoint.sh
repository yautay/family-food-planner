#!/bin/sh
# Paśnik — start aplikacji w obrazie prod (docker/Dockerfile, target `prod`).
#
# Dlaczego skrypt, a nie CMD w formie exec: liczba workerów i poziom logów mają
# przychodzić z env (09_DEPLOYMENT §2, karta B17 AC6), a exec-form CMD nie
# rozwija zmiennych. `exec` na końcu oddaje PID 1 uvicornowi, więc SIGTERM
# z `docker stop` trafia prosto w serwer (graceful shutdown, `stop_grace_period`).
#
# Zmienne (wszystkie opcjonalne):
#   UVICORN_WORKERS      liczba workerów (domyślnie 2 — 09_DEPLOYMENT §7)
#   LOG_LEVEL            poziom logów aplikacji I uvicorna (domyślnie INFO)
#   FORWARDED_ALLOW_IPS  adresy proxy, którym ufamy w X-Forwarded-For/-Proto;
#                        czyta je sam uvicorn (domyślnie 127.0.0.1). Za Caddym
#                        w compose połączenie przychodzi z bramy sieci dockera,
#                        więc B18 ustawia tu tę bramę albo `*` — port aplikacji
#                        jest opublikowany WYŁĄCZNIE na 127.0.0.1 hosta.
#
# Migracji tu NIE MA (ADR-002): `docker compose run --rm app alembic upgrade head`
# jest jawnym krokiem procedury update.
set -eu

: "${UVICORN_WORKERS:=2}"
: "${LOG_LEVEL:=INFO}"

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
