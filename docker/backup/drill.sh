#!/usr/bin/env bash
# Paśnik — DRILL round-tripu backup → zniszczenie środowiska → restore → smoke
# (karta BATCH_17 §Tests: „wykonany REALNIE na compose testowym"; `task backup-drill`).
#
# Scenariusz (09_DEPLOYMENT §3, restore wg runbooka B18):
#   0. czysty stack testowy (down -v)
#   1. db → alembic upgrade head → create-admin → seed demo → app → health ok
#   2. dane, których seed nie ma: zdjęcie przepisu przez API (uploady w tarze)
#   3. liczności kluczowych tabel + liczba plików uploadów PRZED
#   4. backup (kontener `backup`) → zestaw w PASNIK_TEST_BACKUPS_DIR
#   5. `down -v` — baza i uploady ZNIKAJĄ (wolumeny nazwane)
#   6. db → restore (pg_restore + tar) → alembic upgrade head (idempotentnie) → app
#   7. liczności PO == PRZED; smoke API: health ok, login, przepisy, plan tygodnia
#      demo, listy zakupowe, zdjęcie przepisu (200)
#
# Zmienne przychodzą ze środowiska — `task backup-drill` wstrzykuje .env przez
# `dotenv:` Taskfile'a (skrypt ŚWIADOMIE nie robi `. ./.env`: to plik dotenv,
# nie skrypt shella — hasło z `&` czy `$` bash by wykonał albo uciął).
# Wymagane: E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD (konto smoke — stack testowy jest
# efemeryczny, więc to jedyne hasło, jakie repo zna z env), PASNIK_TEST_BACKUPS_DIR
# (KATALOG HOSTA — backupy muszą przeżyć `down -v`; eksportuj w shellu przed
# `task backup-drill` albo wpisz do .env).
# Wymagane na hoście: docker, curl, python (parsowanie JSON), bash.
# Obraz: `task build-prod` wcześniej.
set -euo pipefail
cd "$(dirname "$0")/../.."
# Git Bash (MSYS) zamienia argumenty wyglądające jak ścieżki POSIX (`/backups/x`)
# na ścieżki Windows PRZED przekazaniem do dockera — restore dostawałby
# `C:/Program Files/Git/backups/x`. Na Linuksie zmienne są ignorowane.
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'

: "${PASNIK_TEST_BACKUPS_DIR:?ustaw PASNIK_TEST_BACKUPS_DIR — katalog hosta na backupy drilla}"
: "${E2E_ADMIN_EMAIL:?ustaw E2E_ADMIN_EMAIL}"
: "${E2E_ADMIN_PASSWORD:?ustaw E2E_ADMIN_PASSWORD}"
: "${PASNIK_TEST_PORT:=8081}"
: "${POSTGRES_USER:=pasnik}"
: "${POSTGRES_DB:=pasnik}"
export PASNIK_TEST_BACKUPS_DIR
COMPOSE="docker compose --env-file .env -f docker/compose.test.yml"
BASE="http://127.0.0.1:${PASNIK_TEST_PORT}"
API="$BASE/api/v1"
TABLES="users households canonical_products product_unit_weights retail_products stores recipes recipe_ingredients plan_days plan_meals plan_meal_items week_templates shopping_round_configs shopping_generations shopping_lists shopping_list_items pantry_items audit_entries"

t0=$(date +%s)
log() { printf '\n[%4ds] === %s\n' "$(( $(date +%s) - t0 ))" "$*"; }
die() { printf 'DRILL: BŁĄD: %s\n' "$*" >&2; exit 1; }
# Windows/Git Bash: `python3` bywa stubem Microsoft Store („nie znaleziono
# Python") — wybieramy pierwszy interpreter, który naprawdę działa.
PYTHON=""
for candidate in python3 python; do
    if "$candidate" -c 'pass' >/dev/null 2>&1; then PYTHON="$candidate"; break; fi
done
[ -n "$PYTHON" ] || die "brak działającego interpretera Pythona (python3/python) na hoście"
py() { "$PYTHON" -c "$@"; }

wait_health() {
    local expected="$1" i body
    for i in $(seq 1 60); do
        body=$(curl -fsS "$API/health" 2>/dev/null || true)
        if [ -n "$body" ] && py "import json,sys; sys.exit(0 if json.loads(sys.argv[1])['status']=='$expected' else 1)" "$body"; then
            echo "health: $body"; return 0
        fi
        sleep 2
    done
    die "health nie osiągnął statusu '$expected' w 120 s (ostatnia odpowiedź: ${body:-brak})"
}

counts() {
    local out="" t n
    for t in $TABLES; do
        n=$($COMPOSE exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "SELECT count(*) FROM $t")
        out+="$t=$n "
    done
    echo "$out"
}

uploads_count() {
    $COMPOSE --profile backup run --rm --no-deps backup bash -c 'find /data/uploads -type f -not -path "*/transfer/*" | wc -l' | tr -d '\r' | grep -oE '^[0-9]+$' | tail -1
}

# Login w prod: cookies mają `Secure` + `__Host-`, a stack testowy jedzie po http —
# curl NIE odsyła cookie Secure po http, więc przepisujemy je ręcznie do nagłówka.
login() {
    local headers
    headers=$(curl -sS -D - -o /dev/null -H 'Content-Type: application/json' \
        -d "{\"email\":\"$E2E_ADMIN_EMAIL\",\"password\":\"$E2E_ADMIN_PASSWORD\"}" "$API/auth/login")
    SESSION=$(printf '%s' "$headers" | grep -i '^set-cookie: __Host-pasnik_session=' | sed 's/^[Ss]et-[Cc]ookie: //; s/;.*//' | tr -d '\r')
    CSRF=$(printf '%s' "$headers" | grep -i '^set-cookie: __Host-csrf_token=' | sed 's/^[Ss]et-[Cc]ookie: //; s/;.*//' | tr -d '\r')
    [ -n "$SESSION" ] && [ -n "$CSRF" ] || die "logowanie nie dało cookies __Host- (nagłówki: $(printf '%s' "$headers" | head -c 400))"
    COOKIE="$SESSION; $CSRF"
    CSRF_TOKEN=${CSRF#*=}
}
api_get() { curl -fsS -H "Cookie: $COOKIE" "$API$1"; }

log "0. czysty stack testowy"
$COMPOSE --profile backup down -v --remove-orphans >/dev/null 2>&1 || true
mkdir -p "$PASNIK_TEST_BACKUPS_DIR"

log "1. db → migracje → admin → seed demo → app"
$COMPOSE up -d db
$COMPOSE run --rm app alembic upgrade head | tail -1
$COMPOSE run --rm -e PASNIK_ADMIN_EMAIL="$E2E_ADMIN_EMAIL" -e PASNIK_ADMIN_PASSWORD="$E2E_ADMIN_PASSWORD" app python -m app.cli create-admin
$COMPOSE run --rm app python -m scripts.seed_demo | tail -3
$COMPOSE up -d app
wait_health ok

log "2. zdjęcie przepisu przez API (dane poza seedem)"
login
RECIPE_ID=$(api_get "/recipes?limit=1" | py "import json,sys; print(json.load(sys.stdin)['items'][0]['id'])")
curl -fsS -o /dev/null -X POST -H "Cookie: $COOKIE" -H "X-CSRF-Token: $CSRF_TOKEN" \
    -F "file=@frontend/public/icons/icon-512.png;type=image/png" "$API/recipes/$RECIPE_ID/photo"
PHOTO_URL=$(api_get "/recipes/$RECIPE_ID" | py "import json,sys; print(json.load(sys.stdin)['photo_url'])")
echo "zdjęcie: $PHOTO_URL"

log "3. liczności PRZED"
BEFORE=$(counts); echo "$BEFORE"
UPLOADS_BEFORE=$(uploads_count); echo "plików uploadów (bez scratcha): $UPLOADS_BEFORE"

log "4. backup"
tb=$(date +%s)
$COMPOSE --profile backup run --rm backup backup
echo "czas backupu: $(( $(date +%s) - tb )) s"
ls -la "$PASNIK_TEST_BACKUPS_DIR"
DUMP=$(ls -t "$PASNIK_TEST_BACKUPS_DIR"/pasnik-*.dump | head -1); DUMP=$(basename "$DUMP")
TAR="${DUMP%.dump}-uploads.tar.gz"
[ -f "$PASNIK_TEST_BACKUPS_DIR/$TAR" ] || die "brak archiwum uploadów $TAR"

log "5. ZNISZCZENIE środowiska (down -v)"
$COMPOSE --profile backup down -v --remove-orphans
docker volume ls --format '{{.Name}}' | grep -q '^pasnik-test_' && die "wolumeny pasnik-test nadal istnieją" || echo "wolumeny skasowane"

log "6. db → restore → alembic upgrade head → app"
tr0=$(date +%s)
$COMPOSE up -d db
# Gołe nazwy: restore.sh szuka ich w BACKUP_DIR — żadna ścieżka kontenera nie
# przechodzi przez shell hosta (Git Bash przepisałby `/backups/x` na ścieżkę Windows).
$COMPOSE --profile backup run --rm backup restore "$DUMP" "$TAR" --wipe-uploads
$COMPOSE run --rm app alembic upgrade head | tail -1
$COMPOSE up -d app
wait_health ok
echo "czas restore (z podniesieniem stacku): $(( $(date +%s) - tr0 )) s"

log "7. liczności PO + smoke"
AFTER=$(counts); echo "$AFTER"
UPLOADS_AFTER=$(uploads_count); echo "plików uploadów (bez scratcha): $UPLOADS_AFTER"
[ "$BEFORE" = "$AFTER" ] || die "liczności tabel RÓŻNIĄ SIĘ po restore"
[ "$UPLOADS_BEFORE" = "$UPLOADS_AFTER" ] || die "liczba plików uploadów różni się po restore"
login
RECIPES=$(api_get "/recipes?limit=50" | py "import json,sys; print(json.load(sys.stdin)['total'])")
PLAN=$(api_get "/plan/days?from=2026-08-24&to=2026-08-30" | py "import json,sys; d=json.load(sys.stdin); print(len(d['items']) if isinstance(d,dict) and 'items' in d else len(d))")
LISTS=$(api_get "/shopping/lists?limit=50" | py "import json,sys; print(json.load(sys.stdin)['total'])")
PHOTO_STATUS=$(curl -s -o /dev/null -w '%{http_code}' -H "Cookie: $COOKIE" "$BASE$PHOTO_URL")
echo "smoke: przepisy=$RECIPES dni_planu=$PLAN listy=$LISTS zdjęcie_http=$PHOTO_STATUS"
[ "$PHOTO_STATUS" = "200" ] || die "zdjęcie przepisu nie wraca po restore (HTTP $PHOTO_STATUS)"
[ "$RECIPES" -gt 0 ] && [ "$PLAN" -gt 0 ] || die "smoke: brak przepisów albo dni planu po restore"

log "DRILL ZAKOŃCZONY POPRAWNIE — całość $(( $(date +%s) - t0 )) s; zestaw: $DUMP ($(du -h "$PASNIK_TEST_BACKUPS_DIR/$DUMP" | cut -f1)), $TAR ($(du -h "$PASNIK_TEST_BACKUPS_DIR/$TAR" | cut -f1))"
