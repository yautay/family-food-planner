"""Kontrakt HTTP `GET /stats/daily` (04_API §2, macierz 08_TESTING §4).

Endpoint jest wyłącznie do odczytu i agreguje TYLKO to, co użytkownik widzi
w planie, więc macierz sprowadza się do trzech wierszy: anonim 401, cudzy dzień
prywatny niewidoczny (luka, nie 403 i nie cudza treść), dzień rodzinny widoczny.
Reszta testów pilnuje kształtu odpowiedzi (stringi dziesiętne, `null` dla luki)
i walidacji zakresu dat.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scope import Scope
from app.modules.accounts.models import User
from app.modules.catalog.models import CanonicalProduct, VerificationStatus
from app.modules.catalog.units import AmountUnit
from app.modules.planning.stats_service import MAX_STATS_RANGE_DAYS
from tests.factories import (
    create_admin,
    create_category,
    create_goal,
    create_household,
    create_plan_day,
    create_plan_item,
    create_plan_meal,
    create_product,
    create_user,
)
from tests.helpers import API, login

pytestmark = pytest.mark.api

STATS = f"{API}/stats/daily"
DAY = "2026-08-17"
NEXT_DAY = "2026-08-18"
DAY_DATE = date(2026, 8, 17)
NEXT_DAY_DATE = date(2026, 8, 18)


async def _verified_product(session: AsyncSession, *, name: str = "Skyr") -> CanonicalProduct:
    """Produkt 60 kcal / 100 g z kompletem wartości — liczby wychodzą „na czysto"."""
    category = await create_category(session, name=f"Kategoria {name}")
    return await create_product(
        session,
        category=category,
        name=name,
        kcal_100=Decimal("60.00"),
        protein_100=Decimal("10.00"),
        fat_100=Decimal("0.20"),
        carbs_100=Decimal("4.00"),
        fiber_100=Decimal("0.00"),
        sugars_100=Decimal("4.00"),
        glycemic_index=Decimal("11.0"),
        verification_status=VerificationStatus.VERIFIED,
    )


async def _plan_500g(
    session: AsyncSession, *, owner: User, day: date, scope: Scope = Scope.PRIVATE
) -> None:
    """Dzień z jedną pozycją 500 g produktu = 300 kcal."""
    product = await _verified_product(session, name=f"Skyr {day}")
    plan_day = await create_plan_day(session, owner=owner, day=day, scope=scope)
    meal = await create_plan_meal(session, plan_day=plan_day)
    await create_plan_item(
        session,
        meal=meal,
        product=product,
        amount=Decimal("500"),
        amount_unit=AmountUnit.GRAM,
    )


# --- macierz uprawnień (08_TESTING §4) ------------------------------------------------


async def test_anonim_dostaje_401(db_client: AsyncClient) -> None:
    """Statystyki wymagają sesji (04_API §3 pkt 1)."""
    assert (await db_client.get(f"{STATS}?from={DAY}&to={DAY}")).status_code == 401


async def test_cudzy_dzien_prywatny_jest_luka_nie_trescia(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Anty-IDOR: user B widzi w agregatach lukę, nie kalorie usera A."""
    household = await create_household(db_session)
    owner = await create_user(db_session, email="owner@example.com", household=household)
    member = await create_user(db_session, email="member@example.com", household=household)
    await _plan_500g(db_session, owner=owner, day=DAY_DATE, scope=Scope.PRIVATE)
    await login(db_client, member.email)

    response = await db_client.get(f"{STATS}?from={DAY}&to={DAY}")

    assert response.status_code == 200
    body = response.json()
    assert body["days"][0]["has_plan"] is False
    assert body["days"][0]["nutrition"] is None
    assert body["summary"]["days_with_plan"] == 0


async def test_dzien_rodzinny_wchodzi_do_agregatow(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Dzień HOUSEHOLD jest wspólny, więc członek rodziny widzi go w statystykach."""
    household = await create_household(db_session)
    owner = await create_user(db_session, email="owner2@example.com", household=household)
    member = await create_user(db_session, email="member2@example.com", household=household)
    await _plan_500g(db_session, owner=owner, day=DAY_DATE, scope=Scope.HOUSEHOLD)
    await login(db_client, member.email)

    body = (await db_client.get(f"{STATS}?from={DAY}&to={DAY}")).json()

    assert body["days"][0]["has_plan"] is True
    assert body["days"][0]["nutrition"]["kcal"] == "300"


async def test_admin_widzi_cudze_dni_na_sciezce_uzytkownika(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """D16: ADMIN widzi wszystkie encje ze scope także w agregatach."""
    owner = await create_user(db_session, email="owner3@example.com")
    admin = await create_admin(db_session, email="admin@example.com")
    await _plan_500g(db_session, owner=owner, day=DAY_DATE, scope=Scope.PRIVATE)
    await login(db_client, admin.email)

    body = (await db_client.get(f"{STATS}?from={DAY}&to={DAY}")).json()

    assert body["days"][0]["has_plan"] is True


# --- kontrakt odpowiedzi --------------------------------------------------------------


async def test_kontrakt_odpowiedzi_dni_celow_i_podsumowania(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Kształt z karty B13: dni z `nutrition`/`goal`/`status` + `summary`."""
    user = await create_user(db_session)
    await create_goal(
        db_session,
        user=user,
        valid_from=date(2026, 1, 1),
        kcal=Decimal("300"),
        protein_g=Decimal("50.0"),
    )
    await _plan_500g(db_session, owner=user, day=DAY_DATE)
    await login(db_client, user.email)

    body = (await db_client.get(f"{STATS}?from={DAY}&to={NEXT_DAY}")).json()

    assert set(body) == {"days", "summary"}
    planned, gap = body["days"]
    assert set(planned) == {"day", "has_plan", "nutrition", "goal", "status"}
    # Wszystkie liczby to STRINGI dziesiętne (04_API §1) — nie float, nie int.
    assert planned["nutrition"]["kcal"] == "300"
    assert planned["nutrition"]["protein_g"] == "50.0"
    assert planned["goal"] == {
        "kcal": "300",
        "protein_g": "50.0",
        "fat_g": None,
        "carbs_g": None,
        "valid_from": "2026-01-01",
    }
    assert planned["status"] == {
        "kcal": "ok",
        "protein_g": "ok",
        "fat_g": None,
        "carbs_g": None,
    }
    # Dzień bez planu: luka, nie zero — i bez statusu, choć cel istnieje.
    assert gap["has_plan"] is False
    assert gap["nutrition"] is None
    assert gap["status"]["kcal"] is None

    summary = body["summary"]
    assert summary["days_in_range"] == 2
    assert summary["days_with_plan"] == 1
    assert summary["avg"]["kcal"] == "300"
    assert summary["avg"]["complete"] is True
    assert summary["goal_progress"]["kcal"] == {
        "value": "300",
        "target": "300",
        "delta": "0",
        "status": "ok",
    }


async def test_glikemia_jest_w_odpowiedzi_choc_ui_jej_nie_pokazuje(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """ŁG zostaje w kontrakcie (karta B13 Implementation Notes) — nie wycinamy go."""
    user = await create_user(db_session)
    await _plan_500g(db_session, owner=user, day=DAY_DATE)
    await login(db_client, user.email)

    body = (await db_client.get(f"{STATS}?from={DAY}&to={DAY}")).json()

    assert "glycemic_load" in body["days"][0]["nutrition"]
    assert "glycemic_load" in body["summary"]["avg"]


async def test_niepelne_dane_wychodza_flaga_i_lista_brakow(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Produkt bez wartości ⇒ `complete=false` + `missing` (plakietka w UI)."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category, name="Bez wartości")
    plan_day = await create_plan_day(db_session, owner=user, day=DAY_DATE)
    meal = await create_plan_meal(db_session, plan_day=plan_day)
    await create_plan_item(
        db_session,
        meal=meal,
        product=product,
        amount=Decimal("100"),
        amount_unit=AmountUnit.GRAM,
    )
    await login(db_client, user.email)

    body = (await db_client.get(f"{STATS}?from={DAY}&to={DAY}")).json()

    assert body["days"][0]["nutrition"]["complete"] is False
    assert body["days"][0]["nutrition"]["missing"]
    assert body["summary"]["avg"]["complete"] is False


async def test_pusty_zakres_ma_srednia_null_i_zero_dni_z_planem(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Zakres bez planu: `avg: null` i brak statusu — nie zerowe wartości."""
    user = await create_user(db_session)
    await create_goal(db_session, user=user, valid_from=date(2026, 1, 1), kcal=Decimal("2000"))
    await login(db_client, user.email)

    body = (await db_client.get(f"{STATS}?from={DAY}&to={NEXT_DAY}")).json()

    assert body["summary"]["days_with_plan"] == 0
    assert body["summary"]["avg"] is None
    assert body["summary"]["goal_progress"]["kcal"]["status"] is None


# --- walidacja zakresu ----------------------------------------------------------------


async def test_zakres_odwrocony_to_422(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """`from > to` to `validation_error`, nie pusta lista dni."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.get(f"{STATS}?from={NEXT_DAY}&to={DAY}")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_zakres_ponad_92_dni_to_422(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """Sufit 92 dni; dokładnie 92 dni jeszcze przechodzi (granica włącznie)."""
    user = await create_user(db_session)
    await login(db_client, user.email)
    start = date(2026, 1, 1)
    last_allowed = start + timedelta(days=MAX_STATS_RANGE_DAYS - 1)
    too_far = last_allowed + timedelta(days=1)

    assert (await db_client.get(f"{STATS}?from={start}&to={last_allowed}")).status_code == 200

    response = await db_client.get(f"{STATS}?from={start}&to={too_far}")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_brak_parametrow_zakresu_to_422(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`from` i `to` są wymagane — endpoint nie zgaduje domyślnego zakresu."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    assert (await db_client.get(STATS)).status_code == 422


async def test_data_w_zlym_formacie_to_422(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Daty to `YYYY-MM-DD` (04_API §1)."""
    user = await create_user(db_session)
    await login(db_client, user.email)

    assert (await db_client.get(f"{STATS}?from=17.08.2026&to={DAY}")).status_code == 422
