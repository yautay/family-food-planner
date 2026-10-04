#!/usr/bin/env bash
# Paśnik — „cron" kontenera backupu: raz na dobę o BACKUP_AT uruchamia backup.sh.
#
# Dlaczego pętla ze `sleep`, a nie crond (decyzja implementującego, karta B17
# §Implementation Notes): (1) crond w obrazie `postgres:16` to dodatkowy pakiet
# i dodatkowy proces-demon, który NIE przekazuje wyjścia zadań na stdout
# kontenera bez obejść (`> /proc/1/fd/1`), a 09 §6 wymaga logów w `docker logs`;
# (2) crond gubi zmienne środowiskowe kontenera (PG*, BACKUP_*), które są tu
# jedynym źródłem konfiguracji; (3) pętla jest ~20 linii i widać w niej wszystko.
#
# Env: BACKUP_AT (HH:MM w strefie TZ kontenera, domyślnie 03:00), TZ (opcjonalnie).
# SIGTERM (docker stop) przerywa oczekiwanie i kończy pętlę — trwający backup
# dobiega końca (trap nie zabija dziecka), więc `stop_grace_period` ma być
# dłuższy niż typowy czas backupu.
set -euo pipefail

: "${BACKUP_AT:=03:00}"
BACKUP_SCRIPT=${BACKUP_SCRIPT:-/opt/backup/backup.sh}

log() { printf '%s cron: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

running=1
trap 'running=0; log "SIGTERM — kończę pętlę po bieżącym kroku"' TERM INT

seconds_until_next() {
    local now next
    now=$(date +%s)
    next=$(date -d "today $BACKUP_AT" +%s)
    if [ "$next" -le "$now" ]; then
        next=$(date -d "tomorrow $BACKUP_AT" +%s)
    fi
    echo $(( next - now ))
}

log "start; codzienny backup o $BACKUP_AT (${TZ:-UTC})"
while [ "$running" = 1 ]; do
    wait_s=$(seconds_until_next)
    log "następny backup za ${wait_s} s"
    # `sleep` w tle + `wait`: trap TERM przerywa oczekiwanie natychmiast,
    # a nie dopiero po upływie pełnego `sleep`.
    sleep "$wait_s" &
    wait $! || true
    [ "$running" = 1 ] || break
    if "$BACKUP_SCRIPT"; then
        log "backup zakończony poprawnie"
    else
        log "BŁĄD: backup zakończony kodem $? — sprawdź komunikaty wyżej"
    fi
done
log "zatrzymany"
