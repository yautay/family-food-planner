#!/usr/bin/env bash
# Paśnik — restore: dump bazy (pg_restore) + katalog uploadów (09_DEPLOYMENT §3).
#
# Nieinteraktywny, parametry jawne — B18 wkleja go do runbooka:
#   restore.sh <plik.dump> [<plik-uploads.tar.gz>] [--wipe-uploads]
#
#   Nazwy BEZ katalogu są szukane w BACKUP_DIR (domyślnie /backups) — dzięki temu
#   z hosta nie trzeba podawać ścieżek absolutnych kontenera (Git Bash na Windows
#   przepisuje `/backups/x` na ścieżkę hosta, zanim docker cokolwiek zobaczy).
#
#   <plik.dump>            zestaw z backup.sh (pg_dump -Fc); jeśli obok leży
#                          `pasnik-<stempel>.sha256`, sumy są SPRAWDZANE przed
#                          restore — uszkodzony backup ma paść tu, nie po godzinie
#   <plik-uploads.tar.gz>  (opcjonalnie) archiwum uploadów do rozpakowania w UPLOADS_DIR
#   --wipe-uploads         najpierw wyczyść UPLOADS_DIR (restore „na czysto";
#                          domyślnie pliki są DOKŁADANE — istniejące zostają)
#
# Env: PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE (libpq), UPLOADS_DIR (/data/uploads).
#
# Baza: `--clean --if-exists` — działa zarówno na świeżej bazie (DROP IF EXISTS
# jest no-opem), jak i na bazie z zawartością (obiekty są podmieniane). Aplikacja
# MUSI być w tym czasie zatrzymana (`docker compose stop app`): otwarte sesje
# blokują DROP TABLE. `alembic_version` jest w dumpie, więc po restore schemat
# jest w wersji z chwili backupu — `alembic upgrade head` (jawny krok runbooku)
# domiga do wersji obrazu, idempotentnie.
#
# Skrypt nie loguje connection stringów ani haseł; kod wyjścia ≠ 0 przy każdym błędzie.
set -euo pipefail

: "${UPLOADS_DIR:=/data/uploads}"
: "${BACKUP_DIR:=/backups}"
: "${PGDATABASE:?ustaw PGDATABASE}"
: "${PGHOST:?ustaw PGHOST}"

log() { printf '%s restore: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "BŁĄD: $*"; exit 1; }

# Goła nazwa pliku → plik w BACKUP_DIR; ścieżka z katalogiem zostaje jak jest.
in_backup_dir() { case "$1" in */*) printf '%s' "$1" ;; *) printf '%s/%s' "$BACKUP_DIR" "$1" ;; esac; }

dump=""
uploads_tar=""
wipe=0
for arg in "$@"; do
    case "$arg" in
        --wipe-uploads) wipe=1 ;;
        *.dump) dump=$(in_backup_dir "$arg") ;;
        *.tar.gz) uploads_tar=$(in_backup_dir "$arg") ;;
        *) die "nieznany argument: $arg (użycie: restore.sh <plik.dump> [<uploads.tar.gz>] [--wipe-uploads])" ;;
    esac
done
[ -n "$dump" ] || die "podaj plik dumpu (pasnik-<stempel>.dump)"
[ -r "$dump" ] || die "plik dumpu nieczytelny: $dump"
[ -z "$uploads_tar" ] || [ -r "$uploads_tar" ] || die "archiwum uploadów nieczytelne: $uploads_tar"

started=$(date +%s)

# --- 0. sumy kontrolne (jeśli zestaw je ma) -----------------------------------
sums="${dump%.dump}.sha256"
if [ -r "$sums" ]; then
    # --ignore-missing: zestaw mógł mieć `.env`, którego operator świadomie nie
    # skopiował na docelowy host — brak pliku to nie uszkodzenie.
    (cd "$(dirname "$dump")" && sha256sum --check --quiet --ignore-missing "$(basename "$sums")") \
        || die "sumy kontrolne zestawu NIE zgadzają się — backup uszkodzony"
    log "sumy kontrolne zgodne"
else
    log "UWAGA: brak pliku sum kontrolnych obok dumpu — pomijam weryfikację"
fi

# --- 1. baza ------------------------------------------------------------------
log "pg_restore do bazy $PGDATABASE z $(basename "$dump")"
pg_restore --clean --if-exists --no-owner --no-privileges --exit-on-error \
    --dbname="$PGDATABASE" "$dump" \
    || die "pg_restore nie powiódł się"
version=$(psql --tuples-only --no-align --command='SELECT version_num FROM alembic_version' 2>/dev/null || true)
log "baza odtworzona; alembic_version = ${version:-brak}"

# --- 2. uploady --------------------------------------------------------------
if [ -n "$uploads_tar" ]; then
    mkdir -p "$UPLOADS_DIR"
    if [ "$wipe" = 1 ]; then
        find "$UPLOADS_DIR" -mindepth 1 -delete
        log "katalog uploadów wyczyszczony (--wipe-uploads)"
    fi
    tar --extract --gzip --file="$uploads_tar" --directory="$UPLOADS_DIR" \
        || die "rozpakowanie uploadów nie powiodło się"
    log "uploady odtworzone: $(find "$UPLOADS_DIR" -type f | wc -l) plików, $(du -sh "$UPLOADS_DIR" | cut -f1)"
else
    log "archiwum uploadów nie podane — katalog uploadów nietknięty"
fi

log "koniec po $(( $(date +%s) - started )) s. Następny krok runbooku: alembic upgrade head, potem start app i smoke."
