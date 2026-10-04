"""Reguły katalogu `deploy/` (B18a) pilnowane mechanicznie.

Deploy jest jedynym miejscem w całym łańcuchu, w którym pojawiają się wartości
sekretów, i jedynym, które dotyka uprawnień na żywej maszynie. Testy czytają
pliki — niczego nie wdrażają, nie potrzebują Ansible, SSH ani sieci.

Cztery rodziny reguł:

* **zgodność z kodem** — `pasnik.env.j2` wymienia każde pole `Settings`
  (rozjazd = usługa wstanie na domyślnych wartościach, których nikt nie wybrał);
* **zgodność z maszyną** — każde `sudo` w zadaniach deployu mieści się w wąskiej
  liście z `deploy/lxc/provision.sh` (inaczej deploy pada dopiero na hoście,
  w połowie wydania);
* **sekrety** — wykluczenia rsynca i guard release'u obejmują te same pliki,
  a szablon env nie ma wartości, które systemd i powłoka czytałyby inaczej;
* **decyzje** — ADR-017 (bez Dockera w LXC, PG 16, usługa jako nie-root),
  07_SECURITY §7 (`FORWARDED_ALLOW_IPS` bez `*`), jedno źródło flag uvicorna.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]  # PyYAML dochodzi przez uvicorn[standard]; bez stubów

from app.core.config import Settings

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
DEPLOY = REPO_ROOT / "deploy"
GROUP_VARS = DEPLOY / "group_vars"
TASKS = DEPLOY / "tasks"
TEMPLATES = DEPLOY / "templates"
PROVISION_SH = DEPLOY / "lxc" / "provision.sh"
SERVE_SH = REPO_ROOT / "backend" / "scripts" / "serve.sh"

PLAYBOOKS = (
    "playbook-provision.yml",
    "playbook-deploy.yml",
    "playbook-rollback.yml",
    "playbook-caddy-vhost.yml",
)

#: Pola `Settings`, których NIE ma w `pasnik.env.j2`, z uzasadnieniem. Każda
#: kolejna pozycja wymaga zdania „dlaczego" — inaczej szablon zaczyna żyć własnym życiem.
ENV_TEMPLATE_ALLOWLIST = {
    # Wersję release'u podaje `serve.sh` z pliku VERSION w `current/`: zmienia się
    # z każdym deployem, a `pasnik.env` powstaje RAZ (09 §2, health.version).
    "APP_VERSION": "wersja z pliku VERSION release'u, nie z env",
}

#: Zmienne w `pasnik.env.j2`, które NIE są polami `Settings`, bo czyta je sam
#: uvicorn / `serve.sh` — każda musi być opisana w nagłówku `serve.sh`.
NON_SETTINGS_ENV_KEYS = {"UVICORN_WORKERS", "FORWARDED_ALLOW_IPS"}

#: Wzorce plików sekretów — jedna lista dla wykluczeń rsynca, guardu release'u
#: i tego testu. Dodanie wzorca tu bez dodania go w `group_vars/all.yml` i
#: `tasks/after-update.yml` zatrzymuje bramkę.
SENSITIVE_GLOBS = (
    ".env",
    ".env.*",
    "*.env",
    ".netrc",
    "*.netrc",
    "*_key",
    "*.pem",
    "*.key",
    "id_rsa",
    "id_rsa.*",
    "id_ed25519",
    "id_ed25519.*",
    "id_ecdsa",
    "id_ecdsa.*",
    "known_hosts",
    "known_hosts.*",
    "authorized_keys",
    "*vault*",
    "pasnik.env",
    "pgpass",
)

UVICORN_FLAGS = ("--proxy-headers", "--timeout-worker-healthcheck", "--no-server-header")


def _yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _without_comments(path: Path) -> str:
    """Treść pliku bez linii komentarza — testy „czego tu nie ma" patrzą na to, co się WYKONA."""
    return "\n".join(line for line in _text(path).splitlines() if not line.lstrip().startswith("#"))


def _deploy_files() -> list[Path]:
    """Pliki `deploy/` bez `.ansible/` (role i kolekcje z galaxy — poza gitem i bez znaczenia)."""
    found: list[Path] = []
    for root, dirs, files in os.walk(DEPLOY):
        dirs[:] = [d for d in dirs if d != ".ansible"]
        found.extend(Path(root) / name for name in files)
    return found


def _group_vars() -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for name in ("all.yml", "prod.yml"):
        merged.update(_yaml(GROUP_VARS / name))
    return merged


def _render(value: str, variables: dict[str, Any]) -> str:
    """Najprostsze podstawienie `{{ zmienna }}` (bez filtrów) — dość na ścieżki i nazwy usług."""
    for _ in range(8):
        replaced = re.sub(
            r"\{\{\s*(\w+)\s*\}\}",
            lambda m: str(variables.get(m.group(1), m.group(0))),
            value,
        )
        if replaced == value:
            return replaced
        value = replaced
    return value


def _walk_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Wszystkie zadania, także zagnieżdżone w `block`/`rescue`/`always`."""
    found: list[dict[str, Any]] = []
    for task in tasks or []:
        found.append(task)
        for nested in ("block", "rescue", "always"):
            if nested in task:
                found.extend(_walk_tasks(task[nested]))
    return found


def _all_deploy_tasks() -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for path in sorted(TASKS.glob("*.yml")):
        collected.extend(_walk_tasks(_yaml(path)))
    for name in PLAYBOOKS:
        for play in _yaml(DEPLOY / name):
            for section in ("pre_tasks", "tasks", "post_tasks"):
                collected.extend(_walk_tasks(play.get(section, [])))
    return collected


def _env_assignments() -> dict[str, str]:
    """Pary `KLUCZ=wartość` z szablonu env (linie komentarza pomijamy)."""
    values: dict[str, str] = {}
    for line in _text(TEMPLATES / "pasnik.env.j2").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def _marked_block(text: str, name: str) -> str:
    match = re.search(rf"# {name}-BEGIN\n(.*?)# {name}-END", text, flags=re.S)
    assert match, f"brak bloku {name} w provision.sh"
    return match.group(1)


# --- (a) komplet plików ------------------------------------------------------


@pytest.mark.parametrize(
    "relative",
    [
        "ansible.cfg",
        "ansible-run.sh",
        "requirements.yml",
        "inventories/prod/hosts.yml",
        "group_vars/all.yml",
        "group_vars/prod.yml",
        *PLAYBOOKS,
        "tasks/assert-machine.yml",
        "tasks/assert-external-infra.yml",
        "tasks/refresh-host-key.yml",
        "tasks/after-update.yml",
        "tasks/before-symlink.yml",
        "tasks/restart-and-health.yml",
        "templates/pasnik.service.j2",
        "templates/pasnik-backup.service.j2",
        "templates/pasnik-backup.timer.j2",
        "templates/pasnik.env.j2",
        "templates/pgpass.j2",
        "templates/pasnik-cli.sh.j2",
        "templates/caddy-vhost.example.j2",
        "lxc/provision.sh",
        "lxc/create-incus.sh",
    ],
)
def test_katalog_deploy_jest_kompletny(relative: str) -> None:
    """Scenariusz: brakujący plik z karty B18 zatrzymuje bramkę, zanim zrobi to host."""
    assert (DEPLOY / relative).is_file(), f"brak deploy/{relative}"


@pytest.mark.parametrize("name", PLAYBOOKS)
def test_playbooki_sa_poprawnymi_listami_playow(name: str) -> None:
    """Scenariusz: playbook jest listą play-ów z `hosts` i niepustą zawartością."""
    plays = _yaml(DEPLOY / name)
    assert isinstance(plays, list) and plays
    for play in plays:
        assert "hosts" in play
        assert any(play.get(key) for key in ("tasks", "pre_tasks", "roles", "post_tasks"))


def test_pliki_wysylane_na_linuksa_maja_zakonczenia_lf() -> None:
    """Scenariusz: CRLF (checkout z Windows) w skrypcie/unicie/env psuje shebang na hoście."""
    candidates = _deploy_files()
    candidates += [SERVE_SH, REPO_ROOT / "docker" / "entrypoint.sh"]
    crlf = [str(p.relative_to(REPO_ROOT)) for p in candidates if b"\r" in p.read_bytes()]
    assert not crlf, f"CRLF w plikach wysyłanych na Linuksa: {crlf}"


# --- (b) zgodność szablonu env z Settings -------------------------------------


def test_szablon_env_wymienia_kazde_pole_settings() -> None:
    """Scenariusz: nowe pole `Settings` bez wpisu w `pasnik.env.j2` = usługa wstaje na domyślnej
    wartości, której nikt nie wybrał. Reguła z CLAUDE.md §4."""
    template_keys = set(_env_assignments())
    expected = {name.upper() for name in Settings.model_fields} - set(ENV_TEMPLATE_ALLOWLIST)
    missing = expected - template_keys
    assert not missing, f"pola Settings bez wpisu w pasnik.env.j2: {sorted(missing)}"


def test_szablon_env_nie_ustawia_wersji_release() -> None:
    """Scenariusz: APP_VERSION w pasnik.env przykrywałby wersję z pliku VERSION — health
    pokazywałby inny release niż wdrożony."""
    assert "APP_VERSION" not in _env_assignments()
    assert "APP_VERSION" in ENV_TEMPLATE_ALLOWLIST


def test_szablon_env_nie_ma_zmiennych_spoza_settings_i_serve_sh() -> None:
    """Scenariusz: obca zmienna w pliku env jest po cichu ignorowana (extra=ignore) —
    literówka w nazwie wyglądałaby na ustawioną opcję."""
    allowed = {name.upper() for name in Settings.model_fields} | NON_SETTINGS_ENV_KEYS
    unknown = set(_env_assignments()) - allowed
    assert not unknown, f"zmienne poza Settings i serve.sh: {sorted(unknown)}"
    serve_header = _text(SERVE_SH)
    for key in NON_SETTINGS_ENV_KEYS:
        assert key in serve_header, f"{key} nie jest opisany w serve.sh"


def test_szablon_env_nie_ma_wartosci_ze_spacja_ani_cudzyslowem() -> None:
    """Scenariusz: wartość ze spacją albo cudzysłowem czyta systemd inaczej niż powłoka
    (dług nr 1 runnera) — `pasnik-cli` i usługa muszą widzieć to samo."""
    for key, value in _env_assignments().items():
        literal = re.sub(r"\{\{.*?\}\}", "X", value)
        assert not re.search(r"[\s\"'`$\\]", literal), f"{key}: wartość `{value}` niejednoznaczna"
        assert literal, f"{key}: pusta wartość"
    template = _text(TEMPLATES / "pasnik.env.j2")
    assert not re.search(r"^\s*export\s", template, flags=re.M)


def test_szablon_env_ma_absolutne_sciezki_i_prod() -> None:
    """Scenariusz: względny UPLOADS_DIR rozwiązałby się w katalogu release'u i znikał z deployem."""
    values = _env_assignments()
    variables = _group_vars()
    assert values["APP_ENV"] == "prod"
    assert values["UPLOADS_DIR"] == "{{ uploads_dir }}"
    assert _render("{{ uploads_dir }}", variables).startswith("/opt/pasnik/shared/")
    assert _render(values["SPA_DIST_DIR"], variables) == "/opt/pasnik/current/frontend/dist"


def test_forwarded_allow_ips_to_adres_mostu_a_nie_gwiazdka() -> None:
    """Scenariusz: `*` pozwala każdemu, kto dosięgnie portu aplikacji, podstawić adres klienta
    (07_SECURITY §7); zaufany jest wyłącznie adres hosta na moście (źródło połączeń Caddy)."""
    variables = _group_vars()
    assert variables["forwarded_allow_ips"] == "{{ bridge_gateway }}"
    bridge = str(variables["bridge_gateway"])
    assert "*" not in bridge
    # do czasu `create-incus.sh` wartość to strażnik CHANGE_ME, potem adres IPv4
    assert bridge == "CHANGE_ME" or re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", bridge)
    assert "FORWARDED_ALLOW_IPS={{ forwarded_allow_ips }}" in _text(TEMPLATES / "pasnik.env.j2")


def test_adresy_kontenera_i_mostu_sa_wymagane_przez_provision_i_deploy() -> None:
    """Scenariusz: provision z `CHANGE_ME` w ct_ip/bridge_gateway wyrenderowałby zły
    FORWARDED_ALLOW_IPS i zły cel Caddy'ego — musi stanąć w asercji."""
    for name in ("playbook-provision.yml", "playbook-deploy.yml"):
        text = _text(DEPLOY / name)
        assert 'ct_ip: "{{ ct_ip }}"' in text, name
        assert 'bridge_gateway: "{{ bridge_gateway }}"' in text, name
    variables = _group_vars()
    assert variables["app_host"] == "{{ ct_ip }}"
    assert variables["app_host_port"] == 8000


def test_group_vars_niosa_nazwy_sekretow_a_nie_wartosci() -> None:
    """Scenariusz: sekret wpisany do group_vars trafia do repo — tam są wyłącznie `vault_*`
    z domyślnym strażnikiem CHANGE_ME."""
    variables = _group_vars()
    for name, vault in (("db_password", "vault_db_password"), ("secret_key", "vault_secret_key")):
        assert vault in str(variables[name])
        assert "CHANGE_ME" in str(variables[name])
    prod = _text(GROUP_VARS / "prod.yml")
    assert not re.search(r"^\s*(vault_\w+|db_password|secret_key)\s*:", prod, flags=re.M)


# --- (c) jedno źródło flag uvicorna -------------------------------------------


def test_flagi_uvicorna_maja_jedno_zrodlo() -> None:
    """Scenariusz: skopiowane flagi rozjeżdżają się (np. brak `--proxy-headers` na produkcji
    zrobiłby z limitu logowania limit GLOBALNY)."""
    serve = _text(SERVE_SH)
    for flag in UVICORN_FLAGS:
        assert flag in serve, f"serve.sh nie ma {flag}"
    others = [
        p
        for p in [
            REPO_ROOT / "docker" / "entrypoint.sh",
            REPO_ROOT / "docker" / "Dockerfile",
            *_deploy_files(),
        ]
        if p.is_file() and p != SERVE_SH
    ]
    offenders = [
        f"{p.relative_to(REPO_ROOT)}:{flag}"
        for p in others
        for flag in UVICORN_FLAGS
        if flag in _without_comments(p)
    ]
    assert not offenders, f"flagi uvicorna poza serve.sh: {offenders}"


def test_unit_i_entrypoint_wolaja_serve_sh() -> None:
    """Scenariusz: unit i obraz startują TYM SAMYM skryptem."""
    assert "scripts/serve.sh" in _text(TEMPLATES / "pasnik.service.j2")
    assert "serve.sh" in _text(REPO_ROOT / "docker" / "entrypoint.sh")


# --- (d) unit systemd ---------------------------------------------------------


def test_unit_dziala_jako_pasnik_z_hardeningiem() -> None:
    """Scenariusz: usługa NIE jest rootem, czyta konfigurację wyłącznie z EnvironmentFile
    i pisze tylko do uploadów (09 §2)."""
    unit = _without_comments(TEMPLATES / "pasnik.service.j2")
    assert "User={{ app_user }}" in unit
    assert "User=root" not in unit
    assert "EnvironmentFile={{ pasnik_env_file }}" in unit
    for directive in (
        "NoNewPrivileges=yes",
        "ProtectSystem=strict",
        "PrivateTmp=yes",
        "ProtectHome=yes",
    ):
        assert directive in unit
    assert re.findall(r"ReadWritePaths=(.+)", unit) == ["{{ uploads_dir }}"]
    assert "TimeoutStopSec=30" in unit


def test_unit_nie_deklaruje_wersji_ani_sekretow() -> None:
    """Scenariusz: sekret w unicie (czytelnym dla każdego: `systemctl show`) to wyciek."""
    unit = _without_comments(TEMPLATES / "pasnik.service.j2")
    assert "DATABASE_URL" not in unit and "SECRET_KEY" not in unit and "APP_VERSION" not in unit


def test_backup_chodzi_jako_pasnik_z_pgpass_a_nie_haslem_w_env() -> None:
    """Scenariusz: hasło w `Environment=` byłoby widoczne w `systemctl show` — idzie PGPASSFILE."""
    unit = _without_comments(TEMPLATES / "pasnik-backup.service.j2")
    assert "Type=oneshot" in unit and "User={{ app_user }}" in unit
    assert "PGPASSFILE={{ pgpass_file }}" in unit
    assert "PGPASSWORD" not in unit
    timer = _without_comments(TEMPLATES / "pasnik-backup.timer.j2")
    assert "Persistent=true" in timer and "OnCalendar={{ backup_oncalendar }}" in timer
    assert "03:00" in str(_group_vars()["backup_oncalendar"])


def test_pasnik_cli_nie_czyta_env_przez_source() -> None:
    """Scenariusz: `source pasnik.env` czytałby wartość ze spacją inaczej niż systemd
    (dług nr 1 runnera); środowisko ładuje pętla KLUCZ=wartość."""
    script = _without_comments(TEMPLATES / "pasnik-cli.sh.j2")
    assert not re.search(r"(^|\s)(source|\.)\s+[\"$]", script, flags=re.M)
    assert 'export "$key=$value"' in script
    assert "runuser -u" in script and "--release" in script


# --- (e) sekrety w release ------------------------------------------------------


def _rsync_excludes() -> list[str]:
    params = _group_vars()["ansistrano_rsync_extra_params"]
    return [p.removeprefix("--exclude=") for p in params if p.startswith("--exclude=")]


def test_wykluczenia_rsynca_obejmuja_kazdy_wzorzec_sekretu() -> None:
    """Scenariusz: plik `.env`/klucz w drzewie roboczym nie może pojechać na maszynę z F644."""
    excludes = set(_rsync_excludes())
    missing = [glob for glob in SENSITIVE_GLOBS if glob not in excludes]
    assert not missing, f"wzorce sekretów bez wykluczenia rsynca: {missing}"


def test_guard_release_obejmuje_te_same_wzorce_co_rsync() -> None:
    """Scenariusz: wykluczenia to konfiguracja i mogą być skrócone — guard jest DOWODEM
    na tym, co leży na maszynie, więc musi znać te same pliki."""
    tasks = _yaml(TASKS / "after-update.yml")
    find = next(t for t in tasks if "ansible.builtin.find" in t)["ansible.builtin.find"]
    patterns = set(find["patterns"])
    assert patterns >= set(SENSITIVE_GLOBS), sorted(set(SENSITIVE_GLOBS) - patterns)
    assert find["hidden"] is True and find["recurse"] is True


def test_release_z_sekretem_jest_kasowany_przed_assertem() -> None:
    """Scenariusz: assert przerwałby play i zostawił katalog z sekretem na hoście na zawsze."""
    names = [t.get("name", "") for t in _yaml(TASKS / "after-update.yml")]
    delete = next(i for i, n in enumerate(names) if n.startswith("Skasuj release"))
    check = next(i for i, n in enumerate(names) if n.startswith("Release nie zawiera plików"))
    assert delete < check


def test_rsync_kasuje_wykluczone_i_wymusza_prawa() -> None:
    """Scenariusz: bez `--delete-excluded` wzorzec dodany później nie sprząta trwałej kopii
    ansistrano; bez `--chmod` checkout z /mnt/c daje release 0777."""
    params = _group_vars()["ansistrano_rsync_extra_params"]
    assert "--delete-excluded" in params
    assert "--chmod=D755,F644" in params


def test_rsync_nie_wycina_frontend_dist_i_ma_biala_liste() -> None:
    """Scenariusz: `--exclude=dist` z wzorca runnera wycięłoby `frontend/dist`; biała lista
    wpuszcza tylko backend/, frontend/dist/ i VERSION, a reszta (docs, docker, dane) zostaje."""
    params = _group_vars()["ansistrano_rsync_extra_params"]
    assert not any(re.search(r"--exclude=\*?dist\*?$", p) for p in params)
    include_dist = params.index("--include=/frontend/dist/***")
    assert include_dist < params.index("--exclude=/frontend/*")
    assert "--include=/backend/***" in params and "--include=/VERSION" in params
    assert params[-1] == "--exclude=/*"
    # wykluczenia sekretów i śmieci WYGRYWAJĄ z białą listą (pierwsze dopasowanie)
    assert params.index("--exclude=.env") < params.index("--include=/backend/***")
    assert params.index("--exclude=/backend/data") < params.index("--include=/backend/***")
    assert params.index("--exclude=tests") < params.index("--include=/backend/***")


def test_deploy_nie_pisze_do_katalogu_sekretow() -> None:
    """Scenariusz: deploy (kanał bez roota) nie dotyka /etc/pasnik — pliki z sekretami
    zakłada wyłącznie provision."""
    for path in (
        DEPLOY / "playbook-deploy.yml",
        DEPLOY / "playbook-rollback.yml",
        *TASKS.glob("after-update.yml"),
        *TASKS.glob("before-symlink.yml"),
        *TASKS.glob("restart-and-health.yml"),
    ):
        text = _without_comments(path)
        assert 'dest: "{{ pasnik_env_file }}"' not in text, path.name
        assert "template:" not in text, f"{path.name}: deploy nie renderuje szablonów"


def test_pliki_env_i_pgpass_powstaja_raz_i_tylko_przez_provision() -> None:
    """Scenariusz: ponowny provision/deploy nie kasuje sekretów wpisanych na maszynie."""
    provision = _yaml(DEPLOY / "playbook-provision.yml")[0]
    task = next(
        t
        for t in _walk_tasks(provision["tasks"])
        if "ansible.builtin.template" in t and t["ansible.builtin.template"].get("force")
    )
    assert task["ansible.builtin.template"]["force"] == "{{ force_env | bool }}"
    assert task["no_log"] is True
    assert _group_vars()["force_env"] is False


# --- (f) sudo, kanały, interpretery --------------------------------------------


def _sudoers_rules() -> list[tuple[str, list[str]]]:
    """(użytkownik docelowy, polecenie z argumentami) — prosto z `provision.sh`."""
    block = _marked_block(_text(PROVISION_SH), "PASNIK-SUDOERS")
    rules = []
    for line in block.splitlines():
        match = re.match(r"deploy ALL=\((\w+)\) NOPASSWD: (.+)$", line.strip())
        if match:
            rules.append((match.group(1), match.group(2).split()))
    return rules


def _sudo_invocations() -> list[tuple[str, list[str]]]:
    variables = _group_vars()
    found = []
    for task in _all_deploy_tasks():
        command = task.get("ansible.builtin.command")
        argv = command.get("argv") if isinstance(command, dict) else None
        if not argv or argv[0] != "sudo":
            continue
        tokens = [_render(str(part), variables) for part in argv[1:] if part != "-n"]
        runas = "root"
        if tokens[:1] == ["-u"]:
            runas, tokens = tokens[1], tokens[2:]
        found.append((runas, tokens))
    return found


def test_sudoers_deployu_jest_waska_i_ma_swoje_wpisy() -> None:
    """Scenariusz: deploy dostaje wyłącznie wymienione `systemctl` i `pasnik-cli` jako `pasnik`
    — nic z ALL, nic z shellem, `visudo -cf` sprawdza plik na maszynie."""
    provision = _text(PROVISION_SH)
    rules = _sudoers_rules()
    assert ("pasnik", ["/usr/local/bin/pasnik-cli"]) in rules
    for action in ("daemon-reload",):
        assert ("root", ["/usr/bin/systemctl", action]) in rules
    for action in ("start", "stop", "restart", "is-active"):
        assert ("root", ["/usr/bin/systemctl", action, "pasnik"]) in rules
    assert ("root", ["/usr/bin/systemctl", "start", "pasnik-backup"]) in rules
    assert not re.search(r"NOPASSWD:\s*ALL", provision)
    assert "visudo -cf" in provision
    assert not re.search(r"usermod\s+.*-aG\s+sudo|adduser\s+\S+\s+sudo", provision)


def test_kazde_sudo_w_zadaniach_deployu_miesci_sie_w_sudoers() -> None:
    """Scenariusz: zadanie wołające `sudo` czegoś spoza listy padłoby dopiero na hoście."""
    rules = _sudoers_rules()
    invocations = _sudo_invocations()
    assert invocations, "nie znaleziono żadnego sudo — parser zadań się rozjechał"
    for runas, tokens in invocations:
        allowed = any(
            runas == rule_runas
            and tokens[: len(rule)] == rule
            and (len(rule) == 1 or len(tokens) == len(rule))
            for rule_runas, rule in rules
        )
        assert allowed, f"sudo -u {runas} {' '.join(tokens)} nie mieści się w sudoers"


def test_deploy_nie_uzywa_become() -> None:
    """Scenariusz: `become` na kanale deployu oznaczałby roota, którego konto celowo nie ma."""
    for path in (
        DEPLOY / "playbook-deploy.yml",
        DEPLOY / "playbook-rollback.yml",
        *sorted(TASKS.glob("*.yml")),
    ):
        assert not re.search(r"^\s*become\s*:", _without_comments(path), flags=re.M), path.name


def test_prace_uprzywilejowane_ida_kanalem_admina() -> None:
    """Scenariusz: provision i kroki roota wymuszają `ansible_user: admin_user`."""
    for name in ("playbook-provision.yml",):
        play = _yaml(DEPLOY / name)[0]
        assert play["vars"]["ansible_user"] == "{{ admin_user }}"
    deploy_plays = _yaml(DEPLOY / "playbook-deploy.yml")
    root_play = next(
        p for p in deploy_plays if p.get("vars", {}).get("ansible_user") == "{{ admin_user }}"
    )
    assert root_play["hosts"] == "all"
    release_play = next(p for p in deploy_plays if "roles" in p)
    assert "ansible_user" not in release_play.get("vars", {})


def test_interpreter_to_systemowy_python_313() -> None:
    """Scenariusz: venv release'u powstaje z Pythona z obrazu — bez pobierania własnego przez uv."""
    variables = _group_vars()
    assert variables["python_bin"] == "/usr/bin/python3"
    assert variables["python_required"] == "3.13"
    after_update = _text(TASKS / "after-update.yml")
    assert "UV_PYTHON_DOWNLOADS: never" in after_update
    assert "--frozen" in after_update and "--no-dev" in after_update


# --- (g) maszyna, hooki, rollback ---------------------------------------------


def test_provision_sh_przypina_pobrania_skrotem_i_nie_instaluje_dockera() -> None:
    """Scenariusz: binarka uv i klucz PGDG pobrane z sieci muszą mieć przypięty SHA-256;
    w LXC nie ma silnika kontenerów (ADR-017 pkt 1)."""
    provision = _text(PROVISION_SH)
    pins = _marked_block(provision, "PASNIK-PINS")
    assert re.search(r'UV_SHA256="[0-9a-f]{64}"', pins)
    assert re.search(r'PGDG_KEY_SHA256="[0-9a-f]{64}"', pins)
    assert 'PGDG_CLIENT_PACKAGE="postgresql-client-16"' in pins
    packages = _marked_block(provision, "PASNIK-PACKAGES")
    for package in ("python3", "rsync", "openssh-server", "ca-certificates", "sudo", "curl"):
        assert package in packages
    executed = _without_comments(PROVISION_SH)
    assert not re.search(r"apt-get install[^\n]*(docker|podman)", executed)


def test_wersja_uv_w_provision_zgodna_z_dockerfile() -> None:
    """Scenariusz: ten sam minor uv w obrazie i na maszynie — `uv sync --frozen` ma dawać
    ten sam wynik (brief B18, Stage 2)."""
    dockerfile = _text(REPO_ROOT / "docker" / "Dockerfile")
    image_minor = re.search(r"astral-sh/uv:(\d+\.\d+)", dockerfile)
    assert image_minor
    pinned = re.search(r'UV_VERSION="(\d+\.\d+)\.\d+"', _text(PROVISION_SH))
    assert pinned
    assert pinned.group(1) == image_minor.group(1)


def test_dev_i_test_na_postgres_16_jak_klaster_produkcyjny() -> None:
    """Scenariusz: parytet z `postgres-apps` (16) — dump klienta 17 nie zawsze wraca na 16."""
    for relative in (
        "docker/compose.dev.yml",
        "docker/compose.test.yml",
        "docker/backup/Dockerfile",
    ):
        text = _without_comments(REPO_ROOT / relative)
        assert "postgres:17" not in text, relative
        assert "postgres:16" in text, relative


def test_hooki_deployu_sa_podpiete_pod_prawidlowe_nazwy_zmiennych() -> None:
    """Scenariusz: rola rollback ma WŁASNE nazwy hooków (`ansistrano_rollback_*`); wzorzec
    runnera podpinał hook pod nazwę deployu i jego rollback nie sprawdzał zdrowia."""
    deploy = _text(DEPLOY / "playbook-deploy.yml")
    for hook, task_file in (
        ("ansistrano_after_update_code_tasks_file", "after-update.yml"),
        ("ansistrano_before_symlink_tasks_file", "before-symlink.yml"),
        ("ansistrano_after_symlink_tasks_file", "restart-and-health.yml"),
    ):
        assert re.search(rf"{hook}:.*{re.escape(task_file)}", deploy), hook
    rollback = _text(DEPLOY / "playbook-rollback.yml")
    assert re.search(
        r"ansistrano_rollback_after_symlink_tasks_file:.*restart-and-health\.yml", rollback
    )
    assert "ansistrano.rollback" in rollback and "releases.matched >= 2" in rollback


def test_before_symlink_robi_dump_przed_migracja_i_asertuje_zestaw() -> None:
    """Scenariusz: migracja bez świeżego, niepustego dumpu to jedyna droga do utraty danych."""
    names = [t.get("name", "") for t in _yaml(TASKS / "before-symlink.yml")]
    dump = next(i for i, n in enumerate(names) if n.startswith("Dump bazy przed migracją"))
    assert_set = next(i for i, n in enumerate(names) if n.startswith("Zestaw ma dump"))
    migrate = next(i for i, n in enumerate(names) if n.startswith("Migracja bazy"))
    assert dump < assert_set < migrate
    text = _text(TASKS / "before-symlink.yml")
    assert "-size" in text and "--release" in text
    # `+0` bez cudzysłowu YAML czyta jako liczbę 0 → `find -size 0` szuka plików PUSTYCH
    find_task = next(
        t
        for t in _yaml(TASKS / "before-symlink.yml")
        if t.get("name", "").startswith("Nowy, niepusty")
    )
    argv = find_task["ansible.builtin.command"]["argv"]
    assert argv[argv.index("-size") + 1] == "+0"


def test_health_po_deployu_jest_asertowany_na_tresc_i_wersje() -> None:
    """Scenariusz: `degraded` to też HTTP 200 — sam kod przepuściłby nieudaną migrację."""
    text = _text(TASKS / "restart-and-health.yml")
    assert "health.json.status == 'ok'" in text
    assert "health.json.version == expected_version" in text
    assert "checks.migrations == 'ok'" in text.replace("health.json.", "")
    assert "/api/docs" in text and "status_code: 404" in text
    assert "journalctl" in text and 'ansible_user: "{{ admin_user }}"' in text


def test_strazniki_stechlego_dista_po_obu_stronach() -> None:
    """Scenariusz: kod z innego commita niż frontend = stary UI nad nowym API."""
    deploy = _text(DEPLOY / "playbook-deploy.yml")
    assert "build-info.json" in deploy and "release_version_final" in deploy
    assert "build-info.json" in _text(TASKS / "after-update.yml")
    vite = _text(REPO_ROOT / "frontend" / "vite.config.ts")
    assert "build-info.json" in vite and "git describe --tags --always --dirty" in vite


def test_wrappery_taskfile_wolaja_ansible_przez_skrypt_w_wsl() -> None:
    """Scenariusz: `task deploy` zależy od fe-build i secrets-scan, a `ANSIBLE_CONFIG` jest
    ustawiany (checkout na /mnt/c bywa przez Ansible ignorowany)."""
    taskfile = _yaml(REPO_ROOT / "Taskfile.yml")["tasks"]
    for name in ("provision", "deploy", "rollback", "deploy-syntax", "deploy-galaxy"):
        assert name in taskfile, name
    deploy_cmds = taskfile["deploy"]["cmds"]
    assert deploy_cmds[0] == {"task": "fe-build"}
    assert deploy_cmds[1] == {"task": "secrets-scan"}
    assert deploy_cmds[2].startswith("{{.ANSIBLE_SH}} deploy")
    assert "ansible-run.sh" in _text(REPO_ROOT / "Taskfile.yml")
    run = _text(DEPLOY / "ansible-run.sh")
    assert "ANSIBLE_CONFIG=ansible.cfg" in run and ".venvs/ansible" in run
    assert "-i inventories/prod" in run


def test_blok_caddy_nie_wlacza_logu_i_ma_krotki_hsts() -> None:
    """Scenariusz: `log` zapisałby publiczny token listy w access logu hosta (D7 pkt 3)."""
    vhost = _without_comments(TEMPLATES / "caddy-vhost.example.j2")
    assert not re.search(r"^\s*log\b", vhost, flags=re.M)
    assert "reverse_proxy {{ app_host }}:{{ app_host_port }}" in vhost
    assert "Strict-Transport-Security" in vhost and "{{ hsts_max_age }}" in vhost
    assert int(_group_vars()["hsts_max_age"]) <= 3600
    assert "import " not in vhost


def test_lxc_nie_wystawia_portu_aplikacji_w_lan() -> None:
    """Scenariusz: Caddy jest na tym samym hoście i łączy się z kontenerem po moście —
    proxy device aplikacji (DNAT/`nat=true`) otwierałby port w LAN bez potrzeby (D30)."""
    create = _without_comments(DEPLOY / "lxc" / "create-incus.sh")
    assert "nat=true" not in create
    assert not re.search(r"device add .* app\b", create)
    assert "device override" in create and "ipv4.address" in create
    assert "ssh-keygen -lf" in create
    assert "security.nesting" not in create
    assert "bridge_gateway" in create and "ct_ip" in create


def test_zapora_hosta_zamyka_nowe_polaczenia_do_mostu() -> None:
    """Scenariusz: reguła DROP dla NOWYCH przekazywanych połączeń do mostu stoi na pozycji 1
    DOCKER-USER, a wyjście kontenera i odpowiedzi są przepuszczone (inaczej Docker odcina NAT)."""
    firewall = _without_comments(DEPLOY / "lxc" / "host-firewall.sh")
    assert 'ensure_first -o "$BRIDGE" -m conntrack --ctstate NEW -j DROP' in firewall
    assert 'ensure_present -i "$BRIDGE" -j ACCEPT' in firewall
    assert "RELATED,ESTABLISHED" in firewall
    assert "After=docker.service" in firewall and "PartOf=docker.service" in firewall


def _keys_with_jinja(node: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and "{{" in key:
                found.append(f"{path}/{key}")
            found.extend(_keys_with_jinja(value, f"{path}/{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_keys_with_jinja(value, f"{path}[{index}]"))
    return found


def test_klucze_slownikow_w_playbookach_nie_zawieraja_jinja() -> None:
    """Scenariusz: Ansible nie przepuszcza KLUCZY słowników przez Jinja — `{{ deploy_to }}`
    w kluczu zostaje literałem i asercja pada dopiero na hoście (błąd z pierwszego provisionu)."""
    offenders: list[str] = []
    for path in [*sorted(TASKS.glob("*.yml")), *(DEPLOY / name for name in PLAYBOOKS)]:
        offenders += [f"{path.name}:{hit}" for hit in _keys_with_jinja(_yaml(path))]
    assert not offenders, offenders
