"""Cele żywieniowe + baza: historia po `valid_from`, unikalność daty, izolacja kont.

Scenariusze z karty B06 §Tests (integration). Motyw przewodni: zmiana celu od
nowej daty NIE przepisuje historii (D10) — dzień sprzed zmiany dalej liczy się
wg celu, który wtedy obowiązywał.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.modules.nutrition.schemas import GoalPayload
from app.modules.nutrition.service import GoalsService, goal_for_day
from tests.factories import create_goal, create_user

pytestmark = pytest.mark.integration


async def test_cel_obowiazujacy_zalezy_od_daty_dnia(db_session: AsyncSession) -> None:
    """Dzień przed zmianą liczy się starym celem, dzień od zmiany — nowym."""
    user = await create_user(db_session)
    await create_goal(db_session, user=user, valid_from=date(2026, 1, 1), kcal=Decimal("2000"))
    await create_goal(db_session, user=user, valid_from=date(2026, 6, 1), kcal=Decimal("2400"))

    service = GoalsService(db_session)
    goals = await service.goals_of(user.id)

    assert goal_for_day(goals, date(2026, 5, 31)).kcal == Decimal("2000")  # type: ignore[union-attr]
    assert goal_for_day(goals, date(2026, 6, 1)).kcal == Decimal("2400")  # type: ignore[union-attr]
    assert goal_for_day(goals, date(2026, 12, 31)).kcal == Decimal("2400")  # type: ignore[union-attr]


async def test_dzien_sprzed_pierwszego_celu_nie_ma_celu(db_session: AsyncSession) -> None:
    """Brak celu to `None`, nie zero — statusy takiego dnia zostają puste."""
    user = await create_user(db_session)
    await create_goal(db_session, user=user, valid_from=date(2026, 6, 1))

    goals = await GoalsService(db_session).goals_of(user.id)

    assert goal_for_day(goals, date(2026, 5, 31)) is None


async def test_duplikat_daty_konczy_sie_konfliktem(db_session: AsyncSession) -> None:
    """UNIQUE(user_id, valid_from) — drugi cel na tę samą datę to 409, nie nadpisanie."""
    user = await create_user(db_session)
    service = GoalsService(db_session)
    payload = GoalPayload(valid_from=date(2026, 3, 1), kcal=Decimal("2100"))
    await service.create_goal(user=user, payload=payload)

    with pytest.raises(ConflictError) as error:
        await service.create_goal(user=user, payload=payload)

    assert error.value.status_code == 409


async def test_zmiana_daty_celu_na_zajeta_konczy_sie_konfliktem(db_session: AsyncSession) -> None:
    """PUT przesuwający `valid_from` na datę innego celu też łapie UNIQUE."""
    user = await create_user(db_session)
    first = await create_goal(db_session, user=user, valid_from=date(2026, 1, 1))
    second = await create_goal(db_session, user=user, valid_from=date(2026, 2, 1))

    service = GoalsService(db_session)
    with pytest.raises(ConflictError):
        await service.update_goal(
            second.id,
            user=user,
            payload=GoalPayload(valid_from=first.valid_from, kcal=Decimal("1800")),
        )


async def test_ten_sam_cel_moze_istniec_u_dwoch_uzytkownikow(db_session: AsyncSession) -> None:
    """Unikalność jest per konto — cele są prywatne, nie globalne."""
    first = await create_user(db_session, email="a@example.com")
    second = await create_user(db_session, email="b@example.com")

    await create_goal(db_session, user=first, valid_from=date(2026, 1, 1))
    await create_goal(db_session, user=second, valid_from=date(2026, 1, 1))

    assert len(await GoalsService(db_session).goals_of(second.id)) == 1


async def test_cudzy_cel_jest_niewidoczny(db_session: AsyncSession) -> None:
    """Cel innego konta daje 404 — takie samo jak dla celu nieistniejącego."""
    owner = await create_user(db_session, email="owner@example.com")
    stranger = await create_user(db_session, email="stranger@example.com")
    goal = await create_goal(db_session, user=owner, valid_from=date(2026, 1, 1))

    service = GoalsService(db_session)
    with pytest.raises(NotFoundError):
        await service.get_goal(goal.id, user=stranger)
    with pytest.raises(NotFoundError):
        await service.delete_goal(goal.id, user=stranger)


async def test_historia_wychodzi_od_najnowszego_z_celem_biezacym(
    db_session: AsyncSession,
) -> None:
    """Lista jest posortowana malejąco, a `current` to cel obowiązujący danego dnia."""
    user = await create_user(db_session)
    await create_goal(db_session, user=user, valid_from=date(2026, 1, 1), kcal=Decimal("2000"))
    await create_goal(db_session, user=user, valid_from=date(2026, 6, 1), kcal=Decimal("2400"))
    await create_goal(db_session, user=user, valid_from=date(2027, 1, 1), kcal=Decimal("2600"))

    view = await GoalsService(db_session).list_goals(user, today=date(2026, 8, 17))

    assert [goal.valid_from for goal in view.items] == [
        date(2027, 1, 1),
        date(2026, 6, 1),
        date(2026, 1, 1),
    ]
    assert view.current is not None
    assert view.current.kcal == Decimal("2400")


async def test_usuniecie_celu_zostawia_reszte_historii(db_session: AsyncSession) -> None:
    """Kasujemy dokładnie jeden wpis — nic nie znika „przy okazji" (D10)."""
    user = await create_user(db_session)
    first = await create_goal(db_session, user=user, valid_from=date(2026, 1, 1))
    await create_goal(db_session, user=user, valid_from=date(2026, 6, 1))

    service = GoalsService(db_session)
    await service.delete_goal(first.id, user=user)

    remaining = await service.goals_of(user.id)
    assert [goal.valid_from for goal in remaining] == [date(2026, 6, 1)]
