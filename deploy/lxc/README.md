# `deploy/lxc/` — maszyna Paśnika jako plik (host 192.168.2.121)

Trzy pliki opisują **całą maszynę**, na której chodzi Paśnik, i stawiają ją
**jednym poleceniem**. Aplikacji i sekretów tu nie ma — te wjeżdżają osobno
(Ansible, `deploy/README.md`), więc odtworzenie maszyny nigdy nie wymaga hasła.

> **Host: 192.168.2.121 (decyzja D30).** D29 wskazywał Odroida .111, ale
> właściciel postawił kontener na hoście, na którym stoją już Caddy i klaster
> `postgres-apps` (Docker). Skutek: Caddy łączy się z kontenerem WPROST po moście
> Incusa — bez proxy device'a aplikacji, bez DNAT-a i bez portu w LAN.

| Plik | Do czego |
|---|---|
| `provision.sh` | **instalator maszyny**, jako root w gotowym kontenerze Debian 13: pakiety, `uv`, `postgresql-client-16` z PGDG, użytkownicy `deploy`/`pasnik`, katalogi, `sshd`, sudoers, samotest `/usr/local/sbin/pasnik-selftest`. Idempotentny |
| `create-incus.sh` | **na hoście**: `incus init` ze STATYCZNYM IPv4, `provision.sh`, proxy device SSH (dla Ansible z WSL), migawka `czysty`, **odcisk klucza hosta SSH** i wartości `ct_ip`/`bridge_gateway` do `group_vars/prod.yml` |
| `host-firewall.sh` | **na hoście**: reguły `DOCKER-USER` dla mostu Incusa (wyjście kontenera + zamknięcie nowych połączeń do mostu) i unit utrwalający je po restarcie |

Wszystko, co dzieje się **na hoście**, wykonuje **właściciel**; agent i Ansible
mają wyłącznie kontener po SSH. Każda komenda niżej jest do wklejenia.

## 0. Topologia (09_DEPLOYMENT §1)

```
Internet ─► Caddy (host .121, TLS) ─► <ct_ip>:8000 (po moście incusbr0) ─► LXC `pasnik` (uvicorn, User=pasnik)
Operator (WSL) ─► 192.168.2.121:2223 ─proxy device─► LXC:22
LXC ─► 192.168.2.121:5432 (postgres-apps, baza ffp_db — ten sam host)
```

Źródłem połączeń Caddy → kontener jest adres hosta na moście
(`bridge_gateway`, np. `10.x.y.1`), więc to on jest jedynym zaufanym w
`FORWARDED_ALLOW_IPS`. Port **2223** (SSH) to PROPOZYCJA — potwierdź go
w sekcji 1; gdy zajęty, zmień w `inventories/prod/hosts.yml` i podaj
`PASNIK_LXC_SSH_PORT` do `create-incus.sh`.

## 1. Odczyt hosta (nic nie zmienia) — wklej wynik do sesji

```bash
hostname -I | tr ' ' '\n' | head -2
incus version && incus network show incusbr0
incus list -c n4s
sudo ss -ltnp | grep -E ':(22|2222|2223|80|443|5432)\b'
docker ps --format '{{.Names}} {{.Ports}}'
sudo iptables -S DOCKER-USER; sudo iptables -S FORWARD | head -3
sudo ufw status verbose
sysctl -n net.ipv4.ip_forward
```

Co z tego wynika:

- `ss`: 2223 musi być WOLNY. 80/443 trzyma Caddy, 5432 klaster (Docker).
- `incus network show incusbr0`: `ipv4.address` (np. `10.53.158.1/24`) wyznacza
  podsieć; `create-incus.sh` bierze domyślnie adres `.201` z niej
  (`PASNIK_LXC_IPV4` nadpisuje) i wypisuje na końcu `ct_ip` oraz `bridge_gateway`.
- `ufw status`: jeśli AKTYWNY — sekcja 3 (reguły dla `incusbr0`).
- Podsieci Dockera (172.17–25.x) nie kolidują z `incusbr0`, jeśli jest to 10.x.

## 2. Postawienie kontenera

Kolejność na hoście (raz): `sudo incus admin init --minimal`, ponowne
zalogowanie (grupa `incus-admin`), potem skrypty:

```bash
scp deploy/lxc/{create-incus.sh,provision.sh,host-firewall.sh} <użytkownik>@192.168.2.121:~/pasnik-lxc/
```

```bash
cd ~/pasnik-lxc && chmod +x *.sh && OPERATOR_PUBKEY="$(cat ~/.ssh/id_rsa.pub)" ./create-incus.sh
```

(Klucz publiczny z WSL — ten, którym Ansible będzie wchodził jako `deploy`
i `root`. Klucz **publiczny** jest parametrem; w repo go nie zapisujemy.)

Domyślnie: kontener `pasnik`, `images:debian/13`, 2 vCPU, 2 GiB, adres `.201`
w podsieci `incusbr0`, proxy SSH `0.0.0.0:2223 → 127.0.0.1:22`, migawka
`czysty`. Skrypt kończy się **samotestem** (`SAMOTEST: OK`), **odciskiem klucza
hosta SSH** i blokiem „WPISZ do prod.yml" — wklej cały wynik do sesji.

| Sytuacja | Polecenie |
|---|---|
| odtworzenie po awarii | `./create-incus.sh --recreate` (potem `-e refresh_host_key=true`, sekcja 4) |
| powrót do stanu sprzed deployu | `incus snapshot restore pasnik czysty` |
| ponowne sprawdzenie maszyny | `incus exec pasnik -- /usr/local/sbin/pasnik-selftest` |
| konsola awaryjna (SSH nie działa) | `incus exec pasnik -- bash` |
| skasowanie | `incus delete --force pasnik` |

Kontener bez dostępu do internetu zaraz po starcie (krok 5 skryptu pada) =
Docker (`FORWARD DROP`) odcina NAT mostu: nałóż `host-firewall.sh` (sekcja 3)
i uruchom `create-incus.sh --recreate`.

## 3. Zapora na hoście: Docker i ufw

**Docker** ustawia `iptables -P FORWARD DROP` i odcina NAT mostu Incusa
(kontener nie dosięga ani apt, ani PyPI, ani GitHuba). Reguły trzeba nałożyć
w `DOCKER-USER` i **utrwalić** — po restarcie hosta znikają. Robi to
`host-firewall.sh`: pozycja 1 = DROP nowych połączeń PRZEKAZYWANYCH do mostu
(obrona w głąb — nic z LAN-u nie ma prawa nawiązać połączenia do kontenera
przez ten host), dalej akceptacja wyjścia z mostu i odpowiedzi do niego. Ruch
Caddy → kontener to OUTPUT hosta i tych reguł nie dotyczy.

```bash
incus list pasnik -c 4 --format csv        # → adres kontenera, np. 10.53.158.201 (bez "(eth0)")
```

```bash
cd ~/pasnik-lxc && sudo PASNIK_CT_IP=<adres-kontenera> ./host-firewall.sh --install-unit
```

Unit `pasnik-docker-user.service` nakłada reguły po KAŻDYM starcie Dockera
i hosta (`After=docker.service`, `PartOf=docker.service`).

**ufw** (jeśli aktywny; skrypt go nie zmienia). Incus dokumentuje to tak:
host musi przepuszczać DHCP/DNS od kontenerów i ich ruch na zewnątrz:

```bash
sudo ufw allow in on incusbr0
sudo ufw route allow in on incusbr0
sudo ufw route allow out on incusbr0
sudo ufw allow from 192.168.2.0/24 to any port 2223 proto tcp   # SSH do kontenera z LAN (Ansible z WSL)
```

**Dowody** (kryterium 2): port aplikacji NIE jest wystawiony w LAN — z laptopa
(nie z .121) `Test-NetConnection 192.168.2.121 -Port 8000` ma dać `False`, a
`Test-NetConnection 192.168.2.121 -Port 2223` — `True` (SSH). Z samego hosta:
`curl -s http://<ct_ip>:8000/api/v1/health` → JSON (po pierwszym deployu).

## 4. Odcisk klucza hosta SSH — pierwszy provision wiezie sekrety

Pierwszy przebieg Ansible (`task provision`) przesyła hasło bazy i `SECRET_KEY`,
więc nie może przyjąć dowolnego klucza odpowiadającego na porcie 2223 (dług nr 4
runnera). `create-incus.sh` wypisuje na końcu odcisk i **gotowy wpis
`known_hosts`**. Wklej go do pliku z inwentarza PRZED pierwszym przebiegiem
(WSL):

```bash
echo '[192.168.2.121]:2223 ssh-ed25519 AAAA…(z wyjścia create-incus.sh)' > ~/.ssh/pasnik-prod.hostkeys
```

Plik jest wskazany w `group_vars/prod.yml` (`ssh_host_key_file`); od tej chwili
`StrictHostKeyChecking=accept-new` nie ma czego przypinać, a podmieniony klucz
zatrzyma Ansible. **Po `--recreate`** klucz się zmienia: skasuj plik
(`-e refresh_host_key=true`), wklej NOWY wpis z wyjścia skryptu i dopiero potem
puszczaj Ansible.

## 5. Co jest w maszynie i dlaczego tak mało

Debian 13 (trixie) plus: `python3` (3.13 — spełnia `requires-python >=3.13`),
`rsync` + `openssh-server` (ansistrano, jedyne wejście), `ca-certificates`,
`curl`, `sudo`, **`uv`** w wersji z `docker/Dockerfile` (przypięty SHA-256) i
**`postgresql-client-16`** z PGDG (przypięty skrót klucza; klient 17 z Debiana
13 robi dump, który nie zawsze wraca na serwer 16). **Nie ma** Dockera, Podmana,
nestingu, kompilatora ani przeglądarek — samotest sprawdza brak silnika kontenerów.

Zegar kontenera = zegar HOSTA (`systemd-timesyncd` nie wstaje w kontenerze):
NTP jest zadaniem hosta.

### Użytkownicy i uprawnienia

| Konto | Ma | Nie ma |
|---|---|---|
| `deploy` | SSH kluczem; `sudo NOPASSWD` wyłącznie: `systemctl daemon-reload`, `start\|stop\|restart\|is-active pasnik`, `start pasnik-backup` oraz `sudo -u pasnik /usr/local/bin/pasnik-cli`; właściciel `/opt/pasnik/releases` | hasła, grupy `sudo`, odczytu `/opt/pasnik/shared/{uploads,backups}` i `/etc/pasnik`, journala |
| `root` | SSH **wyłącznie kluczem** (`PermitRootLogin prohibit-password`) — kanał `playbook-provision.yml` | logowania hasłem |
| `pasnik` | konto usługi i backupu (system, `nologin`); właściciel `shared/uploads` i `shared/backups` (0750) | powłoki, hasła, sudo |

> **Klucz `deploy` traktuj jak klucz do SEKRETÓW APLIKACJI.** `deploy`
> jest właścicielem `releases/` i restartuje usługę, a usługa czyta
> `/etc/pasnik/pasnik.env` (hasło bazy). Podmiana kodu w release + restart daje
> dostęp do tych sekretów (nie do roota maszyny: `deploy` nie zostaje rootem).
> Domyślnie `PROVISION_PUBKEY` jest tym samym kluczem — rozdziel, jeśli chcesz,
> żeby ścieżka rutynowa nie niosła kanału roota.

## 6. Weryfikacja

```bash
incus exec pasnik -- /usr/local/sbin/pasnik-selftest; echo "kod=$?"
```

Sprawdza: Python 3.13.x, `uv` w przypiętej wersji, `pg_dump/pg_restore/psql` = 16,
brak Dockera/Podmana, użytkowników i grupy, prawa i właścicieli katalogów
(`stat`), poprawność sudoers (`visudo -cf`), `sshd` bez haseł, tryb logowania
roota, rozmiar rootfs i listę pakietów. Jest też **assertem provisionu
Ansible** (`tasks/assert-machine.yml`) — ten sam plik, nie kopia warunków.

Z WSL, po przekierowaniu portu:

```bash
ssh -p 2223 deploy@192.168.2.121 'python3 --version; uv --version; pg_dump --version'
```

## 7. Po restarcie hosta .121

Kontener wstaje sam (`boot.autostart` domyślnie `true` w Incusie) i dostaje
ten sam adres. Aplikacja widzi bazę dopiero, gdy `pasnik-docker-user.service`
nałożył reguły (`systemctl status pasnik-docker-user`). Objaw braku reguł:
`/api/v1/health` → `degraded` (`checks.db: fail`) albo kontener bez `apt`.
Doraźnie: `sudo systemctl restart pasnik-docker-user`. Runbook:
`docs/OPERATIONS.md` (18b).
