"""Szablony i cykle + baza: brak live-sync, blokady JSONB, blok 2+2+2, apply cyklu.

Scenariusze z karty B07 §Tests (integration). Dwa motywy przewodnie:

1. **Szablon to ZAMROŻONA KOPIA** (02_DOMAIN §7) — instancjacja przepisuje
   strukturę, więc od tej chwili plan i szablon żyją osobno. Testy jadą w OBIE
   strony, bo „live-sync" najłatwiej wprowadzić przez przypadek w jedną z nich.
2. **Referencje w payloadzie JSONB blokują usuwanie** (ADR-012) — baza nie ma tu
   FK, więc jedyną obroną jest licznik referencji. Bez tych testów usunięcie
   przepisu zostawiłoby szablon wskazujący w pustkę.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.core.scope import Scope
from app.modules.accounts.models import User
from app.modules.catalog.models import CanonicalProduct, VerificationStatus
from app.modules.catalog.service import CatalogService
from app.modules.planning.models import DayTemplate, PlanDay, PlanMeal, PlanMealItem
from app.modules.planning.schemas import (
    CycleApplyRequest,
    CycleWriteRequest,
    DayTemplatePayload,
    DayTemplateWriteRequest,
    MealCreateRequest,
    PlanCopyRequest,
)
from app.modules.planning.service import PlanningService, PlanValidationError
from app.modules.planning.templates_service import TemplatesService
from app.modules.recipes.models import Recipe
from app.modules.recipes.service import RecipesService
from tests.factories import (
    create_admin,
    create_category,
    create_day_template,
    create_household,
    create_ingredient,
    create_member_profile,
    create_plan_day,
    create_plan_item,
    create_plan_meal,
    create_product,
    create_recipe,
    create_user,
    create_week_cycle,
    create_week_template,
    day_payload,
    template_meal,
    template_product_item,
    template_recipe_item,
)

pytestmark = pytest.mark.integration

#: Poniedziałek — wszystkie scenariusze tygodniowe liczą się od niego.
MONDAY = date(2026, 8, 17)
TUESDAY = date(2026, 8, 18)
NEXT_MONDAY = date(2026, 8, 24)


def _days(count: int) -> timedelta:
    return timedelta(days=count)


async def _count(session: AsyncSession, table: object) -> int:
    return int(
        (await session.execute(select(func.count()).select_from(table))).scalar_one()  # type: ignore[arg-type]
    )


async def _full_product(session: AsyncSession, *, name: str = "Skyr") -> CanonicalProduct:
    """Produkt 60 kcal/100 g z kompletem wartości — wyniki liczą się „na czysto"."""
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
        glycemic_index=Decimal("25"),
        verification_status=VerificationStatus.VERIFIED,
    )


async def _day_with_meal(session: AsyncSession, user: User, day: date) -> tuple[PlanDay, Recipe]:
    """Dzień planu z jednym posiłkiem i pozycją z przepisu."""
    recipe = await create_recipe(session, owner=user, name=f"Danie {day.isoformat()}")
    product = await _full_product(session, name=f"Produkt {day.isoformat()}")
    await create_ingredient(session, recipe=recipe, product=product, amount=Decimal("200.000"))
    plan_day = await create_plan_day(session, owner=user, day=day, title=f"Dzień {day.day}")
    meal = await create_plan_meal(session, plan_day=plan_day, name="Obiad")
    await create_plan_item(session, meal=meal, recipe=recipe, servings=Decimal("2.00"))
    return plan_day, recipe


# --- szablon = zamrożona kopia (02_DOMAIN §7) ---------------------------------------


async def test_instancjacja_kopiuje_wartosci_a_nie_zywe_referencje(
    db_session: AsyncSession,
) -> None:
    """Zmiana szablonu PO instancjacji nie rusza planu (brak live-sync)."""
    user = await create_user(db_session)
    _plan_day, recipe = await _day_with_meal(db_session, user, MONDAY)
    templates = TemplatesService(db_session)

    template = await templates.create_day_template(
        user=user,
        payload=DayTemplateWriteRequest(name="Szablon", from_date=MONDAY),
    )
    await templates.instantiate_day_template(template.id, user=user, dates=[NEXT_MONDAY])

    plan_before = await PlanningService(db_session).get_day(user, NEXT_MONDAY)
    assert [meal.meal.name for meal in plan_before.meals] == ["Obiad"]

    # Nadpisujemy CAŁY payload szablonu — plan ma tego nie zauważyć.
    await templates.update_day_template(
        template.id,
        user=user,
        payload=DayTemplateWriteRequest(
            name="Szablon po zmianie",
            payload=DayTemplatePayload.model_validate(
                day_payload(meals=[template_meal(name="Kolacja")])
            ),
        ),
    )

    plan_after = await PlanningService(db_session).get_day(user, NEXT_MONDAY)
    assert [meal.meal.name for meal in plan_after.meals] == ["Obiad"]
    assert plan_after.meals[0].items[0].item.recipe_id == recipe.id


async def test_zmiana_planu_nie_rusza_szablonu(db_session: AsyncSession) -> None:
    """Druga strona braku live-sync: plan edytowany po zapisie szablonu."""
    user = await create_user(db_session)
    plan_day, _recipe = await _day_with_meal(db_session, user, MONDAY)
    templates = TemplatesService(db_session)

    template = await templates.create_day_template(
        user=user, payload=DayTemplateWriteRequest(name="Szablon", from_date=MONDAY)
    )
    payload_before = dict(template.payload)

    # Dokładamy posiłek do DNIA, z którego szablon powstał.
    await PlanningService(db_session).create_meal(
        user, MONDAY, MealCreateRequest(name="Podwieczorek")
    )

    refreshed = await templates.get_day_template(template.id, user=user)
    assert refreshed.payload == payload_before
    assert len(refreshed.payload["meals"]) == 1  # type: ignore[arg-type]
    assert plan_day.id is not None


async def test_szablon_z_pustego_dnia_jest_odrzucany(db_session: AsyncSession) -> None:
    """„Zapisz jako szablon" na pustym dniu to pomyłka użytkownika, nie pusty szablon."""
    user = await create_user(db_session)
    templates = TemplatesService(db_session)

    with pytest.raises(PlanValidationError, match="pusty"):
        await templates.create_day_template(
            user=user, payload=DayTemplateWriteRequest(name="Pusty", from_date=MONDAY)
        )


# --- blokada usuwania przez payload JSONB (ADR-012) --------------------------------


async def test_usuniecie_przepisu_z_payloadu_szablonu_dnia_daje_409(
    db_session: AsyncSession,
) -> None:
    """Przepis TYLKO w payloadzie szablonu ⇒ 409 z nazwą szablonu w `used_in`.

    Baza nie pomoże: w `day_templates` nie ma FK do `recipes`, bo referencja
    siedzi w JSONB. Gdyby licznik referencji tego nie widział, DELETE przeszedłby
    i szablon wskazywałby na nieistniejący przepis.
    """
    user = await create_user(db_session)
    recipe = await create_recipe(db_session, owner=user, name="Gołąbki")
    template = await create_day_template(
        db_session,
        owner=user,
        name="Szablon z gołąbkami",
        payload=day_payload(meals=[template_meal(items=[template_recipe_item(recipe.id)])]),
    )

    with pytest.raises(ConflictError) as error:
        await RecipesService(db_session).delete_recipe(recipe.id, actor=user)

    assert error.value.details["used_in"] == [
        {"type": "day_template", "id": template.id, "name": "Szablon z gołąbkami"}
    ]


async def test_usuniecie_przepisu_z_payloadu_szablonu_tygodnia_daje_409(
    db_session: AsyncSession,
) -> None:
    """To samo o poziom głębiej: `days[].day.meals[].items[].recipe_id`."""
    user = await create_user(db_session)
    recipe = await create_recipe(db_session, owner=user, name="Zupa")
    await create_week_template(
        db_session,
        owner=user,
        name="Tydzień z zupą",
        payload={
            "v": 1,
            "days": [
                {
                    "offset": 2,
                    "day": day_payload(
                        meals=[template_meal(items=[template_recipe_item(recipe.id)])]
                    ),
                }
            ],
        },
    )

    with pytest.raises(ConflictError) as error:
        await RecipesService(db_session).delete_recipe(recipe.id, actor=user)

    used_in = error.value.details["used_in"]
    assert [row["type"] for row in used_in] == ["week_template"]
    assert used_in[0]["name"] == "Tydzień z zupą"


async def test_usuniecie_produktu_z_payloadu_szablonu_daje_409(
    db_session: AsyncSession,
) -> None:
    """Produkt luzem w payloadzie blokuje usunięcie tak samo jak przepis."""
    admin = await create_admin(db_session)
    product = await _full_product(db_session, name="Cebula")
    await create_day_template(
        db_session,
        owner=admin,
        name="Szablon z cebulą",
        payload=day_payload(meals=[template_meal(items=[template_product_item(product.id)])]),
    )

    with pytest.raises(ConflictError) as error:
        await CatalogService(db_session).delete_product(product.id, actor=admin)

    used_in = error.value.details["used_in"]
    assert [(row["type"], row["name"]) for row in used_in] == [("day_template", "Szablon z cebulą")]


async def test_po_usunieciu_szablonu_przepis_da_sie_usunac(db_session: AsyncSession) -> None:
    """Blokada jest warunkowa, nie trwała — to warunek sensowności całego 409."""
    user = await create_user(db_session)
    recipe = await create_recipe(db_session, owner=user, name="Naleśniki")
    template = await create_day_template(
        db_session,
        owner=user,
        payload=day_payload(meals=[template_meal(items=[template_recipe_item(recipe.id)])]),
    )

    with pytest.raises(ConflictError):
        await RecipesService(db_session).delete_recipe(recipe.id, actor=user)

    await TemplatesService(db_session).delete_day_template(template.id, user=user)
    await RecipesService(db_session).delete_recipe(recipe.id, actor=user)

    assert await _count(db_session, DayTemplate) == 0


async def test_szablon_bez_tego_przepisu_nie_blokuje_usuwania(db_session: AsyncSession) -> None:
    """Containment `@>` musi dopasowywać ID, a nie „cokolwiek w tym miejscu"."""
    user = await create_user(db_session)
    used = await create_recipe(db_session, owner=user, name="Użyty")
    free = await create_recipe(db_session, owner=user, name="Wolny")
    await create_day_template(
        db_session,
        owner=user,
        payload=day_payload(meals=[template_meal(items=[template_recipe_item(used.id)])]),
    )

    await RecipesService(db_session).delete_recipe(free.id, actor=user)

    with pytest.raises(ConflictError):
        await RecipesService(db_session).delete_recipe(used.id, actor=user)


async def test_indeksy_gin_na_payloadach_istnieja(db_session: AsyncSession) -> None:
    """ADR-012: bez indeksu GIN każdy DELETE przepisu skanowałby wszystkie szablony."""
    rows = (
        await db_session.execute(
            text(
                "SELECT tablename, indexname, indexdef FROM pg_indexes "
                "WHERE indexname IN "
                "('ix_day_templates_payload_gin', 'ix_week_templates_payload_gin') "
                "ORDER BY indexname"
            )
        )
    ).all()

    assert [row[0] for row in rows] == ["day_templates", "week_templates"]
    for row in rows:
        assert "USING gin" in row[2]
        assert "jsonb_path_ops" in row[2]


async def test_zapytanie_zliczajace_referencje_uzywa_indeksu_gin(
    db_session: AsyncSession,
) -> None:
    """EXPLAIN potwierdza, że containment `@>` faktycznie sięga po indeks GIN.

    Planner wybiera indeks tylko wtedy, gdy uzna to za tańsze, a na pustej
    tabeli seq scan zawsze wygrywa — dlatego wyłączamy go na czas testu
    (`enable_seqscan`). Test pilnuje ZDOLNOŚCI zapytania do użycia indeksu,
    czyli tego, co ADR-012 faktycznie wymaga: gdyby operator był niezgodny
    z `jsonb_path_ops`, planner nie miałby czego wybrać i EXPLAIN pokazałby
    seq scan nawet z wyłączoną tą opcją.
    """
    user = await create_user(db_session)
    recipe = await create_recipe(db_session, owner=user, name="Indeksowany")
    await create_day_template(
        db_session,
        owner=user,
        payload=day_payload(meals=[template_meal(items=[template_recipe_item(recipe.id)])]),
    )

    await db_session.execute(text("SET LOCAL enable_seqscan = off"))
    # Wzorzec jedzie PARAMETREM, nie wklejony w SQL: `text()` traktuje `:1`
    # z literału JSON (`"recipe_id":1`) jako nazwę parametru wiązanego i wysypuje
    # się na „A value is required for bind parameter '1'".
    pattern = json.dumps({"meals": [{"items": [{"recipe_id": recipe.id}]}]})
    plan = "\n".join(
        row[0]
        for row in (
            await db_session.execute(
                text(
                    "EXPLAIN SELECT id FROM day_templates WHERE payload @> CAST(:pattern AS jsonb)"
                ),
                {"pattern": pattern},
            )
        ).all()
    )

    assert "ix_day_templates_payload_gin" in plan, plan


# --- powiel blok (2+2+2) -------------------------------------------------------------


async def test_blok_dwa_dwa_dwa_daje_szesc_dni_w_kolejnosci_par(
    db_session: AsyncSession,
) -> None:
    """3 dni źródłowe x 2 powtórzenia ⇒ d1,d1,d2,d2,d3,d3 na 6 kolejnych datach."""
    user = await create_user(db_session)
    for offset in range(3):
        await _day_with_meal(db_session, user, MONDAY + _days(offset))

    target = date(2026, 9, 7)
    views = await PlanningService(db_session).copy_block(
        user=user,
        payload=PlanCopyRequest(
            what="block", source_from=MONDAY, source_days=3, repeat_each=2, target_start=target
        ),
    )

    assert [view.day for view in views] == [target + _days(offset) for offset in range(6)]
    # Nazwa przepisu niesie datę dnia źródłowego, więc kolejność jest widoczna wprost.
    portions = [view.meals[0].items[0].recipe for view in views]
    assert all(portion is not None for portion in portions)
    names = [portion.name for portion in portions if portion is not None]
    assert names == [
        f"Danie {MONDAY.isoformat()}",
        f"Danie {MONDAY.isoformat()}",
        f"Danie {(MONDAY + _days(1)).isoformat()}",
        f"Danie {(MONDAY + _days(1)).isoformat()}",
        f"Danie {(MONDAY + _days(2)).isoformat()}",
        f"Danie {(MONDAY + _days(2)).isoformat()}",
    ]


async def test_blok_jest_gleboka_kopia(db_session: AsyncSession) -> None:
    """Edycja kopii nie rusza źródła — nowe id posiłków i pozycji."""
    user = await create_user(db_session)
    source_day, _recipe = await _day_with_meal(db_session, user, MONDAY)
    planning = PlanningService(db_session)

    target = date(2026, 9, 7)
    await planning.copy_block(
        user=user,
        payload=PlanCopyRequest(
            what="block", source_from=MONDAY, source_days=1, repeat_each=2, target_start=target
        ),
    )

    copy_view = await planning.get_day(user, target)
    copied_item = copy_view.meals[0].items[0].item
    await planning.delete_item(copied_item.id, user=user)

    source_view = await planning.get_day(user, MONDAY)
    assert len(source_view.meals[0].items) == 1
    assert source_view.entity is not None and source_view.entity.id == source_day.id


async def test_blok_pomija_dziury_w_zakresie_zrodlowym(db_session: AsyncSession) -> None:
    """Pusty dzień w bloku daje pusty dzień docelowy, a nie błąd całej operacji."""
    user = await create_user(db_session)
    await _day_with_meal(db_session, user, MONDAY)
    # środkowy dzień (TUESDAY) celowo pusty
    await _day_with_meal(db_session, user, MONDAY + _days(2))

    target = date(2026, 9, 7)
    views = await PlanningService(db_session).copy_block(
        user=user,
        payload=PlanCopyRequest(
            what="block", source_from=MONDAY, source_days=3, repeat_each=1, target_start=target
        ),
    )

    assert [len(view.meals) for view in views] == [1, 0, 1]


# --- instancjacja tygodnia -----------------------------------------------------------


async def test_instancjacja_tygodnia_tworzy_dni_po_offsetach(db_session: AsyncSession) -> None:
    """Payload z offsetami 0 i 3 ⇒ poniedziałek i czwartek."""
    user = await create_user(db_session)
    recipe = await create_recipe(db_session, owner=user, name="Danie tygodnia")
    template = await create_week_template(
        db_session,
        owner=user,
        payload={
            "v": 1,
            "days": [
                {"offset": 0, "day": day_payload(meals=[template_meal(name="Poniedziałkowy")])},
                {
                    "offset": 3,
                    "day": day_payload(
                        meals=[
                            template_meal(
                                name="Czwartkowy", items=[template_recipe_item(recipe.id)]
                            )
                        ]
                    ),
                },
            ],
        },
    )

    result = await TemplatesService(db_session).instantiate_week_template(
        template.id, user=user, week_start=NEXT_MONDAY
    )

    assert [view.day for view in result.days] == [NEXT_MONDAY, NEXT_MONDAY + _days(3)]
    assert [view.meals[0].meal.name for view in result.days] == ["Poniedziałkowy", "Czwartkowy"]


async def test_instancjacja_tygodnia_na_zajete_daty_dopisuje_posilki(
    db_session: AsyncSession,
) -> None:
    """Zachowanie z B06: kopia DOPISUJE się, nie nadpisuje istniejącej pracy."""
    user = await create_user(db_session)
    await _day_with_meal(db_session, user, NEXT_MONDAY)
    template = await create_week_template(
        db_session,
        owner=user,
        payload={
            "v": 1,
            "days": [{"offset": 0, "day": day_payload(meals=[template_meal(name="Z szablonu")])}],
        },
    )

    result = await TemplatesService(db_session).instantiate_week_template(
        template.id, user=user, week_start=NEXT_MONDAY
    )

    assert [meal.meal.name for meal in result.days[0].meals] == ["Obiad", "Z szablonu"]


async def test_instancjacja_tygodnia_wymaga_poniedzialku(db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    template = await create_week_template(db_session, owner=user)

    with pytest.raises(PlanValidationError, match="poniedziałek"):
        await TemplatesService(db_session).instantiate_week_template(
            template.id, user=user, week_start=TUESDAY
        )


async def test_instancjacja_z_martwym_przepisem_konczy_sie_422_i_nie_zapisuje_nic(
    db_session: AsyncSession,
) -> None:
    """Payload wskazujący nieistniejący przepis nie ma prawa dosypać połowy dnia."""
    user = await create_user(db_session)
    template = await create_day_template(
        db_session,
        owner=user,
        payload=day_payload(meals=[template_meal(items=[template_recipe_item(999_999)])]),
    )

    with pytest.raises(PlanValidationError, match="przepisy"):
        await TemplatesService(db_session).instantiate_day_template(
            template.id, user=user, dates=[MONDAY]
        )

    assert await _count(db_session, PlanDay) == 0
    assert await _count(db_session, PlanMeal) == 0


async def test_instancjacja_z_archiwalnym_przepisem_przechodzi_z_ostrzezeniem(
    db_session: AsyncSession,
) -> None:
    """Archiwum to nie usunięcie: dzień powstaje, ale użytkownik dostaje ostrzeżenie."""
    user = await create_user(db_session)
    recipe = await create_recipe(db_session, owner=user, name="Stare danie")
    recipe.is_archived = True
    await db_session.commit()

    template = await create_day_template(
        db_session,
        owner=user,
        payload=day_payload(meals=[template_meal(items=[template_recipe_item(recipe.id)])]),
    )

    result = await TemplatesService(db_session).instantiate_day_template(
        template.id, user=user, dates=[MONDAY]
    )

    assert len(result.days[0].meals) == 1
    assert any("zarchiwizowany" in warning for warning in result.warnings)


# --- cykle ---------------------------------------------------------------------------


async def test_apply_cyklu_rotuje_szablony_po_tygodniach(db_session: AsyncSession) -> None:
    """Dwa szablony na trzy tygodnie ⇒ A, B, A — każdy w swoim tygodniu."""
    user = await create_user(db_session)
    templates = TemplatesService(db_session)
    first = await create_week_template(
        db_session,
        owner=user,
        name="A",
        payload={
            "v": 1,
            "days": [{"offset": 0, "day": day_payload(meals=[template_meal(name="A")])}],
        },
    )
    second = await create_week_template(
        db_session,
        owner=user,
        name="B",
        payload={
            "v": 1,
            "days": [{"offset": 0, "day": day_payload(meals=[template_meal(name="B")])}],
        },
    )
    cycle = await create_week_cycle(
        db_session, owner=user, template_ids=[first.id, second.id], start_date=MONDAY
    )

    result = await templates.apply_cycle(
        cycle.id,
        user=user,
        payload=CycleApplyRequest(date_from=MONDAY, date_to=MONDAY + _days(20)),
    )

    assert [view.day for view in result.days] == [MONDAY, NEXT_MONDAY, MONDAY + _days(14)]
    assert [view.meals[0].meal.name for view in result.days] == ["A", "B", "A"]


async def test_apply_cyklu_obcina_niepelny_tydzien_na_koncu_zakresu(
    db_session: AsyncSession,
) -> None:
    """Zakres do wtorku nie ma prawa dosypać środy — „tylko dni w zakresie"."""
    user = await create_user(db_session)
    template = await create_week_template(
        db_session,
        owner=user,
        payload={
            "v": 1,
            "days": [
                {"offset": offset, "day": day_payload(meals=[template_meal(name=f"D{offset}")])}
                for offset in range(4)
            ],
        },
    )
    cycle = await create_week_cycle(db_session, owner=user, template_ids=[template.id])

    result = await TemplatesService(db_session).apply_cycle(
        cycle.id, user=user, payload=CycleApplyRequest(date_from=MONDAY, date_to=TUESDAY)
    )

    assert [view.day for view in result.days] == [MONDAY, TUESDAY]


async def test_apply_cyklu_wymaga_poniedzialku(db_session: AsyncSession) -> None:
    """„Zastosuj od środy" nie ma jednoznacznego znaczenia — 422, nie domysł."""
    user = await create_user(db_session)
    template = await create_week_template(db_session, owner=user)
    cycle = await create_week_cycle(db_session, owner=user, template_ids=[template.id])

    with pytest.raises(PlanValidationError, match="poniedziałek"):
        await TemplatesService(db_session).apply_cycle(
            cycle.id,
            user=user,
            payload=CycleApplyRequest(date_from=TUESDAY, date_to=TUESDAY + _days(7)),
        )


async def test_usuniecie_szablonu_uzytego_w_cyklu_daje_409_z_nazwa_cyklu(
    db_session: AsyncSession,
) -> None:
    """`template_ids` to tablica bez FK (03_DB §6) — spójności pilnuje serwis."""
    user = await create_user(db_session)
    template = await create_week_template(db_session, owner=user, name="Tydzień A")
    cycle = await create_week_cycle(
        db_session, owner=user, name="Cykl rotacyjny", template_ids=[template.id]
    )

    with pytest.raises(ConflictError) as error:
        await TemplatesService(db_session).delete_week_template(template.id, user=user)

    assert error.value.details["used_in"] == [
        {"type": "week_cycle", "id": cycle.id, "name": "Cykl rotacyjny"}
    ]


async def test_cykl_nie_przyjmie_cudzego_szablonu(db_session: AsyncSession) -> None:
    """Anty-IDOR: cykl może wskazywać tylko szablony widoczne dla właściciela."""
    owner = await create_user(db_session, email="wlasciciel@example.com")
    stranger = await create_user(db_session, email="obcy@example.com")
    foreign = await create_week_template(db_session, owner=stranger, name="Cudzy")

    with pytest.raises(PlanValidationError, match="szablony"):
        await TemplatesService(db_session).create_cycle(
            user=owner,
            payload=CycleWriteRequest(name="Podejrzany", template_ids=[foreign.id]),
        )


async def test_apply_cyklu_ignoruje_szablony_poza_zakresem(db_session: AsyncSession) -> None:
    """Martwa referencja w szablonie, który NIE wypada w zakresie, nie blokuje apply.

    Cykl [A, B] zastosowany na JEDEN tydzień używa wyłącznie A. Walidacja
    referencji obejmująca cały cykl wysadzałaby operację przez zepsute B,
    którego użytkownik w tym zakresie w ogóle nie dotyka (ustalenie /code-review).
    """
    user = await create_user(db_session)
    good = await create_week_template(
        db_session,
        owner=user,
        name="A dobry",
        payload={"v": 1, "days": [{"offset": 0, "day": day_payload(meals=[template_meal()])}]},
    )
    broken = await create_week_template(
        db_session,
        owner=user,
        name="B zepsuty",
        payload={
            "v": 1,
            "days": [
                {
                    "offset": 0,
                    "day": day_payload(
                        meals=[template_meal(items=[template_recipe_item(999_999)])]
                    ),
                }
            ],
        },
    )
    cycle = await create_week_cycle(db_session, owner=user, template_ids=[good.id, broken.id])

    result = await TemplatesService(db_session).apply_cycle(
        cycle.id,
        user=user,
        payload=CycleApplyRequest(date_from=MONDAY, date_to=MONDAY + _days(6)),
    )

    assert [view.day for view in result.days] == [MONDAY]
    assert result.warnings == []


async def test_apply_cyklu_jest_jedna_transakcja(db_session: AsyncSession) -> None:
    """Cykl ze złym szablonem nie zostawia połowy tygodni w bazie."""
    user = await create_user(db_session)
    good = await create_week_template(
        db_session,
        owner=user,
        name="Dobry",
        payload={"v": 1, "days": [{"offset": 0, "day": day_payload(meals=[template_meal()])}]},
    )
    broken = await create_week_template(
        db_session,
        owner=user,
        name="Zepsuty",
        payload={
            "v": 1,
            "days": [
                {
                    "offset": 0,
                    "day": day_payload(
                        meals=[template_meal(items=[template_recipe_item(999_999)])]
                    ),
                }
            ],
        },
    )
    cycle = await create_week_cycle(db_session, owner=user, template_ids=[good.id, broken.id])

    with pytest.raises(PlanValidationError):
        await TemplatesService(db_session).apply_cycle(
            cycle.id,
            user=user,
            payload=CycleApplyRequest(date_from=MONDAY, date_to=MONDAY + _days(13)),
        )

    assert await _count(db_session, PlanDay) == 0
    assert await _count(db_session, PlanMealItem) == 0


# --- scope referencji w payloadzie (ustalenie /security-review) ---------------------


async def test_payload_nie_przyjmie_cudzego_prywatnego_przepisu(
    db_session: AsyncSession,
) -> None:
    """Payload NIE jest obejściem scope — cudzy prywatny przepis kończy się 422.

    Bez tej walidacji payload byłby dziurą w `ScopedQuery`: `add_item` sprawdza
    widoczność przepisu (`_assert_recipe_available`), a `portion_values` świadomie
    NIE filtruje scope. Wpisanie obcego `recipe_id` do szablonu i instancjacja
    dałyby więc nazwę i wartości odżywcze cudzego prywatnego przepisu
    w `GET /plan/days`.
    """
    attacker = await create_user(db_session, email="obcy@example.com")
    victim = await create_user(db_session, email="ofiara@example.com")
    secret = await create_recipe(db_session, owner=victim, name="Tajny przepis babci")

    templates = TemplatesService(db_session)
    with pytest.raises(PlanValidationError) as error:
        await templates.create_day_template(
            user=attacker,
            payload=DayTemplateWriteRequest(
                name="Podejrzany",
                payload=DayTemplatePayload.model_validate(
                    day_payload(meals=[template_meal(items=[template_recipe_item(secret.id)])])
                ),
            ),
        )

    # Ten sam komunikat, co dla nieistniejącego id — endpoint nie jest oracle'em.
    assert "nie są dla Ciebie widoczne" in error.value.message
    assert await _count(db_session, DayTemplate) == 0
    assert await _count(db_session, PlanMealItem) == 0


async def test_instancjacja_odrzuca_przepis_ktory_przestal_byc_widoczny(
    db_session: AsyncSession,
) -> None:
    """Widoczność sprawdzana jest TAKŻE przy instancjacji, nie tylko przy zapisie.

    Szablon rodzinny mógł powstać, gdy przepis był `household`; po zmianie na
    `private` przez właściciela instancjacja przez innego członka rodziny nie ma
    prawa przepisać go do planu.
    """
    household = await create_household(db_session)
    owner = await create_user(db_session, email="wlasciciel@example.com", household=household)
    member = await create_user(db_session, email="czlonek@example.com", household=household)
    recipe = await create_recipe(
        db_session, owner=owner, name="Rodzinny obiad", scope=Scope.HOUSEHOLD
    )
    template = await create_day_template(
        db_session,
        owner=owner,
        scope=Scope.HOUSEHOLD,
        payload=day_payload(meals=[template_meal(items=[template_recipe_item(recipe.id)])]),
    )

    # Właściciel przepisu chowa go przed rodziną.
    recipe.scope = Scope.PRIVATE
    await db_session.commit()

    with pytest.raises(PlanValidationError):
        await TemplatesService(db_session).instantiate_day_template(
            template.id, user=member, dates=[MONDAY]
        )

    assert await _count(db_session, PlanMealItem) == 0


async def test_wlasny_i_rodzinny_przepis_w_payloadzie_przechodzi(
    db_session: AsyncSession,
) -> None:
    """Walidacja nie może być nadmiarowa: własny i rodzinny przepis są legalne."""
    household = await create_household(db_session)
    owner = await create_user(db_session, email="wlasciciel@example.com", household=household)
    member = await create_user(db_session, email="czlonek@example.com", household=household)
    own = await create_recipe(db_session, owner=member, name="Mój przepis")
    shared = await create_recipe(
        db_session, owner=owner, name="Wspólny przepis", scope=Scope.HOUSEHOLD
    )

    template = await TemplatesService(db_session).create_day_template(
        user=member,
        payload=DayTemplateWriteRequest(
            name="Legalny",
            payload=DayTemplatePayload.model_validate(
                day_payload(
                    meals=[
                        template_meal(
                            items=[
                                template_recipe_item(own.id, position=0),
                                template_recipe_item(shared.id, position=1),
                            ]
                        )
                    ]
                )
            ),
        ),
    )

    result = await TemplatesService(db_session).instantiate_day_template(
        template.id, user=member, dates=[MONDAY]
    )

    assert len(result.days[0].meals[0].items) == 2


# --- rozkład rodzinny w szablonie ----------------------------------------------------


async def test_rozklad_rodzinny_przechodzi_przez_szablon(db_session: AsyncSession) -> None:
    """Szablon zapisany z rozkładem odtwarza go przy instancjacji w tej samej rodzinie."""
    household = await create_household(db_session)
    user = await create_user(db_session, household=household)
    profile = await create_member_profile(db_session, household=household, name="Ania")
    recipe = await create_recipe(db_session, owner=user, name="Obiad rodzinny")

    template = await create_day_template(
        db_session,
        owner=user,
        payload=day_payload(
            meals=[
                template_meal(
                    items=[
                        {
                            "recipe_id": recipe.id,
                            "servings": "1.5",
                            "position": 0,
                            "servings_split": [
                                {"member_profile_id": profile.id, "multiplier": "1.5"}
                            ],
                        }
                    ]
                )
            ]
        ),
    )

    result = await TemplatesService(db_session).instantiate_day_template(
        template.id, user=user, dates=[MONDAY]
    )

    split = result.days[0].meals[0].items[0].split
    assert [(row.member_profile_id, row.multiplier) for row in split] == [
        (profile.id, Decimal("1.50"))
    ]
