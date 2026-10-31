"""Opt-in Linux dla lokalnych testów DB; wywołanie wyłącznie przez Taskfile."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def validate_database_target(environment: Mapping[str, str]) -> tuple[str, str]:
    """Sprawdź cel przed Dockerem; poświadczenia pozostają wyłącznie w env."""
    if environment.get("APP_ENV") not in {"dev", "test"}:
        raise ValueError("APP_ENV musi wskazywać dev albo test.")
    value = environment.get("TEST_DATABASE_URL", "")
    try:
        if any(ord(character) <= 32 for character in value):
            raise ValueError
        parsed = urlsplit(value)
        # Parametry libpq (np. host/dbname w query) mogłyby ominąć allowlistę.
        if (
            parsed.scheme not in {"postgres", "postgresql", "postgresql+psycopg"}
            or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.path not in {"/pasnik_ux_test", "/pasnik_test"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError
        _ = parsed.port  # Odrzuć także niepoprawny port, zanim uruchomimy Docker.
    except ValueError:
        raise ValueError(
            "TEST_DATABASE_URL musi wskazywać dozwoloną lokalną bazę testową."
        ) from None
    # Zachowaj zakodowane user/password, w tym znaki specjalne, bez ich dekodowania.
    userinfo, separator, _host = parsed.netloc.rpartition("@")
    authority = f"{userinfo}{separator}db-test:5432"
    return parsed.path[1:], urlunsplit(parsed._replace(netloc=authority))


def _compose_value(command: list[str], root: Path, environment: dict[str, str]) -> str:
    result = subprocess.run(command, cwd=root, env=environment, capture_output=True, text=True)
    if result.returncode:
        # Nie drukuj stderr ani wyjątku subprocess: mogą zawierać konfigurację.
        raise ValueError("Nie można odczytać lokalnego obrazu/kontenera dev app.")
    value = result.stdout.strip()
    if not re.fullmatch(r"(?:sha256:)?[a-f0-9]{12,64}", value):
        raise ValueError("Uruchom lokalny dev app przed testami Linux.")
    return value


def run(root: Path, suite: str, pytest_args: Sequence[str], environment: Mapping[str, str]) -> int:
    """Uruchom nowy kontener z kodem worktree callera i zwróć kod pytesta."""
    database, target = validate_database_target(environment)
    if suite not in {"integration", "api"}:
        raise ValueError("Dozwolone suity: integration albo api.")
    root = root.resolve()
    backend = root / "backend"
    env_file = root / ".env"
    compose_file = root / "docker" / "compose.dev.yml"
    if not backend.is_dir() or not env_file.is_file() or not compose_file.is_file():
        raise ValueError("Brak backendu lub konfiguracji lokalnego worktree.")
    child_env = dict(environment)
    child_env.update(
        TEST_DATABASE_URL=target,
        DATABASE_URL=target,
        UV_PROJECT_ENVIRONMENT="/opt/venv",
        UV_CACHE_DIR="/tmp/uv-cache",
        UPLOADS_DIR="/tmp/pasnik-test-uploads",
    )
    compose = ["docker", "compose", "--env-file", str(env_file), "-f", str(compose_file)]
    image = _compose_value([*compose, "images", "-q", "app"], root, child_env)
    container = _compose_value([*compose, "ps", "-q", "app"], root, child_env)
    command = [
        "docker",
        "run",
        "--rm",
        "--init",
        "--pull=never",
        f"--network=container:{container}",
        "--env-file",
        str(env_file),
        "-e",
        "APP_ENV",
        "-e",
        "TEST_DATABASE_URL",
        "-e",
        "DATABASE_URL",
        "-e",
        "UV_PROJECT_ENVIRONMENT",
        "-e",
        "UV_CACHE_DIR",
        "-e",
        "UPLOADS_DIR",
        "--mount",
        f"type=bind,source={backend},target=/app,readonly",
        "--tmpfs",
        "/app/.venv",
        "--tmpfs",
        "/app/.pytest_cache",
        "--tmpfs",
        "/app/.hypothesis",
        "-w",
        "/app",
        image,
        "uv",
        "run",
        "--frozen",
        "pytest",
        "-m",
        suite,
        "--tb=short",
        *pytest_args,
    ]
    print(f"DB tests: database={database} suite={suite} platform=linux", flush=True)
    return subprocess.run(command, cwd=root, env=child_env).returncode


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("suite", choices=("integration", "api"))
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    pytest_args = args.pytest_args
    if pytest_args[:1] == ["--"]:
        pytest_args = pytest_args[1:]
    try:
        return run(args.root, args.suite, pytest_args, os.environ)
    except (ValueError, OSError):
        # Wyjątki systemowe mogą zawierać argv/env; pokaż wyłącznie stały komunikat.
        print(
            "Nie można uruchomić testów DB Linux; sprawdź lokalny env i dev app.", file=sys.stderr
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
