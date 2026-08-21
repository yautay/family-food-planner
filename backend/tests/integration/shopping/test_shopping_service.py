"""Serwis zakupowy + baza: preset tur, `params`, finalizacja, blokady usuwania.

Scenariusze z karty B10 §Tests (integration). Motyw przewodni: `params` jest
JEDYNYM źródłem prawdy o podglądzie (karta B10, Implementation Notes pkt 3),
więc każdy odczyt i każda decyzja przechodzą przez ten sam silnik.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.core.scope import Scope
from app.modules.accounts.models import User
from app.modules.catalog.models import (
    CanonicalProduct,
    MeasureKind,
    Perishability,
    ProductCategory,
)
from app.modules.catalog.retail_service import RetailService
from app.modules.catalog.service import CatalogService
from app.modules.catalog.stores_service import StoresService
from app.modules.catalog.units import AmountUnit
from app.modules.planning.models import PlanMealItem
from app.modules.shopping.engine import IssueKind, RoundMode, generate_preview, load_input
from app.modules.shopping.models import GenerationStatus, ShoppingList, ShoppingRoundConfig
from app.modules.shopping.service import ShoppingService, ShoppingValidationError
from tests.factories import (
    assign_to_household,
    create_admin,
    create_category,
    create_household,
    create_ingredient,
    create_pantry_item,
    create_plan_day,
    create_plan_item,
    create_plan_meal,
    create_product,
    create_recipe,
    create_retail_product,
    create_round_config,
    create_store,
    create_user,
)

pytestmark = pytest.mark.integration

#: Poniedziałek — plan testowy trzyma się konwencji „daty z lat 2030+".
WEEK_START = date(2030, 1, 7)
WEEK_END = date(2030, 1, 13)
NOW = datetime(2030, 1, 6, 12, 0, tzinfo=UTC)


async def _plan_with_flour(
    session: AsyncSession, *, owner: User, amount: str = "1500", day: date = WEEK_START
) -> tuple[CanonicalProduct, ProductCategory]:
    """Dzień planu z jednym produktem luzem — najkrótsza droga do zapotrzebowania."""
    category = await create_category(
        session, name="Sypkie", perishability=Perishability.DURABLE, position=5
    )
    product = await create_product(
        session, category=category, name="Mąka pszenna", measure_kind=MeasureKind.MASS
    )
    plan_day = await create_plan_day(session, owner=owner, day=day)
    meal = await create_plan_meal(session, plan_day=plan_day, name="Obiad")
    await create_plan_item(
        session,
        meal=meal,
        product=product,
        amount=Decimal(amount),
        amount_unit=AmountUnit.GRAM,
    )
    return product, category


async def test_preset_tur_zasiewa_sie_raz_i_sie_nie_duplikuje(db_session: AsyncSession) -> None:
    """Pierwszy odczyt tworzy preset niedziela/środa; kolejne nic nie dokładają."""
    user = await create_user(db_session, email="tury@example.com")
    service = ShoppingService(db_session)

    first = await service.list_round_configs(user)
    second = await service.list_round_configs(user)

    assert [config.name for config in first] == ["Niedziela", "Środa"]
    assert [config.mode for config in first] == [
        RoundMode.DURABLE_PLUS_FRESH_WINDOW,
        RoundMode.FRESH_ONLY,
    ]
    assert (first[0].covers_days, first[0].fresh_days, first[0].shopping_weekday) == (7, 4, 6)
    assert (second[1].covers_days, second[1].fresh_days, second[1].shopping_weekday) == (
        3,
        None,
        2,
    )
    total = (
        await db_session.execute(select(func.count()).select_from(ShoppingRoundConfig))
    ).scalar_one()
    assert total == 2


async def test_preset_powstaje_jako_domowy_gdy_uzytkownik_ma_rodzine(
    db_session: AsyncSession,
) -> None:
    """Tury są ustaleniem domowym — z rodziną powstają jako HOUSEHOLD."""
    household = await create_household(db_session, name="Kowalscy")
    user = await create_user(db_session, email="rodzina@example.com")
    await assign_to_household(db_session, user=user, household=household)

    configs = await ShoppingService(db_session).list_round_configs(user)

    assert {config.scope for config in configs} == {Scope.HOUSEHOLD}
    assert {config.household_id for config in configs} == {household.id}


async def test_edycja_tury_czysci_okno_swiezych_po_zmianie_trybu(
    db_session: AsyncSession,
) -> None:
    """Okno świeżych ma sens tylko w jednym trybie — po zmianie nie zostaje w bazie."""
    user = await create_user(db_session, email="edycja@example.com")
    config = await create_round_config(db_session, owner=user)
    service = ShoppingService(db_session)

    updated = await service.update_round_config(
        config.id, user=user, changes={"mode": RoundMode.FRESH_ONLY}
    )

    assert updated.mode is RoundMode.FRESH_ONLY
    assert updated.fresh_days is None


async def test_cudza_tura_to_404_a_nie_403(db_session: AsyncSession) -> None:
    """Prywatna tura innego użytkownika jest nieodróżnialna od nieistniejącej."""
    owner = await create_user(db_session, email="wlasciciel@example.com")
    stranger = await create_user(db_session, email="obcy@example.com")
    config = await create_round_config(db_session, owner=owner)

    with pytest.raises(NotFoundError):
        await ShoppingService(db_session).update_round_config(
            config.id, user=stranger, changes={"name": "Podmiana"}
        )


async def test_generate_zapisuje_tylko_generacje_z_pelnym_params(
    db_session: AsyncSession,
) -> None:
    """`generate` nie tworzy żadnych list — wyłącznie szkic z pełnym wejściem silnika."""
    user = await create_user(db_session, email="generacja@example.com")
    await _plan_with_flour(db_session, owner=user)
    service = ShoppingService(db_session)

    view = await service.generate(user, date_from=WEEK_START, date_to=WEEK_END, use_pantry=False)

    assert view.generation.status is GenerationStatus.PREVIEW
    assert view.generation.used_pantry is False
    assert view.generation.params["v"] == 1
    # `params` jest w typach JSONB-em, więc do asercji sięgamy przez `load_input`.
    assert len(load_input(view.generation.params).items) == 1
    lists = (await db_session.execute(select(func.count()).select_from(ShoppingList))).scalar_one()
    assert lists == 0
    line = view.preview.rounds[0].items[0]
    assert line.needed_amount == Decimal("1500")


async def test_params_odtwarzaja_identyczny_preview(db_session: AsyncSession) -> None:
    """GET generacji liczy podgląd z `params`, bez ponownego pytania planu.

    Test dowodzi tego mocno: po zapisie generacji USUWAMY pozycję planu, a
    podgląd nadal wychodzi identyczny — bo materiał jest w `params`.
    """
    user = await create_user(db_session, email="odtworzenie@example.com")
    await _plan_with_flour(db_session, owner=user)
    service = ShoppingService(db_session)
    created = await service.generate(user, date_from=WEEK_START, date_to=WEEK_END)

    await db_session.execute(delete(PlanMealItem))
    await db_session.commit()

    reloaded = await service.get_generation(created.generation.id, user=user)

    assert reloaded.preview == created.preview
    assert generate_preview(load_input(created.generation.params)) == created.preview


async def test_spizarnia_odejmuje_sie_tylko_na_jawne_zyczenie(
    db_session: AsyncSession,
) -> None:
    """Bez `use_pantry` serwis nawet nie pyta bazy o stan domowy (02_DOMAIN §8)."""
    user = await create_user(db_session, email="spizarnia@example.com")
    product, _ = await _plan_with_flour(db_session, owner=user)
    await create_pantry_item(
        db_session,
        owner=user,
        product=product,
        amount=Decimal("400.000"),
    )
    service = ShoppingService(db_session)

    without = await service.generate(user, date_from=WEEK_START, date_to=WEEK_END)
    with_pantry = await service.generate(
        user, date_from=WEEK_START, date_to=WEEK_END, use_pantry=True
    )

    assert without.generation.params["pantry"] == []
    assert without.preview.rounds[0].items[0].needed_amount == Decimal("1500")
    assert with_pantry.preview.rounds[0].items[0].needed_amount == Decimal("1100")
    assert with_pantry.preview.rounds[0].items[0].from_pantry_amount == Decimal("400.000")


async def test_resolve_zapisuje_decyzje_i_przelicza_podglad(db_session: AsyncSession) -> None:
    """„Mam już w domu" i wybór wariantu lądują w `params` i zmieniają podgląd."""
    user = await create_user(db_session, email="resolve@example.com")
    product, _ = await _plan_with_flour(db_session, owner=user)
    small = await create_retail_product(
        db_session,
        product=product,
        name="Mąka 500 g",
        package_amount=Decimal("500.00"),
    )
    big = await create_retail_product(
        db_session,
        product=product,
        name="Mąka 2 kg",
        package_amount=Decimal("2000.00"),
    )
    service = ShoppingService(db_session)
    created = await service.generate(user, date_from=WEEK_START, date_to=WEEK_END)

    # Automat wybiera najmniejszą resztkę: 3 x 500 g pokrywa 1500 g bez reszty.
    assert created.preview.rounds[0].items[0].retail_product_id == small.id
    assert created.preview.rounds[0].items[0].leftover_amount == Decimal("0")

    resolved = await service.resolve(
        created.generation.id,
        user=user,
        retail_choices=[(product.id, big.id)],
    )

    line = resolved.preview.rounds[0].items[0]
    assert line.retail_product_id == big.id
    assert line.packages_count == 1
    assert line.leftover_amount == Decimal("500.00")
    assert resolved.generation.params["retail_choices"] == [
        {"product_id": product.id, "retail_product_id": big.id}
    ]
    # Podgląd echuje JAWNE wybory: bez tego UI nie odróżni wariantu wskazanego
    # przez człowieka od dobranego automatem (ustalenie /code-review B10).
    assert resolved.preview.retail_choices == ((product.id, big.id),)
    assert created.preview.retail_choices == ()

    marked = await service.resolve(created.generation.id, user=user, already_have=[product.id])
    assert marked.preview.rounds[0].items[0].already_have is True
    assert marked.generation.params["already_have"] == [product.id]


async def test_resolve_widzi_wariant_utworzony_po_generacji(db_session: AsyncSession) -> None:
    """Inline create produktu sklepowego działa bez generowania zakupów od nowa."""
    user = await create_user(db_session, email="inline@example.com")
    product, _ = await _plan_with_flour(db_session, owner=user)
    service = ShoppingService(db_session)
    created = await service.generate(user, date_from=WEEK_START, date_to=WEEK_END)
    assert created.preview.rounds[0].items[0].retail_options == ()

    variant = await create_retail_product(
        db_session,
        product=product,
        name="Mąka 1 kg",
        package_amount=Decimal("1000.00"),
    )
    resolved = await service.resolve(created.generation.id, user=user)

    line = resolved.preview.rounds[0].items[0]
    assert [option.retail_product_id for option in line.retail_options] == [variant.id]
    assert line.packages_count == 2


async def test_resolve_odrzuca_wariant_innego_produktu(db_session: AsyncSession) -> None:
    """Wybór wariantu nienależącego do produktu to 422, nie cicha podmiana."""
    user = await create_user(db_session, email="obcy-wariant@example.com")
    product, category = await _plan_with_flour(db_session, owner=user)
    other = await create_product(db_session, category=category, name="Ryż")
    foreign = await create_retail_product(db_session, product=other, name="Ryż 1 kg")
    service = ShoppingService(db_session)
    created = await service.generate(user, date_from=WEEK_START, date_to=WEEK_END)

    with pytest.raises(ShoppingValidationError):
        await service.resolve(
            created.generation.id,
            user=user,
            retail_choices=[(product.id, foreign.id)],
        )


async def test_finalize_tworzy_listy_per_tura_z_kompletem_kolumn(
    db_session: AsyncSession,
) -> None:
    """Finalizacja daje po jednej liście na turę i wypełnia wszystkie kolumny pozycji."""
    user = await create_user(db_session, email="finalize@example.com")
    fresh = await create_category(
        db_session, name="Warzywa", perishability=Perishability.FRESH, position=0
    )
    durable = await create_category(
        db_session, name="Sypkie", perishability=Perishability.DURABLE, position=5
    )
    tomato = await create_product(db_session, category=fresh, name="Pomidor")
    flour = await create_product(db_session, category=durable, name="Mąka")
    await create_retail_product(
        db_session, product=flour, name="Mąka 1 kg", package_amount=Decimal("1000.00")
    )
    for offset in range(7):
        plan_day = await create_plan_day(
            db_session, owner=user, day=WEEK_START + timedelta(days=offset)
        )
        meal = await create_plan_meal(db_session, plan_day=plan_day, name="Obiad")
        await create_plan_item(
            db_session,
            meal=meal,
            product=tomato,
            amount=Decimal("100"),
            amount_unit=AmountUnit.GRAM,
        )
        await create_plan_item(
            db_session,
            meal=meal,
            product=flour,
            amount=Decimal("200"),
            amount_unit=AmountUnit.GRAM,
            position=1,
        )
    service = ShoppingService(db_session)
    created = await service.generate(user, date_from=WEEK_START, date_to=WEEK_END, use_pantry=False)

    views = await service.finalize(created.generation.id, user=user, now=NOW)

    assert [view.shopping_list.round_name for view in views] == ["Niedziela", "Środa"]
    assert views[0].shopping_list.name == "Zakupy 07.01-13.01.2030"
    assert views[0].shopping_list.expires_at == NOW + timedelta(days=7)
    assert views[0].shopping_list.public_token is None
    assert views[0].shopping_list.token_revoked is False

    sunday_labels = [item.label for item in views[0].items]
    assert sunday_labels == ["Pomidor", "Mąka 1 kg"]
    tomato_item, flour_item = views[0].items
    assert (tomato_item.needed_amount, tomato_item.amount_unit) == (
        Decimal("400.000"),
        AmountUnit.GRAM,
    )
    assert tomato_item.packages_count is None
    assert tomato_item.from_pantry_amount is None
    assert tomato_item.position == 0
    assert (flour_item.packages_count, flour_item.package_size) == (2, Decimal("1000.00"))
    assert flour_item.leftover_amount == Decimal("600.000")
    assert flour_item.retail_product_id is not None
    assert flour_item.checked is False

    wednesday = views[1]
    assert [item.label for item in wednesday.items] == ["Pomidor"]
    assert wednesday.items[0].needed_amount == Decimal("300.000")

    refreshed = await service.get_generation(created.generation.id, user=user)
    assert refreshed.generation.status is GenerationStatus.FINAL


async def test_finalize_z_blokerem_konczy_sie_409(db_session: AsyncSession) -> None:
    """Nierozstrzygnięty bloker wstrzymuje finalizację i mówi, co jest nie tak."""
    user = await create_user(db_session, email="bloker@example.com")
    category = await create_category(db_session, name="Napoje", position=1)
    milk = await create_product(
        db_session, category=category, name="Mleko", measure_kind=MeasureKind.VOLUME
    )
    plan_day = await create_plan_day(db_session, owner=user, day=WEEK_START)
    meal = await create_plan_meal(db_session, plan_day=plan_day, name="Śniadanie")
    await create_plan_item(
        db_session,
        meal=meal,
        product=milk,
        amount=Decimal("200"),
        amount_unit=AmountUnit.MILLILITER,
    )
    # ADMIN zmienia sposób liczenia PO zapisaniu pozycji (D15): ilość w ml
    # przestaje dać się przeliczyć na gramy.
    milk.measure_kind = MeasureKind.MASS
    await db_session.commit()

    service = ShoppingService(db_session)
    created = await service.generate(user, date_from=WEEK_START, date_to=WEEK_END)
    assert created.preview.issues[0].kind is IssueKind.PLAN_ITEM_WITHOUT_AMOUNT

    with pytest.raises(ConflictError) as exc:
        await service.finalize(created.generation.id, user=user, now=NOW)
    assert exc.value.status_code == 409
    assert exc.value.details is not None
    assert exc.value.details["issues"][0]["kind"] == IssueKind.PLAN_ITEM_WITHOUT_AMOUNT.value


async def test_odlozenie_blokera_pozwala_sfinalizowac(db_session: AsyncSession) -> None:
    """Świadome odłożenie niejasności odblokowuje finalizację (pozycja nie wchodzi)."""
    user = await create_user(db_session, email="odlozenie@example.com")
    category = await create_category(db_session, name="Napoje", position=1)
    milk = await create_product(
        db_session, category=category, name="Mleko", measure_kind=MeasureKind.VOLUME
    )
    flour = await create_product(db_session, category=category, name="Mąka")
    plan_day = await create_plan_day(db_session, owner=user, day=WEEK_START)
    meal = await create_plan_meal(db_session, plan_day=plan_day, name="Śniadanie")
    await create_plan_item(
        db_session,
        meal=meal,
        product=milk,
        amount=Decimal("200"),
        amount_unit=AmountUnit.MILLILITER,
    )
    await create_plan_item(
        db_session,
        meal=meal,
        product=flour,
        amount=Decimal("300"),
        amount_unit=AmountUnit.GRAM,
        position=1,
    )
    milk.measure_kind = MeasureKind.MASS
    await db_session.commit()

    service = ShoppingService(db_session)
    created = await service.generate(user, date_from=WEEK_START, date_to=WEEK_END)
    key = created.preview.issues[0].key

    resolved = await service.resolve(created.generation.id, user=user, dismissed_issues=[key])
    assert resolved.preview.issues[0].dismissed is True

    views = await service.finalize(created.generation.id, user=user, now=NOW)
    assert [item.label for item in views[0].items] == ["Mąka"]


async def test_finalize_bez_zakupow_konczy_sie_409(db_session: AsyncSession) -> None:
    """Pusty zakres nie tworzy list — zamiast tego mówi, co sprawdzić."""
    user = await create_user(db_session, email="pusto@example.com")
    service = ShoppingService(db_session)
    created = await service.generate(user, date_from=WEEK_START, date_to=WEEK_END)

    with pytest.raises(ConflictError):
        await service.finalize(created.generation.id, user=user, now=NOW)


async def test_pozycja_pokryta_spizarnia_nie_wchodzi_na_liste(
    db_session: AsyncSession,
) -> None:
    """Nie ma czego kupować ⇒ pozycji nie ma na liście, ale „mam w domu" tak."""
    user = await create_user(db_session, email="pokryte@example.com")
    product, category = await _plan_with_flour(db_session, owner=user, amount="300")
    rice = await create_product(db_session, category=category, name="Ryż")
    # Drugi dzień, nie drugi wiersz tej samej daty: `plan_days` ma UNIQUE
    # (owner_user_id, day) — jeden plan dnia na użytkownika i datę (B06).
    plan_day = await create_plan_day(db_session, owner=user, day=WEEK_START + timedelta(days=1))
    meal = await create_plan_meal(db_session, plan_day=plan_day, name="Kolacja")
    await create_plan_item(
        db_session, meal=meal, product=rice, amount=Decimal("100"), amount_unit=AmountUnit.GRAM
    )
    await create_pantry_item(
        db_session,
        owner=user,
        product=product,
        amount=Decimal("1000.000"),
    )
    service = ShoppingService(db_session)
    created = await service.generate(user, date_from=WEEK_START, date_to=WEEK_END, use_pantry=True)
    await service.resolve(created.generation.id, user=user, already_have=[rice.id])

    views = await service.finalize(created.generation.id, user=user, now=NOW)

    labels = [item.label for view in views for item in view.items]
    assert labels == ["Ryż"]
    assert views[0].items[0].already_have is True


async def test_sfinalizowanej_generacji_nie_da_sie_zmienic(db_session: AsyncSession) -> None:
    """Po utworzeniu list generacja jest zamknięta: `resolve` i `finalize` dają 409."""
    user = await create_user(db_session, email="zamknieta@example.com")
    await _plan_with_flour(db_session, owner=user)
    service = ShoppingService(db_session)
    created = await service.generate(user, date_from=WEEK_START, date_to=WEEK_END)
    await service.finalize(created.generation.id, user=user, now=NOW)

    with pytest.raises(ConflictError):
        await service.resolve(created.generation.id, user=user, already_have=[])
    with pytest.raises(ConflictError):
        await service.finalize(created.generation.id, user=user, now=NOW)
    with pytest.raises(ConflictError):
        await service.discard(created.generation.id, user=user)


async def test_odrzucenie_szkicu_zostawia_wiersz_w_bazie(db_session: AsyncSession) -> None:
    """DELETE generacji jest MIĘKKIE — historia to wartość (D10)."""
    user = await create_user(db_session, email="odrzucenie@example.com")
    await _plan_with_flour(db_session, owner=user)
    service = ShoppingService(db_session)
    created = await service.generate(user, date_from=WEEK_START, date_to=WEEK_END)

    await service.discard(created.generation.id, user=user)

    reloaded = await service.get_generation(created.generation.id, user=user)
    assert reloaded.generation.status is GenerationStatus.DISCARDED


async def test_cudza_generacja_to_404(db_session: AsyncSession) -> None:
    """Anty-IDOR: generacja innego użytkownika jest nieodróżnialna od nieistniejącej."""
    owner = await create_user(db_session, email="moja@example.com")
    stranger = await create_user(db_session, email="nie-moja@example.com")
    await _plan_with_flour(db_session, owner=owner)
    service = ShoppingService(db_session)
    created = await service.generate(owner, date_from=WEEK_START, date_to=WEEK_END)

    with pytest.raises(NotFoundError):
        await service.get_generation(created.generation.id, user=stranger)
    with pytest.raises(NotFoundError):
        await service.resolve(created.generation.id, user=stranger, already_have=[])
    with pytest.raises(NotFoundError):
        await service.finalize(created.generation.id, user=stranger, now=NOW)


async def test_generacja_liczy_przepisy_z_planu(db_session: AsyncSession) -> None:
    """Pozycja z przepisem rozwija się do składników x mnożnik / porcje bazowe."""
    user = await create_user(db_session, email="przepis@example.com")
    category = await create_category(
        db_session, name="Warzywa", perishability=Perishability.FRESH, position=0
    )
    onion = await create_product(db_session, category=category, name="Cebula")
    recipe = await create_recipe(db_session, owner=user, name="Zupa", base_servings=2)
    await create_ingredient(
        db_session,
        recipe=recipe,
        product=onion,
        amount=Decimal("300"),
        amount_unit=AmountUnit.GRAM,
    )
    plan_day = await create_plan_day(db_session, owner=user, day=WEEK_START)
    meal = await create_plan_meal(db_session, plan_day=plan_day, name="Obiad")
    await create_plan_item(db_session, meal=meal, recipe=recipe, servings=Decimal("3.00"))

    view = await ShoppingService(db_session).generate(user, date_from=WEEK_START, date_to=WEEK_END)

    assert view.preview.rounds[0].items[0].needed_amount == Decimal("450")


async def test_produkt_z_listy_zakupowej_blokuje_usuniecie_produktu(
    db_session: AsyncSession,
) -> None:
    """Licznik referencji daje 409 z listą „Używane w:" (ADR-012, rejestr B04)."""
    admin = await create_admin(db_session, email="admin-lista@example.com")
    product, _ = await _plan_with_flour(db_session, owner=admin)
    service = ShoppingService(db_session)
    created = await service.generate(admin, date_from=WEEK_START, date_to=WEEK_END)
    await service.finalize(created.generation.id, user=admin, now=NOW)

    with pytest.raises(ConflictError) as exc:
        await CatalogService(db_session).delete_product(product.id, actor=admin)

    assert exc.value.details is not None
    used_in = exc.value.details["used_in"]
    # Produkt trzyma i plan (rejestr B06), i lista zakupowa (rejestr tego batcha)
    # — użytkownik ma zobaczyć OBA miejsca użycia, nie tylko pierwsze.
    assert {entry["type"] for entry in used_in} == {"plan_day", "shopping_list"}
    assert "Zakupy 07.01-13.01.2030" in [entry["name"] for entry in used_in]


async def test_wariant_z_listy_zakupowej_blokuje_usuniecie_wariantu(
    db_session: AsyncSession,
) -> None:
    """To samo dla wariantu sklepowego (karta B09 §Context pkt 3)."""
    user = await create_user(db_session, email="wariant-lista@example.com")
    product, _ = await _plan_with_flour(db_session, owner=user)
    variant = await create_retail_product(
        db_session,
        product=product,
        name="Mąka 1 kg",
        package_amount=Decimal("1000.00"),
    )
    service = ShoppingService(db_session)
    created = await service.generate(user, date_from=WEEK_START, date_to=WEEK_END)
    await service.finalize(created.generation.id, user=user, now=NOW)

    with pytest.raises(ConflictError) as exc:
        await RetailService(db_session).delete_retail_product(variant.id, actor=user)

    assert exc.value.details is not None
    assert exc.value.details["used_in"][0]["type"] == "shopping_list"


async def test_sklep_przypisany_do_listy_blokuje_usuniecie_sklepu(
    db_session: AsyncSession,
) -> None:
    """FK ma SET NULL, więc bez licznika lista po cichu straciłaby profil sklepu."""
    user = await create_user(db_session, email="sklep-lista@example.com")
    store = await create_store(db_session, name="Biedronka")
    await _plan_with_flour(db_session, owner=user)
    service = ShoppingService(db_session)
    created = await service.generate(user, date_from=WEEK_START, date_to=WEEK_END)
    views = await service.finalize(created.generation.id, user=user, now=NOW)
    views[0].shopping_list.store_id = store.id
    await db_session.commit()

    with pytest.raises(ConflictError) as exc:
        await StoresService(db_session).delete_store(store.id, actor=user)

    assert exc.value.details is not None
    assert exc.value.details["used_in"][0]["type"] == "shopping_list"


async def test_wskazanie_cudzej_tury_w_generacji_to_422(db_session: AsyncSession) -> None:
    """`round_config_ids` z cudzą turą nie przechodzi — nie zgadujemy, co miał na myśli."""
    owner = await create_user(db_session, email="tura-wlasciciel@example.com")
    stranger = await create_user(db_session, email="tura-obcy@example.com")
    config = await create_round_config(db_session, owner=owner)

    with pytest.raises(ShoppingValidationError):
        await ShoppingService(db_session).generate(
            stranger,
            date_from=WEEK_START,
            date_to=WEEK_END,
            round_config_ids=[config.id],
        )


async def test_pusta_lista_tur_daje_jedna_ture_zastepcza(db_session: AsyncSession) -> None:
    """Bez tur zapotrzebowanie musi mieć gdzie trafić — jedna tura na cały zakres."""
    user = await create_user(db_session, email="bez-tur@example.com")
    await _plan_with_flour(db_session, owner=user)

    view = await ShoppingService(db_session).generate(
        user, date_from=WEEK_START, date_to=WEEK_END, round_config_ids=[]
    )

    assert [round_view.key for round_view in view.preview.rounds] == ["all"]
    assert view.preview.rounds[0].items[0].needed_amount == Decimal("1500")
