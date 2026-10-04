#!/usr/bin/env bash
# Wejście do Ansible dla wrapperów Taskfile (`task deploy|rollback|provision|…`).
# Uruchamiane W WSL, z katalogu deploy/ (wrapper robi `wsl --cd …/deploy`).
#
#   bash ansible-run.sh galaxy
#   bash ansible-run.sh syntax
#   bash ansible-run.sh provision [argumenty ansible-playbook]
#   bash ansible-run.sh deploy|rollback|caddy-vhost [argumenty ansible-playbook]
#
# Dlaczego skrypt, a nie jedna linia w Taskfile: `wsl.exe` skleja argumenty
# w napis dla powłoki Linuksa i gubi cudzysłowy, więc `$zmienna` i pętle
# w `bash -c '…'` rozwijały się po złej stronie. Tu wszystko dzieje się już
# w WSL.
#
# - `ANSIBLE_CONFIG=ansible.cfg` jest KONIECZNE: checkout na /mnt/c jest
#   world-writable i bez jawnej zmiennej Ansible ignoruje ansible.cfg
#   (razem z `roles_path`).
# - Venv z pipa, NIE ansible z apt (apt wiezie 2.10, na którym role
#   ansistrano nie chodzą): ANSIBLE_VENV, domyślnie ~/.venvs/ansible.
# - Plik z sekretami (Ansible Vault) leży POZA repo: PASNIK_VAULT_FILE,
#   domyślnie ~/pasnik-prod.yml; hasło do niego podajesz w prompcie.
set -euo pipefail

cd "$(dirname "$0")"
export ANSIBLE_CONFIG=ansible.cfg

VENV="${ANSIBLE_VENV:-$HOME/.venvs/ansible}"
VAULT_FILE="${PASNIK_VAULT_FILE:-$HOME/pasnik-prod.yml}"
PLAYBOOK_BIN="$VENV/bin/ansible-playbook"

[ -x "$PLAYBOOK_BIN" ] || {
  echo "Brak $PLAYBOOK_BIN. Wymagania: python3 -m venv $VENV && $VENV/bin/pip install 'ansible-core>=2.16,<2.18'" >&2
  exit 1
}

mode="${1:-}"
[ -n "$mode" ] || { echo "użycie: ansible-run.sh galaxy|syntax|provision|deploy|rollback|caddy-vhost [args]" >&2; exit 2; }
shift

case "$mode" in
  galaxy)
    exec "$VENV/bin/ansible-galaxy" install -r requirements.yml "$@"
    ;;
  syntax)
    for playbook in provision deploy rollback caddy-vhost; do
      echo "== playbook-$playbook.yml --syntax-check"
      "$PLAYBOOK_BIN" -i inventories/prod "playbook-$playbook.yml" --syntax-check "$@"
    done
    ;;
  provision)
    [ -r "$VAULT_FILE" ] || echo "UWAGA: brak $VAULT_FILE — provision bez sekretów (CHANGE_ME zatrzyma go, jeśli pliki mają powstać)" >&2
    if [ -r "$VAULT_FILE" ]; then
      exec "$PLAYBOOK_BIN" -i inventories/prod playbook-provision.yml -e "@$VAULT_FILE" --ask-vault-pass "$@"
    fi
    exec "$PLAYBOOK_BIN" -i inventories/prod playbook-provision.yml "$@"
    ;;
  deploy|rollback|caddy-vhost)
    exec "$PLAYBOOK_BIN" -i inventories/prod "playbook-$mode.yml" "$@"
    ;;
  *)
    echo "nieznany tryb: $mode" >&2
    exit 2
    ;;
esac
