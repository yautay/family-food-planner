"""Bramki bezpiecznego zestawu UX00 — bez bazy i bez żądań HTTP."""

from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from scripts.ux_baseline import (
    DAY_TITLES,
    MEAL_NAME,
    PREFIX,
    Api,
    FixtureError,
    Journal,
    Json,
    fixture_loose_item,
    fixture_meal,
    fixture_recipe_item,
    guard_environment,
    repair_manifest_identifiers,
    verify,
)

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


async def test_dayread_nie_zastepuje_id_utworzonego_posilku(tmp_path: Path) -> None:
    """Dzień 34 zawiera posiłek 35; manifest musi zachować ID posiłku."""
    journal = Journal(tmp_path / "manifest.json", "localhost/pasnik_ux", "photo")
    api = AsyncMock(spec=Api)
    api.call.return_value = {"id": 34, "meals": [{"id": 35}]}
    identifier = await journal.write(
        api,
        "meal-0",
        "POST",
        "/plan/days/2029-06-04/meals",
        identifier_from=lambda day: day["meals"][0]["id"],
    )
    assert identifier == 35
    assert Journal(journal.path, "localhost/pasnik_ux", "photo").state.ids["meal-0"] == 35


async def test_blad_rozpoznania_id_zostawia_pending_bez_powtarzania_posta(tmp_path: Path) -> None:
    """Niejednoznaczna odpowiedź po zapisie wymaga ręcznego uzgodnienia wyniku."""
    journal = Journal(tmp_path / "manifest.json", "localhost/pasnik_ux", "photo")
    api = AsyncMock(spec=Api)
    api.call.return_value = {"id": 34, "meals": []}

    def resolve(day: dict[str, object]) -> int:
        raise FixtureError("Niejednoznaczny posiłek")

    with pytest.raises(FixtureError, match="Niejednoznaczny"):
        await journal.write(api, "meal-0", "POST", "/plan/meals", identifier_from=resolve)
    with pytest.raises(FixtureError, match="Niepotwierdzona operacja meal-0"):
        Journal(journal.path, "localhost/pasnik_ux", "photo")
    api.call.assert_awaited_once()


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


@pytest.fixture
def plan_fixture(tmp_path: Path) -> tuple[Journal, AsyncMock, list[Json]]:
    """Niezależne ID dnia, posiłku i pozycji, zgodne z rzeczywistym kształtem DayRead."""
    journal = Journal(tmp_path / "manifest.json", "localhost/pasnik_ux", "photo")
    journal.state.ids = {
        "user-a1": 3,
        "user-a2": 4,
        "household-a": 5,
        "product-0": 9,
        **{f"profile-{i}": 10 + i for i in range(3)},
        **{f"recipe-{i}": 13 + i for i in range(3)},
        **{f"day-{i}": 34 + i for i in range(3)},
        **{f"meal-{i}": 34 + i for i in range(3)},
        **{f"plan-item-{i}": 34 + i for i in range(3)},
        "loose-product": 34,
        "unrelated": 99,
    }
    journal.state.done = list(journal.state.ids)
    journal.state.complete = True
    journal.save()
    days: list[Json] = []
    for offset, count in enumerate((0, 2, 3)):
        suffix = (
            "Pełnoziarnista zapiekanka z pieczoną papryką, cukinią i serem"
            if offset == 0
            else f"Przepis próbny — śniadanie, obiad i kolacja {offset + 1:03}"
        )
        recipe: Json = {
            "id": 70 + offset,
            "recipe_id": 13 + offset,
            "recipe_name": f"{PREFIX} — {offset + 1:03} {suffix}",
            "product_id": None,
            "servings": "2.20" if offset == 1 else "3.30",
            "servings_split": [
                {"member_profile_id": 10 + i, "multiplier": "1.10"} for i in range(count)
            ],
        }
        days.append(
            {
                "id": 34 + offset,
                "day": f"2029-06-0{4 + offset}",
                "title": f"{PREFIX} — {DAY_TITLES[offset]}",
                "scope": "household",
                "owner_user_id": 3,
                "meals": [
                    {"id": 50 + offset, "name": MEAL_NAME, "kcal_target": "600", "items": [recipe]}
                ],
            }
        )
    days[0]["meals"][0]["items"].append(
        {
            "id": 80,
            "recipe_id": None,
            "product_id": 9,
            "product_name": (
                f"{PREFIX} — 001 Płatki owsiane pełnoziarniste z otrębami i pestkami dyni"
            ),
            "amount": "15.000",
            "amount_unit": "g",
            "servings": "1.00",
            "servings_split": [],
        }
    )
    household = {"id": 5, "name": f"{PREFIX} — Dom A"}
    responses: dict[str, Json] = {
        "/auth/me": {
            "id": 3,
            "email": "ux00-a1@example.com",
            "display_name": f"{PREFIX} — konto A1",
            "role": "user",
            "household": household,
        },
        "/households/my": {
            "household": household,
            "members": [{"id": 3}, {"id": 4}],
            "profiles": [{"id": 10 + i, "household_id": 5} for i in range(3)],
        },
        **{f"/plan/days/{day['day']}": day for day in days},
    }

    async def get_only(method: str, path: str, payload: Json | None = None) -> Json:
        assert method == "GET"
        assert payload is None
        return responses[path]

    api = AsyncMock(spec=Api)
    api.call.side_effect = get_only
    return journal, api, days


def family_reader(api: AsyncMock) -> AsyncMock:
    """Drugie konto widzi ten sam rodzinny dzień, ale nie jest jego właścicielem."""

    async def get_only(method: str, path: str, payload: Json | None = None) -> Json:
        response: Json = await api.call.side_effect(method, path, payload)
        if path == "/auth/me":
            return {
                **response,
                "id": 4,
                "email": "ux00-a2@example.com",
                "display_name": f"{PREFIX} — konto A2",
            }
        return response

    reader = AsyncMock(spec=Api)
    reader.call.side_effect = get_only
    return reader


async def test_nowy_plan_zapisuje_id_encji_zamiast_dayread(
    plan_fixture: tuple[Journal, AsyncMock, list[Json]],
) -> None:
    """Rzeczywiste resolvery zapisują osobne ID posiłku, przepisu oraz produktu luzem."""
    journal, api, days = plan_fixture
    journal.state.done = []
    journal.state.complete = False
    api.call.side_effect = None
    api.call.return_value = days[0]
    ids = journal.state.ids
    for key, resolver, expected in (
        ("meal-0", lambda day: fixture_meal(day, ids, 0)["id"], 50),
        ("plan-item-0", lambda day: fixture_recipe_item(day, ids, 0)["id"], 70),
        ("loose-product", lambda day: fixture_loose_item(day, ids)["id"], 80),
    ):
        assert await journal.write(api, key, "POST", "/plan", identifier_from=resolver) == expected
        assert Journal(journal.path, "localhost/pasnik_ux", "photo").state.ids[key] == expected


async def test_verify_odrzuca_stare_id_z_jasna_instrukcja_bez_naprawiania(
    plan_fixture: tuple[Journal, AsyncMock, list[Json]],
) -> None:
    """Samo verify nie zmienia COMPLETE ani błędnych ID i wskazuje opt-in naprawy."""
    journal, api, _ = plan_fixture
    original = journal.path.read_bytes()
    with pytest.raises(FixtureError, match="--repair-manifest-identifiers"):
        await verify(api, {"a2": family_reader(api)}, journal)
    assert journal.path.read_bytes() == original
    assert not journal.path.with_suffix(".identifiers.bak").exists()


async def test_naprawa_wszystkich_id_z_backupem_atomowo_i_idempotentnie(
    plan_fixture: tuple[Journal, AsyncMock, list[Json]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Oryginał istnieje aż do jednego replace, backup zachowuje dokładne bajty manifestu."""
    journal, api, _ = plan_fixture
    original = journal.path.read_bytes()
    original_state = journal.state.model_copy(deep=True)
    backup = journal.path.with_suffix(".identifiers.bak")
    replace = Path.replace
    replacements = []

    def checked_replace(source: Path, target: Path) -> Path:
        assert journal.path.read_bytes() == original
        assert backup.read_bytes() == original
        assert len(api.call.await_args_list) == 5  # Konto, rodzina i wszystkie trzy dni.
        replacements.append(target)
        return replace(source, target)

    monkeypatch.setattr(Path, "replace", checked_replace)
    await repair_manifest_identifiers(api, journal, household_reader=family_reader(api))
    assert replacements == [journal.path]
    expected = original_state.model_copy(deep=True)
    expected.ids.update(
        {
            **{f"meal-{i}": 50 + i for i in range(3)},
            **{f"plan-item-{i}": 70 + i for i in range(3)},
            "loose-product": 80,
        }
    )
    assert journal.state == expected
    assert Journal(journal.path, "localhost/pasnik_ux", "photo").state == expected
    repaired = journal.path.read_bytes()
    await repair_manifest_identifiers(api, journal, household_reader=family_reader(api))
    assert journal.path.read_bytes() == repaired
    assert backup.read_bytes() == original
    assert replacements == [journal.path]
    assert len(api.call.await_args_list) == 10


@pytest.mark.parametrize(
    "case",
    [
        "ambiguous-meal",
        "ambiguous-recipe",
        "ambiguous-product",
        "title",
        "date",
        "day-id",
        "owner",
        "scope",
        "meal-name",
        "recipe",
        "recipe-name",
        "servings",
        "split",
        "product",
    ],
)
async def test_naprawa_odrzuca_niejednoznaczny_lub_obcy_plan_bez_zapisu(
    plan_fixture: tuple[Journal, AsyncMock, list[Json]],
    case: str,
) -> None:
    """Nawet podobna nazwa albo zgadzająca się liczba splitów nie pozwala adoptować danych."""
    journal, api, days = plan_fixture
    original = journal.path.read_bytes()
    day = days[0]
    meal = day["meals"][0]
    recipe = meal["items"][0]
    if case == "ambiguous-meal":
        day["meals"].append(deepcopy(meal))
    elif case == "ambiguous-recipe":
        meal["items"].append(deepcopy(recipe))
    elif case == "ambiguous-product":
        meal["items"].append(deepcopy(meal["items"][1]))
    elif case in {"title", "date", "day-id", "owner", "scope"}:
        field = {"date": "day", "day-id": "id", "owner": "owner_user_id"}.get(case, case)
        day[field] = {
            "title": "Obcy marker",
            "day": "2029-06-07",
            "id": 999,
            "owner_user_id": 999,
            "scope": "private",
        }[field]
    elif case == "meal-name":
        meal["name"] = "Inny obiad"
    elif case == "recipe":
        recipe["recipe_id"] = 999
    elif case == "recipe-name":
        recipe["recipe_name"] = "Obcy marker"
    elif case == "servings":
        recipe["servings"] = "4.40"
    elif case == "split":
        days[1]["meals"][0]["items"][0]["servings_split"][1]["member_profile_id"] = 999
    elif case == "product":
        meal["items"][1]["amount"] = "16"
    with pytest.raises(FixtureError):
        await repair_manifest_identifiers(api, journal, household_reader=family_reader(api))
    assert journal.path.read_bytes() == original
    assert not journal.path.with_suffix(".identifiers.bak").exists()


async def test_blad_trzeciego_dnia_nie_zostawia_czesciowej_naprawy(
    plan_fixture: tuple[Journal, AsyncMock, list[Json]],
) -> None:
    """Błąd najpóźniejszego GET nie zmienia nawet ID pierwszego, poprawnego dnia."""
    journal, api, days = plan_fixture
    original_state = journal.state.model_copy(deep=True)
    original = journal.path.read_bytes()
    days[2]["title"] = "Obcy marker"
    with pytest.raises(FixtureError):
        await repair_manifest_identifiers(api, journal, household_reader=family_reader(api))
    assert len(api.call.await_args_list) == 5
    assert journal.state == original_state
    assert journal.path.read_bytes() == original
    assert not journal.path.with_suffix(".identifiers.bak").exists()


@pytest.mark.parametrize("case", ["household", "owner", "profile-household"])
async def test_naprawa_wymaga_rzeczywistego_konta_i_rodziny_z_manifestu(
    plan_fixture: tuple[Journal, AsyncMock, list[Json]],
    case: str,
) -> None:
    """Ścisły household potwierdzamy kontekstem konta, bo DayRead nie ma household_id."""
    journal, api, _ = plan_fixture
    me = await api.call("GET", "/auth/me")
    family = await api.call("GET", "/households/my")
    if case == "household":
        me["household"] = {"id": 999, "name": f"{PREFIX} — Dom A"}
    elif case == "owner":
        me["id"] = 999
    else:
        family["profiles"][0]["household_id"] = 999
    original = journal.path.read_bytes()
    with pytest.raises(FixtureError, match="Konto lub rodzina"):
        await repair_manifest_identifiers(api, journal, household_reader=family_reader(api))
    assert journal.path.read_bytes() == original


@pytest.mark.parametrize("case", ["a2-id", "a2-household", "day-id", "day-marker"])
async def test_naprawa_wymaga_widocznosci_tych_samych_dni_przez_a2(
    plan_fixture: tuple[Journal, AsyncMock, list[Json]],
    case: str,
) -> None:
    """Dzień musi być widoczny dla dokładnego A2 z rodziny A, także gdy A1 jest właścicielem."""
    journal, api, _ = plan_fixture
    reader = family_reader(api)
    get_only = reader.call.side_effect

    async def changed_read(method: str, path: str, payload: Json | None = None) -> Json:
        response: Json = deepcopy(await get_only(method, path, payload))
        if path == "/auth/me":
            if case == "a2-id":
                response["id"] = 999
            elif case == "a2-household":
                response["household"]["id"] = 999
        elif path == "/plan/days/2029-06-06":
            if case == "day-id":
                response["id"] = 999
            elif case == "day-marker":
                response["title"] = "Obcy marker"
        return response

    reader.call.side_effect = changed_read
    original = journal.path.read_bytes()
    with pytest.raises(FixtureError):
        await repair_manifest_identifiers(api, journal, household_reader=reader)
    assert journal.path.read_bytes() == original
    assert not journal.path.with_suffix(".identifiers.bak").exists()


async def test_awaria_atomowej_zamiany_zachowuje_manifest_i_backup(
    plan_fixture: tuple[Journal, AsyncMock, list[Json]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Błąd replace nie zmienia ani pliku, ani stanu w pamięci; backup pozostaje dostępny."""
    journal, api, _ = plan_fixture
    original_state = journal.state.model_copy(deep=True)
    original = journal.path.read_bytes()

    def failed_replace(source: Path, target: Path) -> Path:
        raise OSError("Symulowany błąd replace")

    monkeypatch.setattr(Path, "replace", failed_replace)
    with pytest.raises(OSError, match="replace"):
        await repair_manifest_identifiers(api, journal, household_reader=family_reader(api))
    assert journal.path.read_bytes() == original
    assert journal.state == original_state
    assert journal.path.with_suffix(".identifiers.bak").read_bytes() == original


async def test_naprawa_nie_nadpisuje_manifestu_zmienionego_podczas_get(
    plan_fixture: tuple[Journal, AsyncMock, list[Json]],
) -> None:
    """Zmiana pliku przez operatora podczas kontroli nie zostaje utracona."""
    journal, api, _ = plan_fixture
    get_only = api.call.side_effect
    changed = journal.state.model_copy(deep=True)
    changed.ids["unrelated"] = 100
    changed_bytes = changed.model_dump_json(indent=2).encode("utf-8")

    async def concurrent_change(method: str, path: str, payload: Json | None = None) -> Json:
        response: Json = await get_only(method, path, payload)
        if path == "/plan/days/2029-06-06":
            journal.path.write_bytes(changed_bytes)
        return response

    api.call.side_effect = concurrent_change
    with pytest.raises(FixtureError, match="zmienił się podczas"):
        await repair_manifest_identifiers(api, journal, household_reader=family_reader(api))
    assert journal.path.read_bytes() == changed_bytes
    assert not journal.path.with_suffix(".identifiers.bak").exists()


@pytest.mark.parametrize("case", ["pending", "incomplete", "missing-done", "missing-id"])
async def test_naprawa_nie_omija_niepotwierdzonych_operacji(
    plan_fixture: tuple[Journal, AsyncMock, list[Json]],
    case: str,
) -> None:
    """Tryb naprawy nie uzgadnia pending ani nie kończy niedokończonego seedu."""
    journal, api, _ = plan_fixture
    if case == "pending":
        journal.state.pending = "plan-item-0"
    elif case == "incomplete":
        journal.state.complete = False
    elif case == "missing-done":
        journal.state.done.remove("meal-1")
    else:
        del journal.state.ids["plan-item-1"]
    journal.save()
    original = journal.path.read_bytes()
    with pytest.raises(FixtureError, match="COMPLETE"):
        await repair_manifest_identifiers(api, journal, household_reader=family_reader(api))
    api.call.assert_not_awaited()
    assert journal.path.read_bytes() == original


async def test_naprawa_nie_adoptuje_innego_id_niz_potwierdzony_blad_dayread(
    plan_fixture: tuple[Journal, AsyncMock, list[Json]],
) -> None:
    """ID wskazujące obcą encję wymagają osobnej analizy operatora."""
    journal, api, _ = plan_fixture
    journal.state.ids["meal-0"] = 999
    journal.save()
    original = journal.path.read_bytes()
    with pytest.raises(FixtureError, match="inne niż potwierdzony błąd"):
        await repair_manifest_identifiers(api, journal, household_reader=family_reader(api))
    assert journal.path.read_bytes() == original
    assert not journal.path.with_suffix(".identifiers.bak").exists()


async def test_naprawa_nie_nadpisuje_istniejacego_backupu(
    plan_fixture: tuple[Journal, AsyncMock, list[Json]],
) -> None:
    """Wcześniejsza kopia pozostaje nienaruszona także przy kolejnym błędnym manifeście."""
    journal, api, _ = plan_fixture
    original = journal.path.read_bytes()
    backup = journal.path.with_suffix(".identifiers.bak")
    backup.write_bytes(b"existing-backup")
    with pytest.raises(FixtureError, match="już istnieje"):
        await repair_manifest_identifiers(api, journal, household_reader=family_reader(api))
    assert journal.path.read_bytes() == original
    assert backup.read_bytes() == b"existing-backup"


def test_manifest_z_obcym_prefiksem_nie_moze_byc_naprawiany(tmp_path: Path) -> None:
    """Prefiks jest częścią tożsamości tak samo jak baza i suma zdjęcia."""
    path = tmp_path / "manifest.json"
    journal = Journal(path, "localhost/pasnik_ux", "photo")
    journal.state.prefix = "Obcy zestaw"
    journal.save()
    original = path.read_bytes()
    with pytest.raises(FixtureError, match="Manifest dotyczy innej"):
        Journal(path, "localhost/pasnik_ux", "photo")
    assert path.read_bytes() == original
