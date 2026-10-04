#!/usr/bin/env bash
# Instalator maszyny Paśnika (B18a, ADR-017). Uruchamiany JAKO ROOT wewnątrz
# gotowego kontenera Debian 13 (`incus exec`, konsola). Każda sekcja jest
# idempotentna — drugi przebieg niczego nie psuje i kończy się tym samym
# samotestem (`/usr/local/sbin/pasnik-selftest`).
#
#   OPERATOR_PUBKEY="ssh-ed25519 AAAA... operator" ./provision.sh
#
# Zmienne:
#   OPERATOR_PUBKEY  publiczny klucz SSH konta `deploy`; pusty = nie ruszaj
#                    kluczy (ponowny przebieg po deployu)
#   PROVISION_PUBKEY publiczny klucz SSH konta `root` — kanał `playbook-provision.yml`
#                    (unit systemd i pliki w /etc/pasnik wymagają roota, a `deploy`
#                    celowo go nie ma). Domyślnie ten sam co OPERATOR_PUBKEY;
#                    pusty ciąg = root w ogóle nie przyjmuje logowania
#   PASNIK_SKIP_APT  `1` pomija apt/pobieranie (maszyna bez WAN, wszystko już jest)
#
# Zero sekretów: instalator nie zna hasła bazy ani SECRET_KEY. Plik
# /etc/pasnik/pasnik.env i PGPASSFILE zakłada provision Ansible (kanał root)
# z vaulta operatora, więc odtworzenie maszyny nigdy nie wymaga sekretu.
#
# Co instalujemy i DLACZEGO TYLKO TO (B18 Stage 2):
#   python3                  3.13 z Debiana 13 — spełnia `requires-python >=3.13`
#   rsync openssh-server     ansistrano kopiuje release; jedyne wejście na maszynę
#   ca-certificates curl sudo HTTPS (PyPI, GitHub, PGDG); pobranie uv/klucza; sudoers deployu
#   postgresql-client-16     pg_dump/pg_restore/psql w WERSJI SERWERA (PGDG) —
#                            dump klienta 17 nie zawsze wraca na serwer 16
#   uv                       ta sama minor co docker/Dockerfile; `uv sync --frozen`
#                            buduje venv KAŻDEGO release'u na maszynie
# Docker ani żaden silnik kontenerów NIE jest instalowany (ADR-017 pkt 1).
set -euo pipefail

OPERATOR_PUBKEY="${OPERATOR_PUBKEY:-}"
PROVISION_PUBKEY="${PROVISION_PUBKEY-$OPERATOR_PUBKEY}"
PASNIK_SKIP_APT="${PASNIK_SKIP_APT:-0}"

SELFTEST_PATH=/usr/local/sbin/pasnik-selftest
SUDOERS_PATH=/etc/sudoers.d/60-pasnik-deploy
SSHD_DROPIN=/etc/ssh/sshd_config.d/00-pasnik.conf

# PASNIK-PINS-BEGIN
# Wszystko, co pobieramy z sieci, jest przypięte SKRÓTEM — zmiana po stronie
# dostawcy zatrzymuje instalator zamiast cicho podmienić binarkę.
# uv: minor MUSI zgadzać się z `docker/Dockerfile` (pilnuje test_deploy_config).
UV_VERSION="0.11.7"
UV_SHA256="6681d691eb7f9c00ac6a3af54252f7ab29ae72f0c8f95bdc7f9d1401c23ea868"
UV_URL="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz"
# Klucz repozytorium PGDG (ACCC4CF8). Rotacja klucza = nowy skrót tutaj.
PGDG_KEY_URL="https://www.postgresql.org/media/keys/ACCC4CF8.asc"
PGDG_KEY_SHA256="0144068502a1eddd2a0280ede10ef607d1ec592ce819940991203941564e8e76"
PGDG_KEY_PATH=/etc/apt/keyrings/apt.postgresql.org.asc
PGDG_CLIENT_PACKAGE="postgresql-client-16"
# PASNIK-PINS-END

# PASNIK-PACKAGES-BEGIN
PASNIK_PACKAGES="python3 rsync openssh-server ca-certificates sudo curl"
# PASNIK-PACKAGES-END

# PASNIK-DIRS-BEGIN
# katalog                         właściciel          tryb
PASNIK_DIRS_DEPLOY="/opt/pasnik /opt/pasnik/releases /opt/pasnik/shared /opt/pasnik/shared/uv-cache"
PASNIK_DIR_UPLOADS="/opt/pasnik/shared/uploads"
PASNIK_DIR_BACKUPS="/opt/pasnik/shared/backups"
PASNIK_DIR_CONFIG="/etc/pasnik"
PASNIK_DIR_LIB="/usr/local/lib/pasnik"
# PASNIK-DIRS-END

step() { printf '\n== %s\n' "$*"; }
die() { printf 'BŁĄD: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "uruchom jako root (instalator zakłada użytkowników i pisze do /etc)"
[ "$(uname -m)" = "x86_64" ] || die "pinezka uv dotyczy x86_64, a to jest $(uname -m)"

step "1/10 apt i dpkg: bez recommends, bez dokumentacji"
cat >/etc/apt/apt.conf.d/99pasnik-minimal <<'APTCONF'
APT::Install-Recommends "false";
APT::Install-Suggests "false";
APT::Get::Assume-Yes "true";
APTCONF
cat >/etc/dpkg/dpkg.cfg.d/99pasnik-minimal <<'DPKGCONF'
path-exclude=/usr/share/doc/*
path-exclude=/usr/share/man/*
path-exclude=/usr/share/info/*
DPKGCONF
cat >/etc/default/locale <<'LOCALECONF'
LANG=C.UTF-8
LC_ALL=C.UTF-8
LOCALECONF

missing_packages() {
  local missing="" package
  for package in "$@"; do
    if ! dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'; then
      missing="$missing $package"
    fi
  done
  printf '%s' "$missing"
}

step "2/10 pakiety bazowe: $PASNIK_PACKAGES"
# shellcheck disable=SC2086 # lista pakietów ma się rozwinąć na osobne argumenty
missing="$(missing_packages $PASNIK_PACKAGES)"
if [ -z "$missing" ]; then
  printf 'komplet już zainstalowany\n'
elif [ "$PASNIK_SKIP_APT" = "1" ]; then
  die "brakuje pakietów:$missing, a PASNIK_SKIP_APT=1"
else
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  # shellcheck disable=SC2086
  apt-get install -y --no-install-recommends $missing
fi

step "3/10 repozytorium PGDG i $PGDG_CLIENT_PACKAGE (klient = wersja serwera 16)"
# Priorytet 100: z PGDG wchodzi WYŁĄCZNIE to, czego Debian nie ma (klient 16),
# a reszta maszyny zostaje przy pakietach Debiana.
if [ -z "$(missing_packages "$PGDG_CLIENT_PACKAGE")" ]; then
  printf '%s już zainstalowany\n' "$PGDG_CLIENT_PACKAGE"
elif [ "$PASNIK_SKIP_APT" = "1" ]; then
  die "brakuje $PGDG_CLIENT_PACKAGE, a PASNIK_SKIP_APT=1"
else
  install -d -m 0755 /etc/apt/keyrings
  key_tmp="$(mktemp)"
  curl --fail --silent --show-error --location --max-time 60 -o "$key_tmp" "$PGDG_KEY_URL"
  printf '%s  %s\n' "$PGDG_KEY_SHA256" "$key_tmp" | sha256sum --check --status \
    || { rm -f "$key_tmp"; die "skrót klucza PGDG się nie zgadza (rotacja klucza? zaktualizuj PGDG_KEY_SHA256 świadomie)"; }
  install -m 0644 "$key_tmp" "$PGDG_KEY_PATH"
  rm -f "$key_tmp"
  cat >/etc/apt/sources.list.d/pgdg.sources <<PGDGSOURCES
Types: deb
URIs: https://apt.postgresql.org/pub/repos/apt
Suites: trixie-pgdg
Components: main
Signed-By: $PGDG_KEY_PATH
PGDGSOURCES
  cat >/etc/apt/preferences.d/pgdg <<'PGDGPIN'
Package: *
Pin: origin apt.postgresql.org
Pin-Priority: 100
PGDGPIN
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends "$PGDG_CLIENT_PACKAGE"
fi

step "4/10 uv $UV_VERSION (skrót SHA-256 przypięty)"
if [ -x /usr/local/bin/uv ] && [ "$(/usr/local/bin/uv --version | awk '{print $2}')" = "$UV_VERSION" ]; then
  printf 'uv %s już jest\n' "$UV_VERSION"
elif [ "$PASNIK_SKIP_APT" = "1" ]; then
  die "brakuje uv $UV_VERSION, a PASNIK_SKIP_APT=1"
else
  uv_tmp="$(mktemp -d)"
  curl --fail --silent --show-error --location --max-time 120 -o "$uv_tmp/uv.tar.gz" "$UV_URL"
  printf '%s  %s\n' "$UV_SHA256" "$uv_tmp/uv.tar.gz" | sha256sum --check --status \
    || { rm -rf "$uv_tmp"; die "skrót paczki uv się nie zgadza — nie instaluję"; }
  tar --extract --gzip --file="$uv_tmp/uv.tar.gz" --directory="$uv_tmp" --strip-components=1
  install -m 0755 "$uv_tmp/uv" /usr/local/bin/uv
  rm -rf "$uv_tmp"
fi

step "5/10 użytkownik deploy (SSH, ansistrano)"
# Bez grupy `sudo`: Debian daje jej `ALL=(ALL:ALL) ALL`, a deploy ma mieć
# wyłącznie listę z sekcji 8.
if id deploy >/dev/null 2>&1; then
  printf 'deploy już istnieje\n'
else
  useradd --create-home --shell /bin/bash --comment "konto deployu Paśnika (ansistrano, SSH)" deploy
fi
passwd --lock deploy >/dev/null

step "6/10 użytkownik pasnik (usługa i backup, bez logowania)"
if id pasnik >/dev/null 2>&1; then
  printf 'pasnik już istnieje\n'
else
  useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin \
    --comment "usługa Paśnika i backup" pasnik
fi
passwd --lock pasnik >/dev/null

install_pubkey() {
  # $1 = konto, $2 = katalog domowy, $3 = klucz publiczny, $4 = nazwa zmiennej
  case "$3" in
    ssh-ed25519\ *|ssh-rsa\ *|ecdsa-sha2-*\ *|sk-ssh-*\ *) : ;;
    *) die "$4 nie wygląda na publiczny klucz SSH (ssh-ed25519 / ssh-rsa / ecdsa-sha2-*)" ;;
  esac
  install -d -o "$1" -g "$1" -m 0700 "$2/.ssh"
  printf '%s\n' "$3" >"$2/.ssh/authorized_keys"
  chown "$1:$1" "$2/.ssh/authorized_keys"
  chmod 0600 "$2/.ssh/authorized_keys"
  printf 'klucz konta %s zapisany (%s...)\n' "$1" "$(printf '%s' "$3" | cut -c1-20)"
}

step "7/10 klucze SSH kont deploy i root, sshd bez haseł"
# Dwa kanały, dwie role (wzorzec runnera):
#   deploy — ścieżka rutynowa (rsync releasu, restart usługi wąskim sudo),
#   root   — ścieżka uprzywilejowana, RAZ: unity systemd, /etc/pasnik, pasnik-cli.
# `deploy` celowo nie ma jak zostać rootem, więc provision ma własny kanał.
if [ -n "$OPERATOR_PUBKEY" ]; then
  install_pubkey deploy /home/deploy "$OPERATOR_PUBKEY" OPERATOR_PUBKEY
else
  printf 'OPERATOR_PUBKEY pusty — klucze konta deploy bez zmian (ponowny przebieg)\n'
fi
if [ -n "$PROVISION_PUBKEY" ]; then
  install_pubkey root /root "$PROVISION_PUBKEY" PROVISION_PUBKEY
else
  printf 'PROVISION_PUBKEY pusty — root nie przyjmuje logowania (provision Ansible nie wejdzie)\n'
fi
# Bez klucza i bez haseł do maszyny nie wejdzie NIKT (zostaje `incus exec`).
# Lepiej zatrzymać instalator, niż zamknąć drzwi z kluczem w środku.
if [ ! -s /home/deploy/.ssh/authorized_keys ]; then
  die "konto deploy nie ma żadnego klucza, a ten krok wyłącza hasła; podaj OPERATOR_PUBKEY"
fi
install -d -m 0755 /etc/ssh/sshd_config.d
# PASNIK-SSHD-BEGIN
cat >"$SSHD_DROPIN" <<'SSHDCONF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
PermitEmptyPasswords no
X11Forwarding no
SSHDCONF
# PASNIK-SSHD-END
# Zła składnia drop-inu położyłaby sshd dopiero przy restarcie — sprawdzamy ją,
# zanim restart odetnie jedyne wejście na maszynę.
sshd -t || die "$SSHD_DROPIN psuje konfigurację sshd (sshd -t)"
systemctl enable ssh >/dev/null 2>&1 || true
systemctl restart ssh

step "8/10 sudo dla deployu (wąska lista)"
# PASNIK-SUDOERS-BEGIN
cat >"$SUDOERS_PATH" <<'SUDOERS'
deploy ALL=(root) NOPASSWD: /usr/bin/systemctl daemon-reload
deploy ALL=(root) NOPASSWD: /usr/bin/systemctl start pasnik
deploy ALL=(root) NOPASSWD: /usr/bin/systemctl stop pasnik
deploy ALL=(root) NOPASSWD: /usr/bin/systemctl restart pasnik
deploy ALL=(root) NOPASSWD: /usr/bin/systemctl is-active pasnik
deploy ALL=(root) NOPASSWD: /usr/bin/systemctl start pasnik-backup
deploy ALL=(pasnik) NOPASSWD: /usr/local/bin/pasnik-cli
SUDOERS
# PASNIK-SUDOERS-END
chmod 0440 "$SUDOERS_PATH"
visudo -cf "$SUDOERS_PATH" >/dev/null || die "$SUDOERS_PATH nie przechodzi visudo"

step "9/10 katalogi (09_DEPLOYMENT §1)"
for directory in $PASNIK_DIRS_DEPLOY; do
  install -d -o deploy -g deploy -m 0755 "$directory"
done
# Dane aplikacji i backupy: właścicielem jest `pasnik` (tym kontem chodzi usługa
# i timer backupu), `deploy` ich nie czyta — backup to komplet danych rodziny.
install -d -o pasnik -g pasnik -m 0750 "$PASNIK_DIR_UPLOADS"
install -d -o pasnik -g pasnik -m 0750 "$PASNIK_DIR_BACKUPS"
# Konfiguracja: root pisze, grupa `pasnik` czyta (PGPASSFILE leży tu jako 0600 pasnik).
install -d -o root -g pasnik -m 0750 "$PASNIK_DIR_CONFIG"
install -d -o root -g root -m 0755 "$PASNIK_DIR_LIB"
apt-get -y autoremove --purge >/dev/null 2>&1 || true
apt-get clean

step "10/10 samotest"
cat >"$SELFTEST_PATH" <<'PASNIK_SELFTEST'
#!/bin/sh
# PASNIK-SELFTEST-BEGIN
# Samotest maszyny Paśnika (B18a). POSIX sh, wyłącznie narzędzia z bazowego
# systemu i te, które postawił instalator. Kod 0 = maszyna zgodna z ADR-017
# i 09_DEPLOYMENT §1.
set -u
fail=0
say() { printf '%s\n' "$*"; }
bad() { printf 'BŁĄD: %s\n' "$*"; fail=1; }

say "--- pasnik selftest ---"
say "host: $(hostname)"
say "system: $( (. /etc/os-release && printf '%s' "$PRETTY_NAME") 2>/dev/null || printf 'os-release brak')"

version=$(/usr/bin/python3 -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || printf brak)
case "$version" in
  3.13.*) say "python3: $version" ;;
  *) bad "python3 = $version, wymagane 3.13.x (requires-python >=3.13)" ;;
esac

if command -v uv >/dev/null 2>&1; then
  uv_version=$(uv --version | awk '{print $2}')
  [ "$uv_version" = "@UV_VERSION@" ] && say "uv: $uv_version" || bad "uv = $uv_version, oczekiwane @UV_VERSION@"
else
  bad "brak uv"
fi

for tool in pg_dump pg_restore psql; do
  if command -v "$tool" >/dev/null 2>&1; then
    case "$("$tool" --version)" in
      *" 16."*) say "$tool: $("$tool" --version)" ;;
      *) bad "$tool to nie wersja 16 ($("$tool" --version)) — klient musi być równy serwerowi" ;;
    esac
  else
    bad "brak $tool (pakiet postgresql-client-16)"
  fi
done

for tool in rsync ssh sudo curl; do
  if command -v "$tool" >/dev/null 2>&1; then
    say "$tool: $(command -v "$tool")"
  else
    bad "brak $tool"
  fi
done

# ADR-017 pkt 1: Docker nie występuje na produkcji. Obecność = błąd instalatora.
for tool in docker podman; do
  if command -v "$tool" >/dev/null 2>&1; then
    bad "$tool jest zainstalowany (ADR-017: bez silnika kontenerów w LXC)"
  fi
done
say "silnik kontenerów: brak (ok)"

for account in deploy pasnik; do
  if id "$account" >/dev/null 2>&1; then
    say "użytkownik: $(id "$account")"
  else
    bad "brak użytkownika $account"
  fi
done
shell=$(getent passwd pasnik | cut -d: -f7)
case "$shell" in
  */nologin|*/false) say "powłoka pasnik: $shell (ok)" ;;
  *) bad "pasnik ma powłokę $shell, oczekiwane nologin" ;;
esac
for account in deploy pasnik; do
  if id -nG "$account" 2>/dev/null | tr ' ' '\n' | grep -qx sudo; then
    bad "$account jest w grupie sudo (Debian daje jej ALL=(ALL:ALL) ALL)"
  fi
done

check_dir() {
  # $1 = katalog, $2 = oczekiwane "tryb właściciel:grupa"
  if [ -d "$1" ]; then
    actual=$(stat -c '%a %U:%G' "$1")
    say "katalog $1: $actual"
    [ "$actual" = "$2" ] || bad "$1 ma $actual, oczekiwane $2"
  else
    bad "brak katalogu $1"
  fi
}
check_dir /opt/pasnik "755 deploy:deploy"
check_dir /opt/pasnik/releases "755 deploy:deploy"
check_dir /opt/pasnik/shared "755 deploy:deploy"
check_dir /opt/pasnik/shared/uv-cache "755 deploy:deploy"
check_dir /opt/pasnik/shared/uploads "750 pasnik:pasnik"
check_dir /opt/pasnik/shared/backups "750 pasnik:pasnik"
check_dir /etc/pasnik "750 root:pasnik"
check_dir /usr/local/lib/pasnik "755 root:root"

if [ -f /etc/sudoers.d/60-pasnik-deploy ] && visudo -cf /etc/sudoers.d/60-pasnik-deploy >/dev/null 2>&1; then
  say "sudoers: /etc/sudoers.d/60-pasnik-deploy poprawny (visudo -cf)"
else
  bad "brak albo błędny /etc/sudoers.d/60-pasnik-deploy"
fi

if sshd -T 2>/dev/null | grep -qx 'passwordauthentication no'; then
  say "sshd: PasswordAuthentication no (ok)"
else
  bad "sshd przyjmuje hasła albo konfiguracji nie da się odczytać"
fi
rootlogin=$(sshd -T 2>/dev/null | awk '$1 == "permitrootlogin" { print $2 }')
case "$rootlogin" in
  prohibit-password|without-password) say "sshd: PermitRootLogin $rootlogin (tylko kluczem)" ;;
  no) say "sshd: PermitRootLogin no — provision Ansible tu nie wejdzie (PROVISION_PUBKEY pusty?)" ;;
  *) bad "sshd: PermitRootLogin ${rootlogin:-nieznane} — root może wejść hasłem" ;;
esac
if [ -s /root/.ssh/authorized_keys ]; then
  say "klucz roota: obecny (provision Ansible ma czym wejść)"
else
  say "klucz roota: brak — provision Ansible wymaga PROVISION_PUBKEY przy tworzeniu maszyny"
fi

# Zegar kontenera = zegar HOSTA (systemd-timesyncd ma ConditionVirtualization=!container).
if [ "$(systemd-detect-virt --container 2>/dev/null || printf none)" != "none" ]; then
  say "zegar: dziedziczony z hosta ($(systemd-detect-virt --container)); NTP to zadanie hosta"
  say "czas w kontenerze: $(date -u '+%Y-%m-%d %H:%M:%SZ')"
elif systemctl is-active --quiet systemd-timesyncd; then
  say "NTP: systemd-timesyncd aktywny"
else
  bad "NTP nieaktywny na maszynie, która nie jest kontenerem"
fi

size=$(du -sxm / 2>/dev/null | cut -f1)
say "rootfs: ${size} MB"
say "pakiety zainstalowane: $(dpkg-query -W -f='${Status}\n' 2>/dev/null | grep -c 'install ok installed')"

if [ "$fail" -eq 0 ]; then
  say "SAMOTEST: OK"
else
  say "SAMOTEST: BŁĄD"
fi
exit "$fail"
# PASNIK-SELFTEST-END
PASNIK_SELFTEST
sed -i "s/@UV_VERSION@/${UV_VERSION}/g" "$SELFTEST_PATH"
chmod 0755 "$SELFTEST_PATH"
exec "$SELFTEST_PATH"
