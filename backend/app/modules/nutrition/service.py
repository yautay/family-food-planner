"""Logika celów żywieniowych: historia po `valid_from` i cel obowiązujący w dniu.

Granice odpowiedzialności:

- **Własność** — cel należy do użytkownika z SESJI (`user_id` nigdy z body,
  karta B06 §Security); cudzy cel jest po prostu niewidoczny (404).
- **Historia** — zapis nowego celu NIE kasuje poprzednich (D10). Cel
  obowiązujący w dniu D to wiersz z największym `valid_from <= D`, więc
  statusy dni sprzed zmiany zostają takie, jakie były.
- **Czas wchodzi parametrem** — serwis nie woła zegara w środku obliczeń;
  „dzisiaj" podaje router. Dzięki temu logika wyboru celu jest testowalna
  bez zamrażania czasu.

Cele mieszkają w module `nutrition`, bo tam umieszcza je 02_DOMAIN §1
(„nutrition — … cele"); `engine.py` pozostaje czystym plikiem bez I/O (ADR-008).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.modules.accounts.models import User
from app.modules.nutrition.models import UserNutritionGoal
from app.modules.nutrition.schemas import GoalPayload

GOAL_NOT_FOUND = "Nie znaleziono celu żywieniowego."
GOAL_DUPLICATE = (
    "Masz już cel obowiązujący od tej daty. Zmień istniejący wpis albo wybierz inną datę."
)


@dataclass(frozen=True)
class GoalsView:
    """Historia celów (najnowsze pierwsze) razem z celem obowiązującym „dziś"."""

    items: list[UserNutritionGoal]
    current: UserNutritionGoal | None


def goal_for_day(goals: Sequence[UserNutritionGoal], day: date) -> UserNutritionGoal | None:
    """Cel obowiązujący w dniu `day` — czysta funkcja nad WCZYTANĄ historią.

    Wybiera wiersz z największym `valid_from <= day`; brak takiego wiersza
    (użytkownik nie miał wtedy jeszcze celu) daje `None`. Wydzielone z I/O,
    żeby widok zakresu dat mógł policzyć cele dla 7 dni z JEDNEGO zapytania.
    """
    best: UserNutritionGoal | None = None
    for goal in goals:
        if goal.valid_from <= day and (best is None or goal.valid_from > best.valid_from):
            best = goal
    return best


class GoalsService:
    """Operacje na celach żywieniowych. Jedyne miejsce I/O tej części modułu."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- odczyt -----------------------------------------------------------------

    async def list_goals(self, user: User, *, today: date) -> GoalsView:
        """Pełna historia własnych celów (sort `valid_from` malejąco) + cel bieżący."""
        goals = await self.goals_of(user.id)
        return GoalsView(
            items=sorted(goals, key=lambda goal: (goal.valid_from, goal.id), reverse=True),
            current=goal_for_day(goals, today),
        )

    async def goals_of(self, user_id: int) -> list[UserNutritionGoal]:
        """Wszystkie cele użytkownika, rosnąco po `valid_from` (jedno zapytanie).

        Historii celów jest z natury mało (kilka-kilkanaście wierszy na konto),
        więc plan dnia dla zakresu dat czyta ją RAZ i wybiera cel per dzień
        w pamięci — zamiast zapytania na każdy dzień zakresu.
        """
        rows = (
            (
                await self._session.execute(
                    select(UserNutritionGoal)
                    .where(UserNutritionGoal.user_id == user_id)
                    .order_by(UserNutritionGoal.valid_from, UserNutritionGoal.id)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def get_goal(self, goal_id: int, *, user: User) -> UserNutritionGoal:
        """Własny cel po id — cudzy albo nieistniejący kończy się identycznym 404."""
        goal = (
            await self._session.execute(
                select(UserNutritionGoal).where(
                    UserNutritionGoal.id == goal_id,
                    UserNutritionGoal.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if goal is None:
            raise NotFoundError(GOAL_NOT_FOUND)
        return goal

    # --- zapis ------------------------------------------------------------------

    async def create_goal(self, *, user: User, payload: GoalPayload) -> UserNutritionGoal:
        """Nowy cel od daty; drugi cel na tę samą datę to 409, nie nadpisanie."""
        goal = UserNutritionGoal(
            user_id=user.id,
            valid_from=payload.valid_from,
            kcal=payload.kcal,
            protein_g=payload.protein_g,
            fat_g=payload.fat_g,
            carbs_g=payload.carbs_g,
        )
        self._session.add(goal)
        await self._commit_unique(goal)
        return goal

    async def update_goal(
        self, goal_id: int, *, user: User, payload: GoalPayload
    ) -> UserNutritionGoal:
        """PUT — pełna podmiana wraz z datą obowiązywania (kolizja daty ⇒ 409)."""
        goal = await self.get_goal(goal_id, user=user)
        goal.valid_from = payload.valid_from
        goal.kcal = payload.kcal
        goal.protein_g = payload.protein_g
        goal.fat_g = payload.fat_g
        goal.carbs_g = payload.carbs_g
        await self._commit_unique(goal)
        return goal

    async def delete_goal(self, goal_id: int, *, user: User) -> None:
        """Usunięcie pojedynczego wpisu historii — decyzja użytkownika, nigdy automat (D10)."""
        goal = await self.get_goal(goal_id, user=user)
        await self._session.execute(
            delete(UserNutritionGoal).where(UserNutritionGoal.id == goal.id)
        )
        await self._session.commit()

    async def _commit_unique(self, goal: UserNutritionGoal) -> None:
        """Commit z mapowaniem UNIQUE(user_id, valid_from) na 409 (04_API §1)."""
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(GOAL_DUPLICATE) from exc
        await self._session.refresh(goal)
