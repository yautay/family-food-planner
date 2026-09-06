#!/usr/bin/env bash
# Paśnik — backup: dump bazy (pg_dump -Fc) + archiwum uploadów + opcjonalnie
# kopia pliku env + sumy kontrolne + prune retencji (09_DEPLOYMENT §3).
#
# Uruchamiany w kontenerze `backup` (docker/backup/Dockerfile): raz dziennie
# przez cron-loop.sh albo ręcznie: `task backup` / `docker compose run --rm backup backup`.
#
# Wejście — wyłącznie env (07_SECURITY §7); NIC z tego nie jest logowane:
#   PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE   standardowe zmienne libpq
#   BACKUP_DIR       katalog docelowy (domyślnie /backups)
#   UPLOADS_DIR      katalog uploadów do spakowania (domyślnie /data/uploads)
#   BACKUP_ENV_FILE  (opcjonalnie) ścieżka pliku env do włączenia w zestaw —
#                    domyślnie PUSTA: env żyje na hoście (B18) i dev/test go nie kopiują
#   BACKUP_KEEP_DAILY / BACKUP_KEEP_WEEKLY   retencja (domyślnie 7 / 4)
#
# Zestaw = wspólny stempel UTC w nazwach:
#   pasnik-<stempel>.dump            pg_dump -Fc (custom), --no-owner --no-privileges
#   pasnik-<stempel>-uploads.tar.gz  katalog uploadów BEZ scratcha `transfer/` (TTL 24 h)
#   pasnik-<stempel>.env             tylko gdy BACKUP_ENV_FILE ustawione
#   pasnik-<stempel>.sha256          sumy kontrolne powyższych
# Pliki powstają pod nazwą `.tmp` i są przenoszone dopiero po sukcesie — prune
# i restore nigdy nie zobaczą połowicznego zestawu. umask 077 ⇒ uprawnienia 600
# (backup to komplet danych rodziny — traktowany jak sekret, karta B17 §Security).
#
# Kod wyjścia ≠ 0 przy KAŻDYM niepowodzeniu — cron-loop loguje go na stdout,
# a `docker logs backup` jest jedynym alarmem (09 §6).
set -euo pipefail

: "${BACKUP_DIR:=/backups}"
: "${UPLOADS_DIR:=/data/uploads}"
: "${BACKUP_ENV_FILE:=}"
: "${BACKUP_KEEP_DAILY:=7}"
: "${BACKUP_KEEP_WEEKLY:=4}"
: "${PGDATABASE:?ustaw PGDATABASE}"
: "${PGHOST:?ustaw PGHOST}"

PRUNE=${PRUNE_SCRIPT:-/opt/backup/prune.py}

log() { printf '%s backup: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "BŁĄD: $*"; exit 1; }

umask 077
mkdir -p "$BACKUP_DIR" || die "nie mogę utworzyć $BACKUP_DIR"

stamp=$(date -u +%Y%m%dT%H%M%SZ)
base="$BACKUP_DIR/pasnik-$stamp"
started=$(date +%s)
log "start zestawu $stamp (baza: $PGDATABASE, uploady: $UPLOADS_DIR)"

# --- 1. baza ------------------------------------------------------------------
# --no-owner/--no-privileges: restore ma działać niezależnie od nazwy roli
# na docelowej instancji (09 §3: „przywraca do wskazanego środowiska").
pg_dump --format=custom --no-owner --no-privileges --file="$base.dump.tmp" \
    || die "pg_dump nie powiódł się"
mv "$base.dump.tmp" "$base.dump"
log "dump gotowy: $(du -h "$base.dump" | cut -f1)"

# --- 2. uploady --------------------------------------------------------------
# `transfer/` to scratch paczek eksportu/importu z TTL 24 h — nie jest danymi.
if [ -d "$UPLOADS_DIR" ]; then
    tar --create --gzip --file="$base-uploads.tar.gz.tmp" \
        --directory="$UPLOADS_DIR" --exclude='./transfer' --exclude='./transfer/*' . \
        || die "archiwizacja uploadów nie powiodła się"
else
    log "UWAGA: katalog uploadów nie istnieje — archiwum będzie puste"
    tar --create --gzip --file="$base-uploads.tar.gz.tmp" --files-from=/dev/null
fi
mv "$base-uploads.tar.gz.tmp" "$base-uploads.tar.gz"
log "uploady spakowane: $(du -h "$base-uploads.tar.gz" | cut -f1); zajętość katalogu: $(du -sh "$UPLOADS_DIR" 2>/dev/null | cut -f1 || echo 'n/d')"

# --- 3. env (opcjonalnie) -----------------------------------------------------
if [ -n "$BACKUP_ENV_FILE" ]; then
    [ -r "$BACKUP_ENV_FILE" ] || die "BACKUP_ENV_FILE wskazuje nieczytelny plik"
    cp "$BACKUP_ENV_FILE" "$base.env"
    chmod 600 "$base.env"
    log "kopia pliku env dołączona"
fi

# --- 4. sumy kontrolne -------------------------------------------------------
(cd "$BACKUP_DIR" && sha256sum "$(basename "$base.dump")" "$(basename "$base-uploads.tar.gz")" \
    $( [ -f "$base.env" ] && basename "$base.env" ) > "$(basename "$base.sha256")") \
    || die "sha256sum nie powiódł się"

# --- 5. retencja --------------------------------------------------------------
python3 "$PRUNE" --dir "$BACKUP_DIR" --keep-daily "$BACKUP_KEEP_DAILY" --keep-weekly "$BACKUP_KEEP_WEEKLY" \
    || die "prune retencji nie powiódł się"

log "koniec zestawu $stamp po $(( $(date +%s) - started )) s; katalog backupów: $(du -sh "$BACKUP_DIR" | cut -f1)"
