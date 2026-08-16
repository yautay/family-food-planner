"""Logika modułu households: rodziny, skład i profile członków.

Podział ról (02_DOMAIN §3, 07_SECURITY §4):
- ADMIN zarządza rodzinami i ich składem — ścieżki `/admin/households`,
- członek rodziny czyta swoją rodzinę i edytuje profile — `/households/my`.
  ADMIN **nie jest tu wyjątkiem**: na `/households/my` widzi własną rodzinę,
  bo do cudzej ma osobne endpointy.

`member_profiles` NIE jest encją ze scope (nie ma kolumn wzorca 03_DATABASE §4)
— profil należy do rodziny z definicji, więc widoczność to porównanie
`household_id`, a nie `ScopedQuery`. Encje ze scope pojawią się od BATCH_05.

**Serwis oddaje dane ZMATERIALIZOWANE (`HouseholdView`), nigdy encji z leniwymi
relacjami.** Router jest kodem synchronicznym: gdyby sięgnął po niezaładowaną
kolekcję, SQLAlchemy spróbowałoby zrobić I/O poza kontekstem greenletu i
poleciałoby `MissingGreenlet` (500). To nie jest teoria — tak wywracał się
`PUT /admin/households/{id}/members` po masowym `UPDATE users`, mimo
`selectinload` w zapytaniu. Reguła dla kolejnych modułów: **relacje ORM służą
konfiguracji kaskad, a nie odczytowi w warstwie HTTP.**
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.modules.accounts.models import User
from app.modules.audit.service import AuditAction, AuditEntity, AuditService
from app.modules.households.models import Household, MemberProfile

HOUSEHOLD_NOT_FOUND = "Nie znaleziono rodziny o podanym identyfikatorze."
PROFILE_NOT_FOUND = "Nie znaleziono profilu członka rodziny."
NO_HOUSEHOLD = "Nie należysz do żadnej rodziny. Poproś administratora o przypisanie Cię do rodziny."
HOUSEHOLD_NOT_EMPTY = (
    "Rodzina ma przypisane konta lub profile członków i nie może zostać usunięta. "
    "Odepnij konta i usuń profile, a potem spróbuj ponownie."
)

#: Biała lista pól, które PATCH profilu może ruszyć. Serwis ustawia je przez
#: `setattr`, więc lista jest jedynym zabezpieczeniem przed wstrzyknięciem
#: dowolnego atrybutu z payloadu.
PROFILE_EDITABLE_FIELDS = ("name", "default_multiplier", "kcal_goal", "is_active")


@dataclass(frozen=True)
class HouseholdView:
    """Rodzina razem ze składem — komplet, po który sięga warstwa HTTP."""

    household: Household
    members: list[User]
    profiles: list[MemberProfile]


class HouseholdsService:
    """Operacje na rodzinach i profilach. Każda mutacja zostawia wpis w dzienniku."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditService(session)

    # --- odczyt wspólny ---------------------------------------------------------

    async def get_household(self, household_id: int) -> Household:
        """Sam wiersz rodziny albo 404, z KOMPLETEM świeżych kolumn.

        `populate_existing` nie jest ozdobą: po UPDATE kolumna `updated_at`
        (server-side `onupdate`) zostaje oznaczona jako wygasła, a jej odczyt
        w synchronicznym routerze wywołałby doładowanie poza kontekstem
        greenletu — czyli `MissingGreenlet` i 500 zamiast odpowiedzi.
        """
        household = (
            await self._session.execute(
                select(Household)
                .where(Household.id == household_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if household is None:
            raise NotFoundError(HOUSEHOLD_NOT_FOUND)
        return household

    async def household_view(self, household_id: int) -> HouseholdView:
        """Rodzina + konta + profile, wszystko doczytane jawnymi zapytaniami."""
        household = await self.get_household(household_id)
        return (await self._views([household]))[0]

    async def _views(self, households: list[Household]) -> list[HouseholdView]:
        """Skład dla wielu rodzin dwoma zapytaniami — bez N+1 i bez lazy loadów."""
        ids = [household.id for household in households]
        if not ids:
            return []

        # `populate_existing` — jak w `get_household`: wiersze mogą już siedzieć
        # w identity map z wygasłymi kolumnami po masowym UPDATE albo po flushu.
        members = (
            (
                await self._session.execute(
                    select(User)
                    .where(User.household_id.in_(ids))
                    .order_by(User.display_name, User.id)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        profiles = (
            (
                await self._session.execute(
                    select(MemberProfile)
                    .where(MemberProfile.household_id.in_(ids))
                    .order_by(MemberProfile.name, MemberProfile.id)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )

        members_by: dict[int, list[User]] = defaultdict(list)
        for member in members:
            if member.household_id is not None:
                members_by[member.household_id].append(member)
        profiles_by: dict[int, list[MemberProfile]] = defaultdict(list)
        for profile in profiles:
            if profile.household_id is not None:
                profiles_by[profile.household_id].append(profile)

        return [
            HouseholdView(
                household=household,
                members=members_by[household.id],
                profiles=profiles_by[household.id],
            )
            for household in households
        ]

    # --- administracja rodzinami ----------------------------------------------

    async def list_households(
        self, *, limit: int, offset: int, query: str | None = None
    ) -> tuple[list[HouseholdView], int]:
        """Lista rodzin dla ADMIN-a; `query` filtruje po nazwie."""
        statement = select(Household)
        if query:
            statement = statement.where(Household.name.ilike(f"%{query.strip()}%"))

        total = (
            await self._session.execute(select(func.count()).select_from(statement.subquery()))
        ).scalar_one()
        rows = (
            (
                await self._session.execute(
                    statement.order_by(Household.name, Household.id)
                    .limit(limit)
                    .offset(offset)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        return await self._views(list(rows)), total

    async def create_household(self, *, name: str, actor: User) -> HouseholdView:
        """Utwórz rodzinę (ADMIN)."""
        household = Household(name=name)
        self._session.add(household)
        await self._session.flush()

        self._audit.record(
            action=AuditAction.HOUSEHOLD_CREATE,
            entity_type=AuditEntity.HOUSEHOLD,
            entity_id=household.id,
            actor_id=actor.id,
            payload={"name": household.name},
        )
        await self._session.commit()
        return await self.household_view(household.id)

    async def update_household(
        self, household_id: int, *, name: str | None, actor: User
    ) -> HouseholdView:
        """Zmiana nazwy rodziny (ADMIN)."""
        household = await self.get_household(household_id)
        if name is not None and name != household.name:
            before = household.name
            household.name = name
            self._audit.record(
                action=AuditAction.HOUSEHOLD_UPDATE,
                entity_type=AuditEntity.HOUSEHOLD,
                entity_id=household.id,
                actor_id=actor.id,
                payload={"before": {"name": before}, "after": {"name": household.name}},
            )
            await self._session.commit()
        return await self.household_view(household_id)

    async def delete_household(self, household_id: int, *, actor: User) -> None:
        """Usuń rodzinę — wyłącznie pustą; inaczej 409 z listą użyć (ADR-012)."""
        view = await self.household_view(household_id)
        used_in: list[dict[str, Any]] = [
            {"type": "user", "id": member.id, "name": member.display_name}
            for member in view.members
        ] + [
            {"type": "member_profile", "id": profile.id, "name": profile.name}
            for profile in view.profiles
        ]
        if used_in:
            raise ConflictError(HOUSEHOLD_NOT_EMPTY, details={"used_in": used_in})

        name = view.household.name
        # DELETE zapytaniem, a nie `session.delete()`: kaskady pilnuje baza
        # (03_DATABASE §2), a ORM nie musi doczytywać kolekcji encji.
        await self._session.execute(delete(Household).where(Household.id == household_id))
        self._audit.record(
            action=AuditAction.HOUSEHOLD_DELETE,
            entity_type=AuditEntity.HOUSEHOLD,
            entity_id=household_id,
            actor_id=actor.id,
            payload={"name": name},
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            # Encje ze scope (od BATCH_05) trzymają `household_id` z ON DELETE
            # RESTRICT — bez tego wyjątku admin dostałby 500 zamiast 409.
            await self._session.rollback()
            raise ConflictError(HOUSEHOLD_NOT_EMPTY, details={"used_in": []}) from exc

    async def set_members(
        self, household_id: int, *, user_ids: list[int], actor: User
    ) -> HouseholdView:
        """Pełna podmiana składu rodziny (ADMIN).

        Konto może należeć do maksymalnie jednej rodziny (ADR-006) — gwarantuje
        to sama kolumna `users.household_id`, więc przypisanie automatycznie
        odpina konto od poprzedniej rodziny. Odpięcie konta NIE kasuje jego
        profilu: profil wisi na rodzinie, a nie na koncie (02_DOMAIN §3).
        """
        view = await self.household_view(household_id)
        wanted = sorted(set(user_ids))

        if wanted:
            found = (
                (await self._session.execute(select(User.id).where(User.id.in_(wanted))))
                .scalars()
                .all()
            )
            missing = sorted(set(wanted) - set(found))
            if missing:
                raise NotFoundError(
                    "Nie znaleziono kont o podanych identyfikatorach.",
                    details={"user_ids": missing},
                )

        before = sorted(member.id for member in view.members)

        await self._session.execute(
            update(User)
            .where(User.household_id == household_id, User.id.not_in(wanted))
            .values(household_id=None)
        )
        if wanted:
            await self._session.execute(
                update(User).where(User.id.in_(wanted)).values(household_id=household_id)
            )

        self._audit.record(
            action=AuditAction.HOUSEHOLD_MEMBERS_UPDATE,
            entity_type=AuditEntity.HOUSEHOLD,
            entity_id=household_id,
            actor_id=actor.id,
            payload={"before": before, "after": wanted},
        )
        await self._session.commit()
        return await self.household_view(household_id)

    # --- widok użytkownika ------------------------------------------------------

    async def my_household(self, user: User) -> HouseholdView | None:
        """Rodzina zalogowanego użytkownika. Brak rodziny = `None`, nie 404."""
        if user.household_id is None:
            return None
        return await self.household_view(user.household_id)

    async def list_profiles(self, user: User) -> list[MemberProfile]:
        """Profile w rodzinie użytkownika (bez rodziny — pusta lista)."""
        if user.household_id is None:
            return []
        rows = (
            (
                await self._session.execute(
                    select(MemberProfile)
                    .where(MemberProfile.household_id == user.household_id)
                    .order_by(MemberProfile.name, MemberProfile.id)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def create_profile(
        self,
        *,
        user: User,
        name: str,
        default_multiplier: Decimal,
        kcal_goal: Decimal | None,
        is_active: bool,
    ) -> MemberProfile:
        """Dodaj profil członka do rodziny użytkownika (każdy członek może — 02_DOMAIN §3.1)."""
        household_id = self._require_household(user)
        profile = MemberProfile(
            household_id=household_id,
            name=name,
            default_multiplier=default_multiplier,
            kcal_goal=kcal_goal,
            is_active=is_active,
        )
        self._session.add(profile)
        await self._session.flush()

        self._audit.record(
            action=AuditAction.MEMBER_PROFILE_CREATE,
            entity_type=AuditEntity.MEMBER_PROFILE,
            entity_id=profile.id,
            actor_id=user.id,
            payload={"household_id": household_id, "name": profile.name},
        )
        await self._session.commit()
        await self._session.refresh(profile)
        return profile

    async def update_profile(
        self, profile_id: int, *, user: User, changes: Mapping[str, Any]
    ) -> MemberProfile:
        """Edycja profilu przez dowolnego członka rodziny; audit rejestruje kto.

        `changes` to WYŁĄCZNIE pola faktycznie przysłane w żądaniu
        (`model_dump(exclude_unset=True)`). Gdyby serwis dostawał komplet pól
        i pomijał `None`, nie dałoby się wyczyścić `kcal_goal` — a to kolumna
        NULLABLE, więc użytkownik ma prawo skasować cel kaloryczny.
        """
        profile = await self.get_profile(profile_id, user=user)
        before = self._profile_snapshot(profile)

        for field in PROFILE_EDITABLE_FIELDS:
            if field in changes:
                setattr(profile, field, changes[field])

        after = self._profile_snapshot(profile)
        if before != after:
            self._audit.record(
                action=AuditAction.MEMBER_PROFILE_UPDATE,
                entity_type=AuditEntity.MEMBER_PROFILE,
                entity_id=profile.id,
                actor_id=user.id,
                payload={"before": before, "after": after},
            )
        await self._session.commit()
        await self._session.refresh(profile)
        return profile

    async def delete_profile(self, profile_id: int, *, user: User) -> None:
        """Usuń profil z rodziny użytkownika."""
        profile = await self.get_profile(profile_id, user=user)
        name = profile.name
        await self._session.execute(delete(MemberProfile).where(MemberProfile.id == profile_id))
        self._audit.record(
            action=AuditAction.MEMBER_PROFILE_DELETE,
            entity_type=AuditEntity.MEMBER_PROFILE,
            entity_id=profile_id,
            actor_id=user.id,
            payload={"household_id": user.household_id, "name": name},
        )
        await self._session.commit()

    async def get_profile(self, profile_id: int, *, user: User) -> MemberProfile:
        """Profil z rodziny użytkownika. Cudzy albo nieistniejący → identyczne 404."""
        household_id = user.household_id
        profile = await self._session.get(MemberProfile, profile_id)
        if profile is None or household_id is None or profile.household_id != household_id:
            raise NotFoundError(PROFILE_NOT_FOUND)
        return profile

    # --- pomocnicze --------------------------------------------------------------

    @staticmethod
    def _require_household(user: User) -> int:
        if user.household_id is None:
            raise ConflictError(NO_HOUSEHOLD)
        return user.household_id

    @staticmethod
    def _profile_snapshot(profile: MemberProfile) -> dict[str, Any]:
        """Stan profilu do payloadu audytu — same wartości domenowe, bez PII kont."""
        return {
            "name": profile.name,
            "default_multiplier": format(profile.default_multiplier, "f"),
            "kcal_goal": None if profile.kcal_goal is None else format(profile.kcal_goal, "f"),
            "is_active": profile.is_active,
        }
