#!/usr/bin/env bash
# Jedno polecenie stawiające maszynę Paśnika w Incusie NA HOŚCIE 192.168.2.121
# (B18a, ADR-017, D30 — host zmieniony z .111). Wzorzec:
# nc-tech-test-runner/deploy/lxc/create-incus.sh, z różnicami: STATYCZNE IPv4
# kontenera (Caddy łączy się z nim wprost po moście — bez proxy device'a
# aplikacji i bez portu w LAN), proxy device SSH dla Ansible, oraz wypisanie
# ODCISKU klucza hosta SSH i wartości do `group_vars/prod.yml` (`ct_ip`,
# `bridge_gateway`) — pierwszy provision wiezie sekrety i nie może przyjąć
# dowolnego klucza.
#
#   OPERATOR_PUBKEY="ssh-ed25519 AAAA... operator" ./create-incus.sh
#   ./create-incus.sh pasnik ~/.ssh/id_ed25519.pub
#   ./create-incus.sh --recreate           # to samo po awarii: kasuje i stawia od zera
#
# Skrypt jest SAMOWYSTARCZALNY: potrzebuje siebie i leżącego obok `provision.sh`
# (`scp` obu plików na hosta; pliki MUSZĄ mieć LF — pilnuje .gitattributes).
# Nie klonuje repo i nie zna żadnego sekretu — jedyny parametr wrażliwy to
# PUBLICZNY klucz SSH.
#
# Zmienne (bezpieczne domyślne poza kluczem):
#   OPERATOR_PUBKEY       publiczny klucz SSH konta `deploy` (albo 2. argument:
#                         ścieżka do pliku `.pub` lub sama treść klucza)
#   PROVISION_PUBKEY      publiczny klucz SSH konta `root` (kanał provisionu
#                         Ansible); domyślnie ten sam; "" = root bez logowania
#   PASNIK_LXC_NAME       nazwa kontenera                     (pasnik)
#   PASNIK_LXC_IMAGE      obraz systemu                       (images:debian/13)
#   PASNIK_LXC_CPU        limit rdzeni                        (2)
#   PASNIK_LXC_MEMORY     limit pamięci                       (2GiB)
#   PASNIK_LXC_DISK       quota dysku (pusta = bez quoty; pula `dir` jej nie umie)
#   PASNIK_LXC_IPV4       statyczny adres IPv4 w podsieci incusbr0
#                         (domyślnie <podsieć mostu>.201); idzie do `ct_ip`
#   PASNIK_LXC_BRIDGE     most Incusa                         (incusbr0)
#   PASNIK_LXC_NIC        nazwa karty z profilu `default`     (eth0)
#   PASNIK_LXC_SSH_PORT   port SSH na hoście                  (2223)
#   PASNIK_LXC_SSH_LISTEN adres nasłuchu SSH na hoście        (0.0.0.0)
#   PASNIK_LXC_SNAPSHOT   nazwa migawki po instalacji         (czysty)
#   PASNIK_LXC_PROVISION  ścieżka do instalatora              (provision.sh obok)
#   PASNIK_LXC_HOST_IP    adres LAN hosta (tylko do wypisu known_hosts) (192.168.2.121)
#
# PRZED pierwszym uruchomieniem sprawdź na hoście `sudo ss -ltnp` — port SSH
# nie może kolidować (deploy/lxc/README.md, sekcja 1).
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

NAME="${PASNIK_LXC_NAME:-pasnik}"
IMAGE="${PASNIK_LXC_IMAGE:-images:debian/13}"
CPU="${PASNIK_LXC_CPU:-2}"
MEMORY="${PASNIK_LXC_MEMORY:-2GiB}"
DISK="${PASNIK_LXC_DISK:-}"
IPV4="${PASNIK_LXC_IPV4:-}"
BRIDGE="${PASNIK_LXC_BRIDGE:-incusbr0}"
NIC="${PASNIK_LXC_NIC:-eth0}"
SSH_PORT="${PASNIK_LXC_SSH_PORT:-2223}"
SSH_LISTEN="${PASNIK_LXC_SSH_LISTEN:-0.0.0.0}"
SNAPSHOT="${PASNIK_LXC_SNAPSHOT:-czysty}"
PROVISION="${PASNIK_LXC_PROVISION:-$SCRIPT_DIR/provision.sh}"
HOST_IP="${PASNIK_LXC_HOST_IP:-192.168.2.121}"
PUBKEY="${OPERATOR_PUBKEY:-}"
RECREATE=0

SELFTEST=/usr/local/sbin/pasnik-selftest
PROVISION_REMOTE=/root/provision.sh
NETWORK_WAIT_TRIES=60

say() { printf '\n== %s\n' "$*"; }
die() { printf 'BŁĄD: %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,/^set -euo/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
  exit 0
}

positional=()
for argument in "$@"; do
  case "$argument" in
    --recreate) RECREATE=1 ;;
    -h|--help) usage ;;
    -*) die "nieznany przełącznik $argument (zobacz --help)" ;;
    *) positional+=("$argument") ;;
  esac
done
[ "${#positional[@]}" -le 2 ] || die "za dużo argumentów (zobacz --help)"
[ "${#positional[@]}" -lt 1 ] || NAME="${positional[0]}"
[ "${#positional[@]}" -lt 2 ] || PUBKEY="${positional[1]}"

# --- 1. przygotowanie ---------------------------------------------------------

say "1/9 sprawdzenie hosta"
command -v incus >/dev/null 2>&1 || die 'brak polecenia incus w PATH'
incus info >/dev/null 2>&1 || die 'incus nie odpowiada temu kontu: brakuje grupy incus-admin albo "incus admin init --minimal"'
[ -f "$PROVISION" ] || die "brak instalatora $PROVISION (skopiuj oba pliki na hosta)"
printf 'incus: %s\n' "$(incus version | tr '\n' ' ')"

if [ -z "$PUBKEY" ]; then
  die "podaj publiczny klucz SSH: OPERATOR_PUBKEY=\"ssh-ed25519 AAAA... operator\" $0 (albo 2. argument)"
fi
if [ -f "$PUBKEY" ]; then
  PUBKEY="$(head -1 "$PUBKEY")"
fi
PUBKEY="${PUBKEY#"${PUBKEY%%[![:space:]]*}"}"
PUBKEY="${PUBKEY%"${PUBKEY##*[![:space:]]}"}"
case "$PUBKEY" in
  ssh-ed25519\ *|ssh-rsa\ *|ecdsa-sha2-*\ *|sk-ssh-*\ *) : ;;
  *) die "to nie wygląda na publiczny klucz SSH (oczekiwane: ssh-ed25519 AAAA...); klucza PRYWATNEGO tu nie podawaj" ;;
esac
case "$PUBKEY" in
  *'"'*|*'\'*) die "klucz zawiera znak, którego instalator nie przyjmie (cudzysłów albo backslash)" ;;
  *$'\n'*|*$'\r'*) die "klucz musi być JEDNĄ linią (podaj plik .pub albo pojedynczy wiersz)" ;;
esac
printf 'klucz deployu: %s...\n' "$(printf '%s' "$PUBKEY" | cut -c1-24)"

# Statyczny IPv4: Caddy (na tym samym hoście) łączy się z kontenerem wprost po tym
# adresie, a `pasnik.env` i blok Caddy trzymają go jako `ct_ip`.
bridge_cidr="$(incus network get "$BRIDGE" ipv4.address 2>/dev/null || true)"
[ -n "$bridge_cidr" ] && [ "$bridge_cidr" != "none" ] \
  || die "most $BRIDGE nie ma ipv4.address (incus network show $BRIDGE) — kontener potrzebuje IPv4 na moście"
bridge_ip="${bridge_cidr%/*}"
if [ -z "$IPV4" ]; then
  IPV4="${bridge_ip%.*}.201"
fi
case "$IPV4" in
  *[!0-9.]*|"") die "PASNIK_LXC_IPV4 nie wygląda na adres IPv4: $IPV4" ;;
esac
[ "${IPV4%.*}" = "${bridge_ip%.*}" ] \
  || die "adres $IPV4 jest poza podsiecią mostu $BRIDGE ($bridge_cidr) — ustaw PASNIK_LXC_IPV4"
[ "$IPV4" != "$bridge_ip" ] || die "adres $IPV4 to adres mostu"
printf 'most %s: %s; adres kontenera: %s\n' "$BRIDGE" "$bridge_cidr" "$IPV4"

say "2/9 obraz systemu $IMAGE (Debian 13, bez cloud-inita)"
incus image info "$IMAGE" >/dev/null 2>&1 ||
  die "obraz $IMAGE niedostępny; sprawdź WAN i aliasy (incus image list images: debian), np. PASNIK_LXC_IMAGE=images:debian/trixie"

# --- 2. kontener --------------------------------------------------------------

started_at=$SECONDS

if incus info "$NAME" >/dev/null 2>&1; then
  if [ "$RECREATE" -eq 1 ]; then
    say "3/9 kasowanie istniejącego kontenera $NAME (--recreate)"
    incus delete --force "$NAME"
  else
    die "kontener $NAME już istnieje; skasuj go świadomie: $0 --recreate ${NAME}"
  fi
else
  say "3/9 kontener $NAME nie istnieje — stawiam od zera"
fi
# Adres zajęty przez INNY kontener zepsułby jego sieć i naszą — sprawdzamy po
# skasowaniu ewentualnego poprzednika.
if incus list --format csv -c n4 | grep -F "$IPV4" >/dev/null 2>&1; then
  die "adres $IPV4 jest już używany przez inny kontener (incus list) — ustaw PASNIK_LXC_IPV4"
fi

say "4/9 incus init (cpu=$CPU, memory=$MEMORY, dysk=${DISK:-bez quoty}, ipv4=$IPV4)"
init=(incus init "$IMAGE" "$NAME"
  -c "limits.cpu=$CPU"
  -c "limits.memory=$MEMORY")
# Bez security.nesting: w kontenerze nie ma silnika kontenerów.
if [ -n "$DISK" ]; then
  init+=(-d "root,size=$DISK")
fi
"${init[@]}"
incus config device override "$NAME" "$NIC" "ipv4.address=$IPV4"
incus start "$NAME"

say "5/9 czekam, aż kontener złapie trasę do WAN"
online=0
for _ in $(seq "$NETWORK_WAIT_TRIES"); do
  if incus exec "$NAME" -- getent hosts deb.debian.org >/dev/null 2>&1; then
    online=1
    break
  fi
  sleep 1
done
if [ "$online" -eq 0 ]; then
  cat <<HINT
>>> Kontener nie widzi świata. Sprawdź na hoście:

      sysctl -n net.ipv4.ip_forward            # ma być 1
      incus network get $BRIDGE ipv4.nat       # ma być true
      sudo iptables -S FORWARD | head -3       # polityka DROP = ruch mostu ginie

    Najczęstsza przyczyna: Docker na hoście ustawia \`iptables -P FORWARD DROP\`
    i zabija NAT mostów Incusa. Reguły DOCKER-USER dla $BRIDGE opisuje
    deploy/lxc/README.md (sekcja 3, host-firewall.sh).
HINT
  printf '\nKontener %s ZOSTAJE do diagnozy: incus exec %s -- bash\n' "$NAME" "$NAME"
  die "brak trasy z kontenera do repozytorium pakietów"
fi
printf 'DNS i trasa: ok\n'

say "6/9 instalator provision.sh w kontenerze (pakiety, uv, użytkownicy, katalogi, sshd, samotest)"
incus file push "$PROVISION" "$NAME$PROVISION_REMOTE" --mode 0755
provision_status=0
incus exec "$NAME" \
  --env OPERATOR_PUBKEY="$PUBKEY" \
  --env PROVISION_PUBKEY="${PROVISION_PUBKEY-$PUBKEY}" \
  -- "$PROVISION_REMOTE" || provision_status=$?
if [ "$provision_status" -ne 0 ]; then
  printf '\nKontener %s ZOSTAJE do diagnozy (bez migawki): incus exec %s -- bash\n' "$NAME" "$NAME"
  printf 'Po naprawie: %s --recreate %s\n' "$0" "$NAME"
  die "instalator zakończył się kodem $provision_status — maszyna NIE jest gotowa"
fi

say "7/9 proxy SSH ${SSH_LISTEN}:${SSH_PORT} -> 127.0.0.1:22 w kontenerze (dla Ansible z WSL)"
if incus config device get "$NAME" ssh listen >/dev/null 2>&1; then
  printf 'urządzenie `ssh` już jest\n'
else
  incus config device add "$NAME" ssh proxy \
    "listen=tcp:${SSH_LISTEN}:${SSH_PORT}" connect=tcp:127.0.0.1:22
fi

say "8/9 migawka $SNAPSHOT"
incus snapshot delete "$NAME" "$SNAPSHOT" >/dev/null 2>&1 || true
incus snapshot create "$NAME" "$SNAPSHOT"

say "9/9 odcisk klucza hosta SSH (PORÓWNAJ z tym, co zobaczy operator)"
# Dług nr 4 runnera: pierwszy provision wiezie sekrety, więc nie może przyjąć
# dowolnego klucza odpowiadającego na porcie. Wpis poniżej wklej do pliku
# z inwentarza (`ssh_host_key_file`, domyślnie ~/.ssh/pasnik-prod.hostkeys)
# PRZED pierwszym przebiegiem Ansible.
host_pub="$(incus exec "$NAME" -- cat /etc/ssh/ssh_host_ed25519_key.pub)"
incus exec "$NAME" -- ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
printf 'wpis known_hosts:\n  [%s]:%s %s\n' "$HOST_IP" "$SSH_PORT" "$(printf '%s' "$host_pub" | awk '{print $1" "$2}')"

elapsed=$((SECONDS - started_at))
printf '\n--- gotowe w %s s ---\n' "$elapsed"
printf 'kontener : %s (%s), adres %s\n' "$NAME" "$IMAGE" "$IPV4"
printf 'SSH      : ssh -p %s deploy@%s\n' "$SSH_PORT" "$HOST_IP"
printf '\n>>> WPISZ do deploy/group_vars/prod.yml (provision odmówi, dopóki są CHANGE_ME):\n'
printf '    ct_ip: %s\n    bridge_gateway: %s\n' "$IPV4" "$bridge_ip"
printf '>>> i wykonaj na hoście reguły zapory: PASNIK_CT_IP=%s sudo ./host-firewall.sh --install-unit\n\n' "$IPV4"
printf 'migawka  : incus snapshot restore %s %s\n' "$NAME" "$SNAPSHOT"
printf 'od zera  : %s --recreate %s\n' "$0" "$NAME"
printf 'samotest : OK (pełne wyjście w kroku 6/9); powtórka: incus exec %s -- %s\n' "$NAME" "$SELFTEST"
