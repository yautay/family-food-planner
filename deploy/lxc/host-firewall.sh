#!/usr/bin/env bash
# Reguły zapory dla mostu Incusa na hoście 192.168.2.121 (B18a, ADR-017, D30,
# dług O4 runnera). Uruchamiane JAKO ROOT NA HOŚCIE (nie w kontenerze),
# idempotentne.
#
#   sudo PASNIK_CT_IP=<adres kontenera> ./host-firewall.sh                  # nałóż teraz
#   sudo PASNIK_CT_IP=<adres kontenera> ./host-firewall.sh --install-unit   # + unit systemd po każdym starcie Dockera
#
# PROBLEM, który to rozwiązuje:
#
# 1. Docker na hoście ustawia `iptables -P FORWARD DROP` i odcina NAT mostu
#    Incusa: kontener nie dosięga WAN-u (apt, PyPI, GitHub) ani bazy. Po restarcie
#    hosta reguły trzeba nałożyć PONOWNIE — dlatego unit (kryterium 6 karty B18).
#
# 2. Topologia D30: Caddy i kontener są na TYM SAMYM hoście i Caddy łączy się
#    z kontenerem wprost po moście (ruch hosta → kontener to OUTPUT, nie FORWARD),
#    więc port aplikacji NIE jest wystawiony w LAN i nie ma DNAT-a. Zostaje
#    obrona w głąb: nic z LAN-u nie ma prawa NAWIĄZAĆ połączenia do kontenera
#    przez ten host (ktoś mógłby dodać u siebie trasę do podsieci mostu przez
#    .121) — reguła nr 1 DROP-uje wszystkie NOWE przekazywane połączenia do mostu.
#    Dzięki temu jedynym źródłem połączeń do aplikacji jest sam host (Caddy),
#    a `FORWARDED_ALLOW_IPS=<adres mostu>` ufa wyłącznie jemu (07_SECURITY §7).
#
# Zmienne:
#   PASNIK_CT_IP       adres kontenera `pasnik` (tylko do komunikatów/kontroli) — WYMAGANY
#   PASNIK_BRIDGE      most Incusa                                               (incusbr0)
set -euo pipefail

CT_IP="${PASNIK_CT_IP:-}"
BRIDGE="${PASNIK_BRIDGE:-incusbr0}"
INSTALL_UNIT=0
UNIT_PATH=/etc/systemd/system/pasnik-docker-user.service
SCRIPT_TARGET=/usr/local/sbin/pasnik-host-firewall.sh
ENV_TARGET=/etc/default/pasnik-host-firewall

for argument in "$@"; do
  case "$argument" in
    --install-unit) INSTALL_UNIT=1 ;;
    -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) printf 'BŁĄD: nieznany argument %s\n' "$argument" >&2; exit 2 ;;
  esac
done

die() { printf 'BŁĄD: %s\n' "$*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || die "uruchom jako root (sudo) NA HOŚCIE"
[ -n "$CT_IP" ] || die "podaj PASNIK_CT_IP (adres kontenera: incus list pasnik -c 4)"
command -v iptables >/dev/null 2>&1 || die "brak iptables"

# DOCKER-USER istnieje, gdy Docker działa; bez Dockera ten skrypt jest zbędny.
iptables -nL DOCKER-USER >/dev/null 2>&1 || die "brak łańcucha DOCKER-USER (Docker nie działa?). Bez Dockera FORWARD nie jest DROP i reguły nie są potrzebne."

ensure_first() {
  # Reguła ma stać NA POZYCJI 1. `iptables -S` normalizuje zapis, więc pozycję
  # rozpoznajemy po treści pierwszej reguły (linia 1 to `-N DOCKER-USER`).
  first="$(iptables -S DOCKER-USER | sed -n '2p')"
  if iptables -C DOCKER-USER "$@" 2>/dev/null && printf '%s' "$first" | grep -q -- "-j DROP"; then
    return 0
  fi
  iptables -C DOCKER-USER "$@" 2>/dev/null && iptables -D DOCKER-USER "$@"
  iptables -I DOCKER-USER 1 "$@"
}

ensure_present() {
  iptables -C DOCKER-USER "$@" 2>/dev/null || iptables -A DOCKER-USER "$@"
}

# 1. Żadnych NOWYCH połączeń do mostu przez FORWARD (z LAN-u, z innych mostów
#    Dockera). Połączenia hosta (Caddy, ssh przez proxy device) to OUTPUT/INPUT
#    i tego nie dotyczą.
ensure_first -o "$BRIDGE" -m conntrack --ctstate NEW -j DROP

# 2. Wyjście kontenera (WAN, baza na tym hoście) i odpowiedzi do niego. Bez tych
#    reguł Docker (FORWARD DROP) zabija NAT mostu — kontener nie widzi nawet apt.
ensure_present -i "$BRIDGE" -j ACCEPT
ensure_present -o "$BRIDGE" -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT

printf '\nDOCKER-USER po nałożeniu reguł (kontener %s, most %s):\n' "$CT_IP" "$BRIDGE"
iptables -S DOCKER-USER

if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  printf '\nUWAGA: ufw jest AKTYWNY. Kontener potrzebuje DHCP/DNS od hosta i trasy na zewnątrz:\n'
  printf '  sudo ufw allow in on %s\n  sudo ufw route allow in on %s\n  sudo ufw route allow out on %s\n' "$BRIDGE" "$BRIDGE" "$BRIDGE"
  printf '(deploy/lxc/README.md §3). Skrypt ufw NIE zmienia — to Twoja zapora.\n'
fi

if [ "$INSTALL_UNIT" -eq 1 ]; then
  src="$(readlink -f "$0")"
  if [ "$src" != "$SCRIPT_TARGET" ]; then
    install -m 0755 "$src" "$SCRIPT_TARGET"
  fi
  # Parametry w pliku środowiska — unit i skrypt czytają to samo.
  cat >"$ENV_TARGET" <<ENVFILE
PASNIK_CT_IP=$CT_IP
PASNIK_BRIDGE=$BRIDGE
ENVFILE
  chmod 0644 "$ENV_TARGET"
  cat >"$UNIT_PATH" <<UNIT
[Unit]
Description=Reguly DOCKER-USER dla mostu Incusa (Pasnik, B18a)
# Docker tworzy lancuch DOCKER-USER i ustawia FORWARD DROP przy starcie —
# nakladamy reguly PO nim i ponownie przy kazdym jego restarcie (PartOf).
After=docker.service incus.service
Requires=docker.service
PartOf=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
EnvironmentFile=$ENV_TARGET
ExecStart=$SCRIPT_TARGET

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable pasnik-docker-user.service
  printf '\nunit zainstalowany i włączony: %s (sprawdź: systemctl status pasnik-docker-user)\n' "$UNIT_PATH"
fi
