"""Lokalny runner DB Linux: guardy i kontrakt Dockera bez uruchamiania procesów."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import Mock
from urllib.parse import urlsplit

import pytest

from scripts import db_tests_linux

pytestmark = pytest.mark.unit

# Wyłącznie syntetyczne poświadczenia testu (znaki wymagające kodowania URL).
TEST_URL = "postgresql+psycopg://user%40name:fake%3Apass%40word@127.0.0.1:5433/pasnik_ux_test"
IMAGE = "sha256:" + "a" * 64
CONTAINER = "b" * 64


@pytest.fixture
def caller_root(tmp_path: Path) -> Path:
    """Osobny worktree callera, niezależny od bind mounta działającego app."""
    root = tmp_path / "caller worktree"
    (root / "backend").mkdir(parents=True)
    (root / "docker").mkdir()
    (root / "docker" / "compose.dev.yml").touch()
    (root / ".env").touch()
    return root


@pytest.fixture
def docker_mock(monkeypatch: pytest.MonkeyPatch) -> Mock:
    process = Mock(
        side_effect=[
            subprocess.CompletedProcess([], 0, IMAGE + "\n"),
            subprocess.CompletedProcess([], 0, CONTAINER + "\n"),
            subprocess.CompletedProcess([], 0),
        ]
    )
    monkeypatch.setattr("scripts.db_tests_linux.subprocess.run", process)
    return process


@pytest.mark.parametrize(
    ("app_env", "url"),
    [
        ("prod", TEST_URL),
        ("PROD", TEST_URL),
        ("", TEST_URL),
        ("dev", ""),
        ("dev", TEST_URL.replace("127.0.0.1", "remote.example")),
        ("dev", TEST_URL.replace("127.0.0.1", "localhost.example")),
        ("dev", TEST_URL.replace("pasnik_ux_test", "pasnik_ux")),
        ("dev", TEST_URL.replace("pasnik_ux_test", "pasnik")),
        ("dev", TEST_URL + "?host=remote.example"),
        ("dev", TEST_URL + "?dbname=pasnik_ux"),
        ("dev", TEST_URL + "#fragment"),
        ("dev", TEST_URL.replace(":5433/", ":invalid/")),
        ("dev", TEST_URL.replace("postgresql+psycopg", "https")),
        ("dev", "\n" + TEST_URL),
    ],
)
def test_niebezpieczny_cel_odrzucony_przed_subprocess(
    caller_root: Path, docker_mock: Mock, app_env: str, url: str
) -> None:
    """Prod, zdalna baza i baza dev nie mogą uruchomić nawet odczytu Dockera."""
    with pytest.raises(ValueError) as error:
        db_tests_linux.run(
            caller_root, "integration", [], {"APP_ENV": app_env, "TEST_DATABASE_URL": url}
        )
    docker_mock.assert_not_called()
    assert "fake" not in str(error.value)
    assert "user%40name" not in str(error.value)


@pytest.mark.parametrize("database", ["pasnik_test", "pasnik_ux_test"])
@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_lokalny_url_zachowuje_zakodowane_credentials(database: str, host: str) -> None:
    """Zmienia się tylko adres transportu, nie login, hasło ani nazwa test DB."""
    source = TEST_URL.replace("127.0.0.1", host).replace("pasnik_ux_test", database)
    actual_database, target = db_tests_linux.validate_database_target(
        {"APP_ENV": "test", "TEST_DATABASE_URL": source}
    )
    parsed = urlsplit(target)
    assert actual_database == database
    assert parsed.hostname == "db-test"
    assert parsed.port == 5432
    assert parsed.username == "user%40name"
    assert parsed.password == "fake%3Apass%40word"
    assert parsed.path == f"/{database}"


@pytest.mark.parametrize("suite", ["integration", "api"])
@pytest.mark.parametrize("exit_code", [0, 1, 5, 130])
def test_kontener_callera_przekazuje_cli_env_i_kod_wyjscia(
    caller_root: Path,
    docker_mock: Mock,
    capsys: pytest.CaptureFixture[str],
    suite: str,
    exit_code: int,
) -> None:
    """Nowy disposable run używa backendu callera i credentials tylko w env."""
    docker_mock.side_effect = [
        subprocess.CompletedProcess([], 0, IMAGE),
        subprocess.CompletedProcess([], 0, CONTAINER),
        subprocess.CompletedProcess([], exit_code),
    ]
    environment = {
        "APP_ENV": "dev",
        "TEST_DATABASE_URL": TEST_URL,
        "DATABASE_URL": "dev-secret",
        "UPLOADS_DIR": "data/uploads",
    }
    cli = ["tests/api/planning/test_recipe_scheduling_api.py", "-k", "last recipe", "-q"]
    assert db_tests_linux.run(caller_root, suite, cli, environment) == exit_code
    assert environment["TEST_DATABASE_URL"] == TEST_URL
    assert environment["DATABASE_URL"] == "dev-secret"
    calls = docker_mock.call_args_list
    assert len(calls) == 3
    compose = [
        "docker",
        "compose",
        "--env-file",
        str(caller_root / ".env"),
        "-f",
        str(caller_root / "docker" / "compose.dev.yml"),
    ]
    assert calls[0].args[0] == [*compose, "images", "-q", "app"]
    assert calls[1].args[0] == [*compose, "ps", "-q", "app"]
    command = calls[2].args[0]
    assert command[:6] == [
        "docker",
        "run",
        "--rm",
        "--init",
        "--pull=never",
        f"--network=container:{CONTAINER}",
    ]
    assert command[command.index("--mount") + 1] == (
        f"type=bind,source={caller_root / 'backend'},target=/app,readonly"
    )
    assert command.count("--mount") == 1
    assert command[command.index("--env-file") + 1] == str(caller_root / ".env")
    assert command[-(7 + len(cli)) :] == [
        "uv",
        "run",
        "--frozen",
        "pytest",
        "-m",
        suite,
        "--tb=short",
        *cli,
    ]
    for name in ("TEST_DATABASE_URL", "DATABASE_URL", "UPLOADS_DIR"):
        assert ["-e", name] == command[command.index(name) - 1 : command.index(name) + 1]
    for cache in ("/app/.venv", "/app/.pytest_cache", "/app/.hypothesis"):
        assert command[command.index(cache) - 1] == "--tmpfs"
    for call in calls:
        assert call.kwargs["cwd"] == caller_root
        assert call.kwargs.get("shell", False) is False
        assert call.kwargs.get("check", False) is False
        env = call.kwargs["env"]
        assert env["DATABASE_URL"] == env["TEST_DATABASE_URL"]
        assert urlsplit(env["DATABASE_URL"]).hostname == "db-test"
        assert env["UV_PROJECT_ENVIRONMENT"] == "/opt/venv"
        assert env["UV_CACHE_DIR"] == "/tmp/uv-cache"
        assert env["UPLOADS_DIR"] == "/tmp/pasnik-test-uploads"
        assert all(secret not in str(call.args) for secret in ("fake", "user%40name", "dev-secret"))
    output = capsys.readouterr()
    assert output.out == f"DB tests: database=pasnik_ux_test suite={suite} platform=linux\n"
    assert output.err == ""


def test_main_zachowuje_argumenty_po_separatorze_i_exitcode(
    caller_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLI usuwa własny separator i zostawia flagi pytesta oraz jego kod."""
    runner = Mock(return_value=5)
    monkeypatch.setattr(db_tests_linux, "run", runner)
    assert db_tests_linux.main(["--root", str(caller_root), "api", "--", "-k", "a b"]) == 5
    assert runner.call_args.args[:3] == (caller_root, "api", ["-k", "a b"])


@pytest.mark.parametrize("failure", [OSError("fake-password"), ValueError("fake-password")])
def test_main_nie_loguje_wyjatku_ani_credentials(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], failure: Exception
) -> None:
    """Błędy procesu nie odsłaniają argv/env ani haseł w komunikacie CLI."""
    monkeypatch.setattr(db_tests_linux, "run", Mock(side_effect=failure))
    assert db_tests_linux.main(["--root", ".", "api"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "fake-password" not in output.err
    assert "Traceback" not in output.err


@pytest.mark.parametrize("stdout", ["", IMAGE + "\n" + IMAGE])
def test_brak_jednego_lokalnego_obrazu_nie_uruchamia_testow(
    caller_root: Path, docker_mock: Mock, stdout: str
) -> None:
    """Nie ma budowania/pull ani zgadywania obrazu, gdy dev app jest niedostępny."""
    docker_mock.side_effect = [subprocess.CompletedProcess([], 0, stdout)]
    with pytest.raises(ValueError):
        db_tests_linux.run(
            caller_root, "api", [], {"APP_ENV": "dev", "TEST_DATABASE_URL": TEST_URL}
        )
    assert docker_mock.call_count == 1


def test_blad_compose_nie_przekazuje_stderr(
    caller_root: Path, docker_mock: Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Nawet błąd narzędzia zawierający dane env zostaje zastąpiony stałym tekstem."""
    docker_mock.side_effect = [subprocess.CompletedProcess([], 1, "", TEST_URL)]
    with pytest.raises(ValueError) as error:
        db_tests_linux.run(
            caller_root, "api", [], {"APP_ENV": "dev", "TEST_DATABASE_URL": TEST_URL}
        )
    assert "fake" not in str(error.value)
    assert capsys.readouterr().out == ""
