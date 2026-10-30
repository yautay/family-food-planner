"""Bramki bezpiecznego zestawu UX00 — bez bazy i bez żądań HTTP."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from scripts.ux_baseline import Api, FixtureError, Journal, guard_environment

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "url,environment",
    [
        ("postgresql://u:p@localhost/pasnik", "dev"),
        ("postgresql://u:p@localhost/ffp_db", "dev"),
        ("postgresql://u:p@192.168.2.111/pasnik_ux", "dev"),
        ("postgresql://u:p@localhost.example.com/pasnik_ux", "dev"),
        ("postgresql://u:p@localhost/pasnik_ux?host=remote", "dev"),
        ("postgresql://u:p@localhost/pasnik_ux?service=production", "dev"),
        ("postgresql://u:p@/pasnik_ux", "dev"),
        ("sqlite:///pasnik_ux", "dev"),
        ("postgresql://u:p@localhost/pasnik_ux", "prod"),
    ],
)
def test_guard_odrzuca_zwykla_zdalna_i_produkcyjna_baze(url: str, environment: str) -> None:
    """Nazwa UX nie wystarcza bez lokalnego hosta, trybu dev/test i braku override."""
    settings = Settings(database_url=url, secret_key="unit", app_env=environment)  # type: ignore[arg-type]
    with pytest.raises(FixtureError):
        guard_environment(settings)


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
@pytest.mark.parametrize("database", ["pasnik_ux", "pasnik_ux_test"])
def test_guard_przyjmuje_wylacznie_odrebna_lokalna_baze(host: str, database: str) -> None:
    """Identyfikator manifestu nie zawiera hasła ani nazwy użytkownika."""
    settings = Settings(
        database_url=f"postgresql://operator:secret@{host}:5544/{database}", secret_key="unit"
    )
    identity = guard_environment(settings)
    assert identity.endswith(f":5544/{database}")
    assert "secret" not in identity
    assert "operator" not in identity


async def test_niepotwierdzony_zapis_blokuje_automatyczna_powtorke(tmp_path: Path) -> None:
    """Przerwanie po wysłaniu POST-a wymaga kontroli wyniku zamiast duplikowania encji."""
    path = tmp_path / "manifest.json"
    journal = Journal(path, "localhost/pasnik_ux", "photo")
    api = AsyncMock(spec=Api)
    api.call.side_effect = RuntimeError("Symulowane przerwanie po zapisie")
    with pytest.raises(RuntimeError):
        await journal.write(api, "product-1", "POST", "/products", {"name": "Próbny"})
    with pytest.raises(FixtureError, match="Niepotwierdzona operacja"):
        Journal(path, "localhost/pasnik_ux", "photo")
    api.call.assert_awaited_once()


async def test_potwierdzony_zapis_reuzywa_id_bez_kolejnego_posta(tmp_path: Path) -> None:
    """Drugi setup korzysta z dziennika, ale nie zapisuje payloadu ani sekretów."""
    path = tmp_path / "manifest.json"
    journal = Journal(path, "localhost/pasnik_ux", "photo")
    api = AsyncMock(spec=Api)
    api.call.return_value = {"id": 42, "public_token": "never-persist-this"}
    assert await journal.write(api, "recipe-1", "POST", "/recipes") == 42
    resumed = Journal(path, "localhost/pasnik_ux", "photo")
    assert await resumed.write(api, "recipe-1", "POST", "/recipes") == 42
    api.call.assert_awaited_once()
    assert "never-persist-this" not in path.read_text(encoding="utf-8")


def test_manifest_nie_przechodzi_do_innej_bazy_lub_zdjecia(tmp_path: Path) -> None:
    """ID z innego środowiska nigdy nie są używane do kontynuowania zapisów."""
    path = tmp_path / "manifest.json"
    Journal(path, "localhost/pasnik_ux", "photo").save()
    for database, photo in (
        ("localhost/pasnik_ux_test", "photo"),
        ("localhost/pasnik_ux", "other"),
    ):
        with pytest.raises(FixtureError, match="Manifest dotyczy innej"):
            Journal(path, database, photo)
