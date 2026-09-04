"""Kontrakt HTTP `/transfer` — macierz uprawnień i gwarancje dry-runu (08_TESTING §4).

Trzy rzeczy, które ten plik pilnuje na poziomie HTTP:

1. macierz ról: anonim 401, USER nie zrobi `scope=instance` (403), ADMIN tak,
2. dry-run NIE zapisuje NICZEGO — asercja na licznikach tabel, nie na słowie
   „nie zapisuje" w dokumentacji,
3. mutacja bez nagłówka CSRF to 403, tak jak w każdym innym module.
"""

from __future__ import annotations

import json
import zipfile
from io import BytesIO

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.modules.audit.models import AuditEntry
from app.modules.catalog.models import CanonicalProduct
from app.modules.recipes.models import Recipe
from app.modules.transfer.schemas import DATA_ENTRY_NAME
from tests.factories import (
    create_admin,
    create_category,
    create_product,
    create_recipe,
    create_user,
)
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

EXPORT = f"{API}/transfer/export"
IMPORT = f"{API}/transfer/import"


def _archive(document: dict[str, object]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(DATA_ENTRY_NAME, json.dumps(document))
    return buffer.getvalue()


def _minimal_user_file() -> bytes:
    """Najmniejszy poprawny plik użytkownika: jedna kategoria i jeden produkt."""
    return _archive(
        {
            "schema_version": 1,
            "app_version": "test",
            "exported_at": "2026-08-29T10:00:00+00:00",
            "scope": "user",
            "data": {
                "product_categories": [
                    {"id": 1, "name": "Owoce importowane", "position": 9, "perishability": "fresh"}
                ],
                "canonical_products": [
                    {
                        "id": 2,
                        "name": "Mango",
                        "normalized_name": "mango",
                        "measure_kind": "mass",
                        "verification_status": "unverified",
                        "is_archived": False,
                        "category_id": 1,
                    }
                ],
            },
        }
    )


def _upload(data: bytes) -> dict[str, tuple[str, bytes, str]]:
    return {"file": ("export.zip", data, "application/zip")}


async def _count(session: AsyncSession, model: type) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


# --- macierz uprawnień ----------------------------------------------------------------


async def test_anonim_dostaje_401_na_calym_transferze(db_client: AsyncClient) -> None:
    """Transfer siedzi za sesją (04_API §3 pkt 1).

    Anonim dostaje własny token CSRF: bez niego middleware odpowiada 403 JESZCZE
    PRZED autoryzacją, a tu testujemy brak sesji, nie brak tokenu (wzorzec
    `tests/api/shopping/test_shopping_api.py`).
    """
    db_client.cookies.set(CSRF_COOKIE_NAME, "token-anonima")
    headers = {CSRF_HEADER_NAME: "token-anonima"}

    assert (await db_client.post(EXPORT, headers=headers)).status_code == 401
    assert (
        await db_client.post(IMPORT, files=_upload(_minimal_user_file()), headers=headers)
    ).status_code == 401
    assert (
        await db_client.post(f"{IMPORT}/{'a' * 32}/apply", json={"decisions": []}, headers=headers)
    ).status_code == 401


async def test_uzytkownik_nie_wyeksportuje_calej_instancji(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`scope=instance` jest za `require_admin` w sensie reguły, nie tylko UI."""
    user = await create_user(db_session, email="user@example.com")
    await login(db_client, user.email)

    response = await db_client.post(
        EXPORT, params={"scope": "instance"}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_admin_eksportuje_instancje_i_dostaje_zip(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """ADMIN dostaje archiwum z kontami — ale bez ani jednego hasła (AC 2)."""
    admin = await create_admin(db_session, email="admin@example.com")
    await login(db_client, admin.email)

    response = await db_client.post(
        EXPORT, params={"scope": "instance"}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        document = json.loads(archive.read(DATA_ENTRY_NAME))
    emails = [row["email"] for row in document["data"]["users"]]
    assert emails == ["admin@example.com"]
    assert "password_hash" not in json.dumps(document)


async def test_uzytkownik_eksportuje_swoje_dane(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Acceptance Criterion 1: ZIP z `export.json` w wersji 1 i nazwą pliku z datą."""
    user = await create_user(db_session, email="anna@example.com")
    category = await create_category(db_session, name="Warzywa")
    await create_product(db_session, category=category, name="Cebula")
    await create_recipe(db_session, owner=user, name="Zupa")
    await login(db_client, user.email)

    response = await db_client.post(EXPORT, headers=csrf_headers(db_client))

    assert response.status_code == 200
    assert "pasnik-export-" in response.headers["content-disposition"]
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        document = json.loads(archive.read(DATA_ENTRY_NAME))
    assert document["schema_version"] == 1
    assert document["scope"] == "user"
    assert [row["name"] for row in document["data"]["recipes"]] == ["Zupa"]
    # Katalog globalny wchodzi tylko w części REFERENCJONOWANEJ — „Cebula"
    # nie jest używana przez nic, co należy do użytkownika.
    assert document["data"]["canonical_products"] == []


async def test_eksport_bez_naglowka_csrf_to_403(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Mutacja bez `X-CSRF-Token` pada tak samo, jak w każdym innym module."""
    user = await create_user(db_session, email="anna@example.com")
    await login(db_client, user.email)

    assert (await db_client.post(EXPORT)).status_code == 403


async def test_uzytkownik_nie_zaimportuje_pliku_instancji(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Plik z kontami i rodzinami wolno wgrać wyłącznie ADMIN-owi."""
    user = await create_user(db_session, email="anna@example.com")
    await login(db_client, user.email)
    instance_file = _archive({"schema_version": 1, "scope": "instance", "data": {"households": []}})

    response = await db_client.post(
        IMPORT, files=_upload(instance_file), headers=csrf_headers(db_client)
    )

    assert response.status_code == 403


# --- dry-run nie zapisuje -------------------------------------------------------------


async def test_dry_run_nie_zostawia_sladu_w_bazie(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Acceptance Criterion 3 — liczniki tabel po dry-runie są takie jak przed."""
    user = await create_user(db_session, email="anna@example.com")
    await login(db_client, user.email)
    before = (
        await _count(db_session, CanonicalProduct),
        await _count(db_session, Recipe),
        await _count(db_session, AuditEntry),
    )

    response = await db_client.post(
        IMPORT, files=_upload(_minimal_user_file()), headers=csrf_headers(db_client)
    )

    assert response.status_code == 200
    report = response.json()
    assert report["to_create"]["canonical_products"] == 1
    assert report["collisions"] == []
    assert report["import_id"]
    assert (
        await _count(db_session, CanonicalProduct),
        await _count(db_session, Recipe),
        await _count(db_session, AuditEntry),
    ) == before


async def test_apply_tworzy_dane_i_wpis_w_dzienniku(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Acceptance Criterion 8: import zostawia w audycie liczby, nie treść."""
    user = await create_user(db_session, email="anna@example.com")
    await login(db_client, user.email)
    dry_run = await db_client.post(
        IMPORT, files=_upload(_minimal_user_file()), headers=csrf_headers(db_client)
    )
    import_id = dry_run.json()["import_id"]

    response = await db_client.post(
        f"{IMPORT}/{import_id}/apply",
        json={"decisions": []},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 200
    assert response.json()["created"]["canonical_products"] == 1
    assert await _count(db_session, CanonicalProduct) == 1

    entry = (
        (await db_session.execute(select(AuditEntry).where(AuditEntry.action == "transfer.import")))
        .scalars()
        .one()
    )
    assert entry.user_id == user.id
    assert entry.payload["created"]["canonical_products"] == 1
    assert "Mango" not in json.dumps(entry.payload)


async def test_cudza_paczka_importu_daje_404(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Odłożona paczka należy do konta, które ją wgrało — cudza jest nie do odróżnienia."""
    owner = await create_user(db_session, email="anna@example.com")
    intruder = await create_user(db_session, email="obcy@example.com")
    await login(db_client, owner.email)
    dry_run = await db_client.post(
        IMPORT, files=_upload(_minimal_user_file()), headers=csrf_headers(db_client)
    )
    import_id = dry_run.json()["import_id"]

    await db_client.post(f"{API}/auth/logout", headers=csrf_headers(db_client))
    await login(db_client, intruder.email)
    response = await db_client.post(
        f"{IMPORT}/{import_id}/apply",
        json={"decisions": []},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 404


async def test_nieznany_import_id_daje_404(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Zmyślony identyfikator paczki nie może zdradzać, czy jakaś istnieje."""
    user = await create_user(db_session, email="anna@example.com")
    await login(db_client, user.email)

    response = await db_client.post(
        f"{IMPORT}/{'a' * 32}/apply",
        json={"decisions": []},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 404


async def test_plik_ktory_nie_jest_archiwum_daje_422_po_polsku(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Acceptance Criterion 7 na poziomie HTTP: komunikat dla człowieka, nie 500."""
    user = await create_user(db_session, email="anna@example.com")
    await login(db_client, user.email)

    response = await db_client.post(
        IMPORT, files=_upload(b"to nie jest zip"), headers=csrf_headers(db_client)
    )

    assert response.status_code == 422
    assert response.json()["error"]["message"].startswith("Przesłany plik nie jest archiwum")
