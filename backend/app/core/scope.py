"""Widoczność encji współdzielnych — JEDNO miejsce egzekwowania scope.

Wzorzec kolumn i warunek widoczności są WIĄŻĄCE (03_DATABASE §4, ADR-006):

    WHERE owner_user_id = :uid
       OR (scope = 'household' AND household_id = :user_household_id)

Reguły operacji (02_DOMAIN §3.1, macierz 08_TESTING §4):

| operacja                | obcy USER | członek rodziny | właściciel | ADMIN |
|-------------------------|-----------|-----------------|------------|-------|
| odczyt PRIVATE          | 404       | 404             | OK         | OK    |
| odczyt/edycja HOUSEHOLD | 404       | OK              | OK         | OK    |
| zmiana scope / usunięcie| 404       | 403             | OK         | OK    |

Cudza encja to **404, nie 403** — nie potwierdzamy jej istnienia (07_SECURITY §4).
Serwisy modułów domenowych NIE piszą własnych filtrów widoczności: każdy
konsument (recipes B05, plany B06/B07, szablony, listy zakupowe B11) używa
`ScopedQuery`. Ręczny filtr scope w serwisie = błąd review.

Spiżarnia (B08) ma wariant „zawsze household, fallback na użytkownika bez
rodziny" — `HouseholdScopedMixin` + `HouseholdScopedQuery` na dole pliku.
Encja bez kolumny `scope` (03_DATABASE §7) nie mieści się we wzorcu wyżej, ale
mieszka w TYM SAMYM module, bo reguła „żadnych filtrów widoczności w serwisie"
obowiązuje jednakowo.

Typ enumowy `entity_scope` powstaje w migracji PIERWSZEJ produkcyjnej tabeli
ze scope (`recipes`, BATCH_05) — BATCH_03 tworzy tylko sam mechanizm.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ColumnElement,
    ForeignKey,
    Identity,
    Select,
    and_,
    or_,
    select,
    true,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.modules.accounts.models import User, UserRole


class Scope(StrEnum):
    """Zakres widoczności encji współdzielnej (ADR-006)."""

    PRIVATE = "private"
    HOUSEHOLD = "household"


#: Typ enumowy w PG współdzielony przez modele — jedna definicja nazw.
#: `create_type=False`, bo cykl życia typu należy do MIGRACJI (`0006` tworzy,
#: jej downgrade kasuje) — ORM-owe create/drop tabeli z kolumną scope nie ma
#: prawa dotykać typu (ustalenie review B05: fixture testowy kasował typ
#: będący w użyciu przez `recipes`).
SCOPE_ENUM = postgresql.ENUM(
    Scope,
    name="entity_scope",
    create_type=False,
    values_callable=lambda enum: [member.value for member in enum],
)

#: Nazwa CHECK-a pilnującego spójności scope na poziomie bazy (03_DATABASE §4).
SCOPE_CHECK_NAME = "scope_requires_household"

NO_HOUSEHOLD_MESSAGE = (
    "Nie należysz do żadnej rodziny, więc nie możesz udostępnić tego rodzinie. "
    "Poproś administratora o przypisanie do rodziny."
)
DEFAULT_FORBIDDEN_MESSAGE = (
    "Tylko właściciel wpisu (albo administrator) może zmienić jego widoczność lub go usunąć."
)


def scope_check_constraint() -> CheckConstraint:
    """CHECK: `scope='household'` wymaga `household_id`.

    Warunek żyje także w bazie, nie tylko w serwisie — wiersz „household bez
    rodziny" byłby niewidoczny dla nikogo poza właścicielem i po cichu łamał
    kontrakt widoczności.
    """
    return CheckConstraint(
        f"scope <> '{Scope.HOUSEHOLD.value}' OR household_id IS NOT NULL",
        name=SCOPE_CHECK_NAME,
    )


class ScopedMixin:
    """Kolumny wzorca scope (03_DATABASE §4) + PK `id` (konwencja 03_DATABASE §1).

    Model konsumujący NIE deklaruje ich ponownie::

        class Recipe(TimestampMixin, ScopedMixin, Base):
            __tablename__ = "recipes"
            name: Mapped[str] = mapped_column(Text, nullable=False)

    Model, który potrzebuje własnych `__table_args__`, musi dołożyć do nich
    `scope_check_constraint()` — inaczej straci gwarancję z bazy::

        __table_args__ = (scope_check_constraint(), Index("ix_recipes_name", "name"))
    """

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    #: Właściciel — encja bez właściciela nie istnieje, więc RESTRICT: konto
    #: z danymi kasuje się dopiero po ich przeniesieniu/usunięciu (ADR-012).
    owner_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    #: RESTRICT, nie SET NULL: wyzerowanie kolumny przy `scope='household'`
    #: złamałoby CHECK-a, a rodziny i tak kasuje się wyłącznie puste (409 used_in).
    household_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("households.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    scope: Mapped[Scope] = mapped_column(
        SCOPE_ENUM,
        nullable=False,
        default=Scope.PRIVATE,
        server_default=Scope.PRIVATE.value,
    )

    @declared_attr.directive
    def __table_args__(cls) -> tuple[Any, ...]:
        return (scope_check_constraint(),)


class ScopedQuery[ScopedT: ScopedMixin]:
    """Widoczność i uprawnienia jednej encji współdzielnej.

    UWAGA (ustalenie `/code-review` B08): `HouseholdScopedQuery` na dole pliku
    jest BLIŹNIAKIEM tej klasy — `select_visible` i `get_or_404` mają tam
    identyczne ciała. Poprawka którejkolwiek z nich MUSI trafić w oba miejsca,
    dopóki R3 nie wyciągnie wspólnej bazy (wspólny przodek wymaga rozluźnienia
    `ScopedT: ScopedMixin`, bo encja „zawsze household" nie ma kolumny `scope`).
    `assert_can_manage` bliźniak ma świadomie NIE mieć — patrz jego docstring.

    Serwis trzyma instancję jako atrybut klasy/modułu i woła jednolinijkowo::

        _RECIPES = ScopedQuery(Recipe, not_found_message="Nie znaleziono przepisu.")
        recipe = await _RECIPES.get_or_404(session, recipe_id, user)
        _RECIPES.assert_can_manage(recipe, user)   # zmiana scope / usunięcie
    """

    def __init__(
        self,
        model: type[ScopedT],
        *,
        not_found_message: str,
        forbidden_message: str = DEFAULT_FORBIDDEN_MESSAGE,
    ) -> None:
        self._model = model
        self._not_found_message = not_found_message
        self._forbidden_message = forbidden_message

    # --- odczyt ---------------------------------------------------------------

    def visible_condition(self, user: User) -> ColumnElement[bool]:
        """Warunek „widoczne dla mnie" z 03_DATABASE §4."""
        if user.role is UserRole.ADMIN:
            # ADMIN widzi wszystko (02_DOMAIN §2); mutacje i tak przechodzą
            # przez `assert_can_manage`, więc to nie jest obejście reguł.
            return true()

        own = self._model.owner_user_id == user.id
        if user.household_id is None:
            # Bez tego warunku `household_id = NULL` dopasowałoby cudze wiersze
            # bez rodziny (SQL: NULL = NULL to UNKNOWN, ale ORM zamienia to na IS NULL).
            return own
        return or_(
            own,
            and_(
                self._model.scope == Scope.HOUSEHOLD,
                self._model.household_id == user.household_id,
            ),
        )

    def select_visible(self, user: User) -> Select[tuple[ScopedT]]:
        """`SELECT` ograniczony do encji widocznych dla użytkownika."""
        return select(self._model).where(self.visible_condition(user))

    async def get_or_404(self, session: AsyncSession, entity_id: int, user: User) -> ScopedT:
        """Encja po id — cudza albo nieistniejąca kończy się identycznym 404."""
        entity = (
            await session.execute(self.select_visible(user).where(self._model.id == entity_id))
        ).scalar_one_or_none()
        if entity is None:
            raise NotFoundError(self._not_found_message)
        return entity

    # --- mutacje --------------------------------------------------------------

    def assert_can_manage(self, entity: ScopedT, user: User) -> None:
        """Zmiana scope i usunięcie: właściciel albo ADMIN (02_DOMAIN §3.1 pkt 2).

        Zwykła edycja treści encji HOUSEHOLD tego nie wymaga — rodzina sobie ufa,
        a kto zmienił, zapisuje audit log.
        """
        if user.role is UserRole.ADMIN or entity.owner_user_id == user.id:
            return
        raise ForbiddenError(self._forbidden_message)

    @staticmethod
    def assert_scope_allowed(user: User, scope: Scope) -> None:
        """Użytkownik bez rodziny nie może nadać scope HOUSEHOLD (03_DATABASE §4)."""
        if scope is Scope.HOUSEHOLD and user.household_id is None:
            raise ConflictError(NO_HOUSEHOLD_MESSAGE)

    @staticmethod
    def ownership_for_create(user: User, scope: Scope) -> dict[str, Any]:
        """Kolumny wzorca scope dla nowo tworzonej encji (po walidacji `scope`).

        `household_id` zapisujemy także dla PRIVATE — dzięki temu późniejsza
        zmiana scope na HOUSEHOLD nie wymaga zgadywania rodziny. Konsekwencja
        przenosin między rodzinami jest świadoma i opisana w ADR-006.
        """
        ScopedQuery.assert_scope_allowed(user, scope)
        return {
            "owner_user_id": user.id,
            "household_id": user.household_id,
            "scope": scope,
        }


# --- wariant „zawsze household" (spiżarnia, B08) -------------------------------------


class HouseholdScopedMixin:
    """Kolumny encji, która NIE MA wyboru scope — jest zawsze domowa (02_DOMAIN §3.1 pkt 1).

    Spiżarnia jest jednym stanem na rodzinę, więc kolumny `scope` nie ma
    (03_DATABASE §7): widoczność wynika wprost z `household_id`. Użytkownik bez
    rodziny ma spiżarnię osobistą — wiersz z `household_id IS NULL` wisi wtedy
    na `owner_user_id`. Dlatego NIE da się tu użyć `ScopedMixin`: jego CHECK
    (`scope <> 'household' OR household_id IS NOT NULL`) zabraniałby dokładnie
    tego przypadku.
    """

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    #: Kto dodał pozycję — RESTRICT jak we wzorcu scope (konto z danymi nie znika).
    owner_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    #: `NULL` = użytkownik bez rodziny (spiżarnia osobista), nie „brak danych".
    household_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("households.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )


class HouseholdScopedQuery[HouseholdScopedT: HouseholdScopedMixin]:
    """Widoczność encji „zawsze household" — bliźniak `ScopedQuery` bez kolumny scope.

    Warunek widoczności (karta B08, 03_DATABASE §7)::

        household_id = :user_household_id
        OR (household_id IS NULL AND owner_user_id = :uid)

    Dwie różnice wobec `ScopedQuery` są celowe:

    1. Samo `owner_user_id = :uid` NIE wystarcza do widoczności. Gdyby
       wystarczało, osoba, która odeszła z rodziny, dalej widziałaby jej
       spiżarnię — a to jeden stan domowy, nie zbiór prywatnych pozycji.
    2. **Nie ma tu `assert_can_manage`** — encja „zawsze household" nie ma
       właściciela w sensie uprawnień. Kto dodał pozycję, jest informacją
       (`owner_user_id` trafia do odpowiedzi), a nie przywilejem: usuwa ją
       każdy członek rodziny, tak samo jak ją edytuje. Decyzja właściciela
       **D17 z 2026-08-21**, wyjątek dopisany do 02_DOMAIN §3.1 pkt 2.

    UWAGA (ustalenie `/code-review` B08): `select_visible` i `get_or_404` są tu
    KOPIĄ tych z `ScopedQuery` — zmiana w jednym miejscu musi trafić w drugie,
    dopóki R3 nie wyciągnie wspólnej bazy.
    """

    def __init__(self, model: type[HouseholdScopedT], *, not_found_message: str) -> None:
        self._model = model
        self._not_found_message = not_found_message

    # --- odczyt ---------------------------------------------------------------

    def household_condition(self, user: User) -> ColumnElement[bool]:
        """Warunek „to jest stan MOJEGO domu" — BEZ wyjątku dla ADMIN-a.

        To nie jest widoczność, tylko przynależność. Silnik zakupowy (B10) pyta
        „co mamy w domu", a nie „co wolno mi zobaczyć": gdyby ADMIN dostał tu
        `true()`, jego lista zakupów odjęłaby spiżarnie wszystkich rodzin
        w instancji. Granica jest ta sama, co dla `/households/my` w 04_API §3
        pkt 2a — zasób zaadresowany MOJĄ rodziną pokazuje ADMIN-owi jego rodzinę.
        """
        personal = and_(self._model.household_id.is_(None), self._model.owner_user_id == user.id)
        if user.household_id is None:
            return personal
        return or_(self._model.household_id == user.household_id, personal)

    def visible_condition(self, user: User) -> ColumnElement[bool]:
        """Warunek „widoczne dla mnie"; ADMIN widzi wszystko (D16, 04_API §3 pkt 2)."""
        if user.role is UserRole.ADMIN:
            return true()
        return self.household_condition(user)

    def select_visible(self, user: User) -> Select[tuple[HouseholdScopedT]]:
        """`SELECT` ograniczony do encji widocznych dla użytkownika."""
        return select(self._model).where(self.visible_condition(user))

    def select_own_household(self, user: User) -> Select[tuple[HouseholdScopedT]]:
        """`SELECT` ograniczony do stanu WŁASNEGO domu (patrz `household_condition`)."""
        return select(self._model).where(self.household_condition(user))

    async def get_or_404(
        self, session: AsyncSession, entity_id: int, user: User
    ) -> HouseholdScopedT:
        """Encja po id — cudza albo nieistniejąca kończy się identycznym 404."""
        entity = (
            await session.execute(self.select_visible(user).where(self._model.id == entity_id))
        ).scalar_one_or_none()
        if entity is None:
            raise NotFoundError(self._not_found_message)
        return entity

    # --- mutacje --------------------------------------------------------------

    @staticmethod
    def ownership_for_create(user: User) -> dict[str, Any]:
        """Kolumny właścicielskie nowej encji: rodzina użytkownika albo on sam."""
        return {"owner_user_id": user.id, "household_id": user.household_id}
