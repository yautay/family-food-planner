"""Logika modułu recipes: CRUD przepisów, normalizacja składników, tagi, oceny.

Granice odpowiedzialności (ADR-008, karta B05):

- **Widoczność** — wyłącznie `ScopedQuery` (`_RECIPES`); cudzy przepis to 404,
  edycję treści HOUSEHOLD ma każdy członek rodziny, `assert_can_manage`
  obowiązuje TYLKO zmianę scope i usunięcie.
- **Ilości** — każda pozycja składnika przechodzi przez `catalog/units.py`
  przy zapisie; nieprzeliczalna ilość wysadza CAŁY zapis (422) i nic nie
  trafia do bazy (niezmiennik 02_DOMAIN §13.1).
- **Wartości odżywcze** — liczy silnik `nutrition/engine.py` z danych podanych
  przez adapter `ProductNutrition` (ADR-004); serwis robi I/O i buduje wejścia,
  silnik nie widzi ORM. Wyniki NIGDY nie są zapisywane (02_DOMAIN §13.2).
- **Blokady usuwania** — moduł rejestruje w katalogu licznik referencji
  produktów (409 z nazwami przepisów) i wystawia własny rejestr referencji
  przepisów dla przyszłych konsumentów (plan B06, szablony B07).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import ColumnElement, delete, exists, func, insert, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.deletion import (
    USED_IN_LIMIT,
    UsedInRef,
    assert_deletable,
    conflict_from_integrity_error,
)
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.scope import NO_HOUSEHOLD_MESSAGE, Scope, ScopedQuery
from app.core.uploads import delete_image, save_image
from app.modules.accounts.models import User
from app.modules.catalog.models import CanonicalProduct, ProductUnitWeight
from app.modules.catalog.nutrition_adapter import measure_for, nutrition_for
from app.modules.catalog.service import register_product_reference_finder
from app.modules.catalog.units import (
    AmountUnit,
    NormalizedAmount,
    ProductMeasure,
    UnitConversionError,
    UnitWeight,
    normalize_amount,
    to_basis_amount,
)
from app.modules.households.service import register_household_reference_finder
from app.modules.nutrition.engine import (
    ingredient_nutrition,
    portion_nutrition,
    recipe_nutrition,
    round_for_output,
    scale,
)
from app.modules.nutrition.types import ZERO_VALUES, NutritionValues
from app.modules.recipes.models import (
    Recipe,
    RecipeIngredient,
    RecipeRating,
    RecipeSource,
    Tag,
    recipe_tags,
)
from app.modules.recipes.schemas import RecipeIngredientInput, RecipePayload

RECIPE_NOT_FOUND = "Nie znaleziono przepisu."
RECIPE_IN_USE = (
    "Przepis jest używany i nie może zostać usunięty. Usuń go najpierw z planów "
    "i szablonów, w których występuje."
)
TAG_NOT_FOUND = "Wybrany tag nie istnieje. Odśwież listę tagów i spróbuj ponownie."
INGREDIENT_PRODUCT_NOT_FOUND = (
    "Składnik wskazuje produkt, którego nie ma w katalogu. Odśwież formularz i wybierz produkt "
    "ponownie."
)
NO_PHOTO_MESSAGE = "Ten przepis nie ma zdjęcia."
MEASURE_KIND_MISMATCH = (
    "ilość składnika zapisano w jednostce niezgodnej z obecnym sposobem liczenia produktu — "
    "popraw składnik w przepisie"
)

#: Podkatalog uploadów dla zdjęć przepisów (B09 doda własny dla retail).
PHOTO_SUBDIR = "recipes"
#: Kwant ilości składnika po przeskalowaniu — skala kolumny NUMERIC(10,3).
_AMOUNT_QUANTUM = Decimal("0.001")
#: Kwant średniej oceny w odpowiedziach (gwiazdki z jednym miejscem po przecinku).
_RATING_QUANTUM = Decimal("0.1")

_RECIPES = ScopedQuery(Recipe, not_found_message=RECIPE_NOT_FOUND)


class RecipeValidationError(AppError):
    """422 — dane przepisu są niespójne (np. składnik ze wskazaniem na nieistniejący produkt)."""

    status_code = 422
    code = "validation_error"


#: Funkcja licząca referencje do przepisu w innym module (plan B06, szablony B07).
RecipeReferenceFinder = Callable[[AsyncSession, int], Awaitable[Sequence[UsedInRef]]]

_RECIPE_REFERENCE_FINDERS: list[RecipeReferenceFinder] = []


def register_recipe_reference_finder(finder: RecipeReferenceFinder) -> None:
    """Zarejestruj licznik referencji do przepisu (wołane przy imporcie modułu).

    W BATCH_05 rejestr jest pusty — mechanizm powstaje teraz, bo blokada
    usuwania obowiązuje każdego przyszłego konsumenta (ADR-012, karta B05).
    """
    if finder not in _RECIPE_REFERENCE_FINDERS:
        _RECIPE_REFERENCE_FINDERS.append(finder)


def unregister_recipe_reference_finder(finder: RecipeReferenceFinder) -> None:
    """Wyrejestruj licznik — testy sprzątają po sobie."""
    if finder in _RECIPE_REFERENCE_FINDERS:
        _RECIPE_REFERENCE_FINDERS.remove(finder)


@dataclass(frozen=True)
class IngredientView:
    """Składnik z produktem i ilością przeskalowaną do żądanej liczby porcji."""

    ingredient: RecipeIngredient
    product: CanonicalProduct
    scaled_amount: Decimal


@dataclass(frozen=True)
class RecipeView:
    """Przepis z danymi zmaterializowanymi dla listy (widok 2)."""

    recipe: Recipe
    tags: list[Tag]
    avg_rating: Decimal | None
    ratings_count: int
    my_rating: int | None
    #: Wartości JEDNEJ porcji bazowej, zaokrąglone na wyjściu (02_DOMAIN §6).
    nutrition: NutritionValues


@dataclass(frozen=True)
class RecipeDetailView:
    """Widok szczegółu (widok 3): lista + instrukcja, składniki i mnożnik porcji."""

    base: RecipeView
    servings: Decimal
    #: Wartości porcja x mnożnik, zaokrąglone na wyjściu.
    nutrition: NutritionValues
    ingredients: list[IngredientView]


@dataclass(frozen=True)
class RecipePortion:
    """Przepis w postaci, której potrzebują konsumenci: plan dnia (B06), szablony (B07).

    `portion` to wartości JEDNEJ porcji bazowej BEZ zaokrągleń — konsument mnoży
    je przez swój mnożnik i dopiero wynik przepuszcza przez `round_for_output`
    (zaokrąglenie w kroku pośrednim rozjechałoby sumę dnia).
    """

    recipe_id: int
    name: str
    base_servings: int
    photo_path: str | None
    portion: NutritionValues


@dataclass(frozen=True)
class ImportedIngredient:
    """Składnik wnoszony przez zatwierdzenie importu PDF (BATCH_16).

    `grams` to gramatura z dokumentu — po ewentualnym przemnożeniu przez liczbę
    porcji dla wierszy z sekcji `Produkty` (te są podane na porcję, a przepis
    na całość). Para `display_*` jest tym, co widział człowiek („2 x Sztuka");
    bywa pusta, bo dwa z trzech wariantów wiersza §3.2 jej nie niosą.
    """

    product_id: int
    grams: Decimal
    display_qty: Decimal | None = None
    display_unit: str | None = None


@dataclass(frozen=True)
class RecipeIngredientAmount:
    """Ilość jednego składnika przepisu — bez wartości odżywczych (karta B10)."""

    product_id: int
    amount: Decimal
    amount_unit: AmountUnit


@dataclass(frozen=True)
class RecipeAmounts:
    """Przepis w postaci „co i ile kupić" — wejście silnika zakupowego (B10).

    Osobno od `RecipePortion`, bo to inne pytanie: tam chodzi o wartości JEDNEJ
    porcji, tu o ILOŚCI składników całego przepisu. Silnik zakupowy dzieli je
    przez `base_servings` i mnoży przez mnożnik pozycji planu.
    """

    recipe_id: int
    name: str
    base_servings: int
    ingredients: tuple[RecipeIngredientAmount, ...]


@dataclass(frozen=True)
class RatingView:
    """Wynik upsertu oceny — odpowiedź zawiera średnią (karta B05)."""

    my_rating: int
    avg_rating: Decimal
    ratings_count: int


@dataclass(frozen=True)
class _ComputedRecipe:
    """Wewnętrzny wynik `_views`: gotowy widok + surowe nutrition i pary do szczegółu."""

    view: RecipeView
    #: Wartości porcji PRZED zaokrągleniem — do skalowania mnożnikiem w szczególe.
    portion_raw: NutritionValues
    pairs: list[tuple[RecipeIngredient, CanonicalProduct]]


class RecipesService:
    """Operacje na przepisach, tagach i ocenach. Jedyne miejsce I/O tego modułu."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        settings = get_settings()
        self._uploads_root = Path(settings.uploads_dir)
        self._image_max_bytes = settings.image_max_upload_mb * 1024 * 1024

    @property
    def image_max_bytes(self) -> int:
        """Limit zdjęcia w bajtach — router czyta multipart z sufitem `limit + 1`."""
        return self._image_max_bytes

    # --- odczyt -----------------------------------------------------------------

    async def list_recipes(
        self,
        user: User,
        *,
        limit: int,
        offset: int,
        query: str | None = None,
        tag_ids: Sequence[int] = (),
        prep_time_max: int | None = None,
        difficulty_max: int | None = None,
        rating_min: int | None = None,
        scope: Scope | None = None,
        include_archived: bool = False,
    ) -> tuple[list[RecipeView], int]:
        """Lista widocznych przepisów z filtrami widoku 2 (karta B05).

        Filtr tagów jest koniunkcją: zaznaczenie „obiad" i „ulubione" zawęża
        do przepisów mających OBA tagi — tak działa doklikiwanie chipsów.
        """
        statement = _RECIPES.select_visible(user)
        if not include_archived:
            statement = statement.where(Recipe.is_archived.is_(False))
        if scope is not None:
            statement = statement.where(Recipe.scope == scope)
        if prep_time_max is not None:
            statement = statement.where(Recipe.prep_time_min <= prep_time_max)
        if difficulty_max is not None:
            statement = statement.where(Recipe.difficulty <= difficulty_max)
        for tag_id in tag_ids:
            statement = statement.where(
                exists(
                    select(recipe_tags.c.recipe_id).where(
                        recipe_tags.c.recipe_id == Recipe.id,
                        recipe_tags.c.tag_id == tag_id,
                    )
                )
            )
        if rating_min is not None:
            average = (
                select(func.avg(RecipeRating.rating))
                .where(RecipeRating.recipe_id == Recipe.id)
                .correlate(Recipe)
                .scalar_subquery()
            )
            statement = statement.where(average >= rating_min)

        phrase = (query or "").strip()
        ordering: tuple[Any, ...]
        if phrase:
            statement = statement.where(_search_condition(phrase))
            ordering = (_similarity(phrase).desc(), Recipe.name, Recipe.id)
        else:
            ordering = (Recipe.name, Recipe.id)

        total = (
            await self._session.execute(select(func.count()).select_from(statement.subquery()))
        ).scalar_one()
        rows = (
            (
                await self._session.execute(
                    statement.order_by(*ordering)
                    .limit(limit)
                    .offset(offset)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        computed = await self._views(list(rows), user)
        return [item.view for item in computed], total

    async def recipe_detail(
        self, user: User, recipe_id: int, *, servings: Decimal = Decimal("1")
    ) -> RecipeDetailView:
        """Szczegóły z nutrition = porcja x mnożnik i przeskalowanymi składnikami.

        Skalowanie liczy backend (05_FRONTEND §7): `scaled_amount` = ilość
        znormalizowana x servings / base_servings, kwantowana do skali kolumny.
        """
        recipe = await _RECIPES.get_or_404(self._session, recipe_id, user)
        computed = (await self._views([recipe], user))[0]

        factor = servings / Decimal(recipe.base_servings)
        ingredients = [
            IngredientView(
                ingredient=ingredient,
                product=product,
                scaled_amount=(ingredient.amount * factor).quantize(
                    _AMOUNT_QUANTUM, rounding=ROUND_HALF_UP
                ),
            )
            for ingredient, product in computed.pairs
        ]
        return RecipeDetailView(
            base=computed.view,
            servings=servings,
            nutrition=round_for_output(scale(computed.portion_raw, servings)),
            ingredients=ingredients,
        )

    # --- zapis ------------------------------------------------------------------

    async def owned_names(self, *, actor: User, limit: int) -> list[tuple[int, str]]:
        """Pary `(id, nazwa)` WŁASNYCH, nieARCHIWALNYCH przepisów — lekki odczyt.

        Wejście dla wykrywania duplikatów w review importu (BATCH_16): tam
        potrzebne są SAME nazwy, a `list_recipes` liczyłoby dla każdego wiersza
        wartości odżywcze i oceny.

        **`owned_condition`, nie `visible_condition`** — świadomie, bo te nazwy
        wychodzą POZA instancję, do Claude API. Widoczność daje ADMIN-owi
        `true()` (D16), więc administrator klikający „Zaproponuj z AI" wysłałby
        nazwy przepisów WSZYSTKICH rodzin, a decyzja D5 zezwala wyłącznie na
        treść PDF-a i katalog. To ta sama granica, co przy eksporcie własnych
        danych (BATCH_14) — przynależność, nie widoczność.
        """
        rows = (
            await self._session.execute(
                select(Recipe)
                .where(_RECIPES.owned_condition(actor), Recipe.is_archived.is_(False))
                .order_by(Recipe.name, Recipe.id)
                .limit(limit)
            )
        ).scalars()
        return [(recipe.id, recipe.name) for recipe in rows]

    async def get_visible(self, recipe_id: int, *, actor: User) -> Recipe:
        """Przepis widoczny dla użytkownika albo 404 — wejście dla innych modułów.

        Publiczne, bo scalanie dania importu z istniejącym przepisem (BATCH_16)
        musi sprawdzić `target_recipe_id` TĄ SAMĄ regułą widoczności, co reszta
        modułu; własny filtr w cudzym serwisie byłby błędem review.
        """
        return await _RECIPES.get_or_404(self._session, recipe_id, actor)

    async def create_recipe(self, *, actor: User, payload: RecipePayload) -> RecipeDetailView:
        """Nowy przepis ze składnikami i tagami — jedna transakcja.

        Nieprzeliczalna ilość któregokolwiek składnika wysadza całość PRZED
        commitem: w bazie nie powstaje ani przepis, ani żaden składnik
        (02_DOMAIN §13.1).
        """
        recipe = Recipe(
            name=payload.name,
            instructions=payload.instructions,
            base_servings=payload.base_servings,
            prep_time_min=payload.prep_time_min,
            difficulty=payload.difficulty,
            **ScopedQuery.ownership_for_create(actor, payload.scope),
        )
        self._session.add(recipe)
        await self._session.flush()

        self._session.add_all(await self._build_ingredients(recipe.id, payload.ingredients))
        await self._replace_tags(recipe.id, payload.tag_ids)
        await self._session.commit()
        return await self.recipe_detail(actor, recipe.id)

    async def create_imported_recipe(
        self,
        *,
        actor: User,
        scope: Scope,
        import_job_id: int,
        name: str,
        instructions: str,
        base_servings: int,
        ingredients: Sequence[ImportedIngredient],
    ) -> Recipe:
        """Przepis z zatwierdzonego importu PDF — BEZ commita (BATCH_16).

        Osobne wejście, a nie `create_recipe`, z trzech powodów:

        1. **Bez commita.** Zatwierdzenie joba tworzy kilkanaście przepisów,
           produkty i próbki przeliczników w JEDNEJ transakcji (ADR-011:
           „do danych aplikacji trafia wyłącznie stan APPROVED" — połowa
           importu byłaby gorsza niż jego brak).
        2. **Ilość wchodzi w GRAMACH z dokumentu**, bo gramatura z nawiasu jest
           jedynym źródłem ilości przy imporcie (01_PDF_AUDIT §8.3) — a para
           ilość x jednostka („2 x Sztuka") zostaje wyłącznie jako
           `display_qty`/`display_unit`, czyli to, co widział człowiek.
        3. `source`/`import_job_id` ustawia się tylko tutaj; ręczny endpoint
           przepisów nie ma prawa ich podać.
        """
        recipe = Recipe(
            name=name,
            instructions=instructions,
            base_servings=base_servings,
            source=RecipeSource.PDF_IMPORT,
            import_job_id=import_job_id,
            **ScopedQuery.ownership_for_create(actor, scope),
        )
        self._session.add(recipe)
        await self._session.flush()

        products, measures = await self._measures_for({item.product_id for item in ingredients})
        for position, item in enumerate(ingredients):
            product = products[item.product_id]
            try:
                normalized = normalize_amount(item.grams, "g", measures[item.product_id])
            except UnitConversionError as exc:
                # Produkt liczony na 100 ml nie przyjmuje gramatury z PDF-a bez
                # gęstości, której model nie ma (ADR-005). Zapis pada CAŁY —
                # niezmiennik 02_DOMAIN §13.1 nie zna wyjątku „prawie się dało".
                raise UnitConversionError(
                    f"Składnik „{product.name}”: {exc.message}",
                    details={"product_id": product.id, "unit": "g", **exc.details},
                ) from exc
            self._session.add(
                RecipeIngredient(
                    recipe_id=recipe.id,
                    product_id=product.id,
                    display_qty=item.display_qty,
                    display_unit=item.display_unit,
                    amount=normalized.amount,
                    amount_unit=normalized.unit,
                    position=position,
                )
            )
        await self._session.flush()
        return recipe

    async def update_recipe(
        self, recipe_id: int, *, actor: User, payload: RecipePayload
    ) -> RecipeDetailView:
        """PUT — pełna podmiana. Składniki wymieniane KOMPLETEM (nowe wiersze,
        stare `id` pozycji nie są zachowywane — rozstrzygnięcie z karty B05).

        Edycja treści HOUSEHOLD nie wymaga `assert_can_manage` (rodzina sobie
        ufa); wymaga go WYŁĄCZNIE zmiana scope.
        """
        recipe = await _RECIPES.get_or_404(self._session, recipe_id, actor)

        if payload.scope is not recipe.scope:
            _RECIPES.assert_can_manage(recipe, actor)
            if payload.scope is Scope.HOUSEHOLD and recipe.household_id is None:
                # Wiersz mógł powstać, zanim właściciel dostał rodzinę —
                # uzupełniamy household WŁAŚCICIELA, nie edytującego.
                owner = await self._session.get(User, recipe.owner_user_id)
                if owner is None or owner.household_id is None:
                    raise ConflictError(NO_HOUSEHOLD_MESSAGE)
                recipe.household_id = owner.household_id
            recipe.scope = payload.scope

        recipe.name = payload.name
        recipe.instructions = payload.instructions
        recipe.base_servings = payload.base_servings
        recipe.prep_time_min = payload.prep_time_min
        recipe.difficulty = payload.difficulty

        await self._session.execute(
            delete(RecipeIngredient).where(RecipeIngredient.recipe_id == recipe.id)
        )
        self._session.add_all(await self._build_ingredients(recipe.id, payload.ingredients))
        await self._replace_tags(recipe.id, payload.tag_ids)
        await self._session.commit()
        return await self.recipe_detail(actor, recipe.id)

    async def delete_recipe(self, recipe_id: int, *, actor: User) -> None:
        """Usunięcie: właściciel/ADMIN; przepis w użyciu → 409 z `used_in` (ADR-012)."""
        recipe = await _RECIPES.get_or_404(self._session, recipe_id, actor)
        _RECIPES.assert_can_manage(recipe, actor)
        assert_deletable(RECIPE_IN_USE, await self.recipe_references(recipe_id))

        photo_path = recipe.photo_path
        await self._session.execute(delete(Recipe).where(Recipe.id == recipe_id))
        try:
            await self._session.commit()
        except IntegrityError as exc:
            # Druga linia obrony: FK RESTRICT konsumenta, który nie zarejestrował
            # licznika referencji (inaczej byłoby 500 zamiast 409).
            await self._session.rollback()
            raise conflict_from_integrity_error(RECIPE_IN_USE) from exc

        if photo_path:
            await run_in_threadpool(delete_image, photo_path, uploads_root=self._uploads_root)

    async def ingredient_amounts(self, recipe_ids: Sequence[int]) -> dict[int, RecipeAmounts]:
        """Ilości składników wskazanych przepisów — wejście silnika zakupowego (B10).

        Publiczne wejście modułu recipes obok `portion_values` (CLAUDE.md §4:
        moduł→moduł wyłącznie przez service). Stała liczba zapytań niezależnie
        od liczby przepisów — tydzień planu nie może generować N+1.

        **Bez filtra scope, świadomie** — z tego samego powodu, co
        `portion_values`: pozycja planu może wskazywać przepis, którego czytający
        sam by nie znalazł na liście (prywatny przepis właściciela dnia
        rodzinnego). Dzień jest udostępniony celowo, więc jego zakupy muszą się
        policzyć; widoczność planu pilnuje `ScopedQuery` po stronie planning.
        """
        unique_ids = sorted(set(recipe_ids))
        if not unique_ids:
            return {}

        recipes = (
            (await self._session.execute(select(Recipe).where(Recipe.id.in_(unique_ids))))
            .scalars()
            .all()
        )
        grouped: dict[int, list[RecipeIngredientAmount]] = {rid: [] for rid in unique_ids}
        for ingredient in (
            (
                await self._session.execute(
                    select(RecipeIngredient)
                    .where(RecipeIngredient.recipe_id.in_(unique_ids))
                    .order_by(RecipeIngredient.position, RecipeIngredient.id)
                )
            )
            .scalars()
            .all()
        ):
            grouped[ingredient.recipe_id].append(
                RecipeIngredientAmount(
                    product_id=ingredient.product_id,
                    amount=ingredient.amount,
                    amount_unit=ingredient.amount_unit,
                )
            )
        return {
            recipe.id: RecipeAmounts(
                recipe_id=recipe.id,
                name=recipe.name,
                base_servings=recipe.base_servings,
                ingredients=tuple(grouped[recipe.id]),
            )
            for recipe in recipes
        }

    async def portion_values(self, recipe_ids: Sequence[int]) -> dict[int, RecipePortion]:
        """Wartości jednej porcji bazowej dla wskazanych przepisów — wejście dla planu.

        Publiczne wejście modułu recipes dla innych modułów (CLAUDE.md §4:
        moduł→moduł wyłącznie przez service). Stała liczba zapytań niezależnie
        od liczby przepisów — plan tygodnia nie może generować N+1.

        **Bez filtra scope, świadomie**: pozycja planu może wskazywać przepis,
        którego czytający sam by nie znalazł na liście (np. prywatny przepis
        właściciela dnia rodzinnego). Dzień jest udostępniony celowo, więc jego
        wartości muszą się policzyć; widoczność samego planu pilnuje `ScopedQuery`
        po stronie planning.
        """
        unique_ids = sorted(set(recipe_ids))
        if not unique_ids:
            return {}

        recipes = (
            (await self._session.execute(select(Recipe).where(Recipe.id.in_(unique_ids))))
            .scalars()
            .all()
        )

        ingredients_by: dict[int, list[RecipeIngredient]] = {rid: [] for rid in unique_ids}
        for ingredient in (
            (
                await self._session.execute(
                    select(RecipeIngredient)
                    .where(RecipeIngredient.recipe_id.in_(unique_ids))
                    .order_by(RecipeIngredient.position, RecipeIngredient.id)
                )
            )
            .scalars()
            .all()
        ):
            ingredients_by[ingredient.recipe_id].append(ingredient)

        product_ids = {
            ingredient.product_id for items in ingredients_by.values() for ingredient in items
        }
        products: dict[int, CanonicalProduct] = {}
        if product_ids:
            products = {
                product.id: product
                for product in (
                    await self._session.execute(
                        select(CanonicalProduct).where(CanonicalProduct.id.in_(product_ids))
                    )
                )
                .scalars()
                .all()
            }

        return {
            recipe.id: RecipePortion(
                recipe_id=recipe.id,
                name=recipe.name,
                base_servings=recipe.base_servings,
                photo_path=recipe.photo_path,
                portion=portion_nutrition(
                    recipe_nutrition(
                        [
                            _ingredient_values(ingredient, products[ingredient.product_id])
                            for ingredient in ingredients_by[recipe.id]
                        ]
                    ),
                    recipe.base_servings,
                ),
            )
            for recipe in recipes
        }

    async def recipe_references(self, recipe_id: int) -> list[UsedInRef]:
        """Gdzie przepis jest używany — suma odpowiedzi zarejestrowanych konsumentów."""
        references: list[UsedInRef] = []
        for finder in _RECIPE_REFERENCE_FINDERS:
            references.extend(await finder(self._session, recipe_id))
        return references[:USED_IN_LIMIT]

    # --- oceny --------------------------------------------------------------------

    async def rate_recipe(self, recipe_id: int, *, actor: User, rating: int) -> RatingView:
        """Upsert WŁASNEJ oceny 1-5 (`user_id` z sesji, nigdy z body — karta B05)."""
        await _RECIPES.get_or_404(self._session, recipe_id, actor)

        existing = (
            await self._session.execute(
                select(RecipeRating).where(
                    RecipeRating.recipe_id == recipe_id,
                    RecipeRating.user_id == actor.id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            self._session.add(RecipeRating(recipe_id=recipe_id, user_id=actor.id, rating=rating))
        else:
            existing.rating = rating
        await self._session.commit()

        average, count = (
            await self._session.execute(
                select(func.avg(RecipeRating.rating), func.count()).where(
                    RecipeRating.recipe_id == recipe_id
                )
            )
        ).one()
        return RatingView(
            my_rating=rating,
            avg_rating=Decimal(average).quantize(_RATING_QUANTUM, rounding=ROUND_HALF_UP),
            ratings_count=int(count),
        )

    # --- zdjęcie --------------------------------------------------------------------

    async def set_photo(self, recipe_id: int, *, actor: User, data: bytes) -> RecipeDetailView:
        """Upload zdjęcia (pipeline 07_SECURITY §6). Edycja treści — może każdy członek."""
        recipe = await _RECIPES.get_or_404(self._session, recipe_id, actor)

        # Pillow jest CPU-bound — poza pętlą zdarzeń (ADR-015).
        saved = await run_in_threadpool(
            save_image,
            data,
            uploads_root=self._uploads_root,
            subdir=PHOTO_SUBDIR,
            max_bytes=self._image_max_bytes,
        )
        previous = recipe.photo_path
        recipe.photo_path = saved.path
        await self._session.commit()

        if previous:
            await run_in_threadpool(delete_image, previous, uploads_root=self._uploads_root)
        return await self.recipe_detail(actor, recipe_id)

    async def delete_photo(self, recipe_id: int, *, actor: User) -> RecipeDetailView:
        """Usunięcie zdjęcia; przepis bez zdjęcia → 404 (nie ma czego usuwać)."""
        recipe = await _RECIPES.get_or_404(self._session, recipe_id, actor)
        if not recipe.photo_path:
            raise NotFoundError(NO_PHOTO_MESSAGE)

        previous = recipe.photo_path
        recipe.photo_path = None
        await self._session.commit()
        await run_in_threadpool(delete_image, previous, uploads_root=self._uploads_root)
        return await self.recipe_detail(actor, recipe_id)

    # --- tagi ----------------------------------------------------------------------

    async def list_tags(self) -> list[Tag]:
        """Słownik tagów: systemowe najpierw, potem alfabetycznie — kolejność chipsów."""
        rows = (
            (
                await self._session.execute(
                    select(Tag).order_by(Tag.is_system.desc(), Tag.name, Tag.id)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def create_tag(self, *, actor: User, name: str) -> Tag:
        """Inline create tagu użytkowego (`is_system=false`).

        Duplikat (bez rozróżniania wielkości liter) → 409 z `details.existing`,
        żeby picker mógł zaproponować wybór istniejącego (wzorzec z produktów).
        """
        cleaned = " ".join(name.split())
        existing = (
            await self._session.execute(
                select(Tag).where(func.lower(Tag.name) == cleaned.casefold())
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError(
                f"Tag „{existing.name}” już istnieje.",
                details={"existing": {"id": existing.id, "name": existing.name}},
            )

        tag = Tag(name=cleaned, is_system=False)
        self._session.add(tag)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(f"Tag „{cleaned}” już istnieje.") from exc
        await self._session.refresh(tag)
        return tag

    # --- pomocnicze -------------------------------------------------------------------

    async def _build_ingredients(
        self, recipe_id: int, inputs: Sequence[RecipeIngredientInput]
    ) -> list[RecipeIngredient]:
        """Wejścia użytkownika → wiersze z ilością znormalizowaną (ADR-005).

        Brak jednoznacznego przelicznika ⇒ `UnitConversionError` (422)
        z komunikatem wskazującym produkt i jednostkę; wyjątek przerywa zapis
        przed commitem, więc rollback jest gwarantowany.
        """
        if not inputs:
            return []

        products, measures = await self._measures_for({item.product_id for item in inputs})

        ingredients: list[RecipeIngredient] = []
        for position, item in enumerate(inputs):
            product = products[item.product_id]
            measure = measures[product.id]
            try:
                normalized = normalize_amount(item.quantity, item.unit, measure)
            except UnitConversionError as exc:
                raise UnitConversionError(
                    f"Składnik „{product.name}”: {exc.message}",
                    details={"product_id": product.id, "unit": item.unit, **exc.details},
                ) from exc

            ingredients.append(
                RecipeIngredient(
                    recipe_id=recipe_id,
                    product_id=product.id,
                    display_qty=item.quantity,
                    display_unit=item.unit,
                    amount=normalized.amount,
                    amount_unit=normalized.unit,
                    note=item.note.strip(),
                    position=position,
                )
            )
        return ingredients

    async def _measures_for(
        self, product_ids: set[int]
    ) -> tuple[dict[int, CanonicalProduct], dict[int, ProductMeasure]]:
        """Produkty i ich miary (razem z przelicznikami) — dwa zapytania, bez N+1.

        `measure_for` przyjmuje dataclassy `UnitWeight`, nie wiersze ORM —
        przepakowanie jest obowiązkiem serwisu (ustalenie review R1).
        """
        products = {
            product.id: product
            for product in (
                await self._session.execute(
                    select(CanonicalProduct).where(CanonicalProduct.id.in_(product_ids))
                )
            )
            .scalars()
            .all()
        }
        missing_products = product_ids - products.keys()
        if missing_products:
            raise RecipeValidationError(
                INGREDIENT_PRODUCT_NOT_FOUND,
                details={"product_ids": sorted(missing_products)},
            )

        weights_by: dict[int, list[UnitWeight]] = {pid: [] for pid in product_ids}
        for row in (
            (
                await self._session.execute(
                    select(ProductUnitWeight).where(ProductUnitWeight.product_id.in_(product_ids))
                )
            )
            .scalars()
            .all()
        ):
            weights_by[row.product_id].append(
                UnitWeight(unit_label=row.unit_label, grams_per_unit=row.grams_per_unit)
            )

        measures = {pid: measure_for(product, weights_by[pid]) for pid, product in products.items()}
        return products, measures

    async def _replace_tags(self, recipe_id: int, tag_ids: Sequence[int]) -> None:
        """Podmień przypisania tagów kompletem; nieistniejący id tagu = 422, nie cichy skip.

        DELETE jest bezwarunkowy — na świeżo utworzonym przepisie to no-op,
        a brak rozgałęzienia oznacza brak parametru, którym przyszły caller
        mógłby wjechać w naruszenie PK.
        """
        unique_ids = sorted(set(tag_ids))
        if unique_ids:
            found = set(
                (
                    await self._session.execute(select(Tag.id).where(Tag.id.in_(unique_ids)))
                ).scalars()
            )
            missing = set(unique_ids) - found
            if missing:
                raise RecipeValidationError(TAG_NOT_FOUND, details={"tag_ids": sorted(missing)})

        await self._session.execute(delete(recipe_tags).where(recipe_tags.c.recipe_id == recipe_id))
        if unique_ids:
            await self._session.execute(
                insert(recipe_tags),
                [{"recipe_id": recipe_id, "tag_id": tag_id} for tag_id in unique_ids],
            )

    async def _views(self, recipes: list[Recipe], user: User) -> list[_ComputedRecipe]:
        """Dane zmaterializowane dla wielu przepisów — stała liczba zapytań, bez N+1."""
        if not recipes:
            return []
        recipe_ids = [recipe.id for recipe in recipes]

        ingredients_by: dict[int, list[RecipeIngredient]] = {rid: [] for rid in recipe_ids}
        for ingredient in (
            (
                await self._session.execute(
                    select(RecipeIngredient)
                    .where(RecipeIngredient.recipe_id.in_(recipe_ids))
                    .order_by(RecipeIngredient.position, RecipeIngredient.id)
                )
            )
            .scalars()
            .all()
        ):
            ingredients_by[ingredient.recipe_id].append(ingredient)

        product_ids = {
            ingredient.product_id for items in ingredients_by.values() for ingredient in items
        }
        products: dict[int, CanonicalProduct] = {}
        if product_ids:
            products = {
                product.id: product
                for product in (
                    await self._session.execute(
                        select(CanonicalProduct).where(CanonicalProduct.id.in_(product_ids))
                    )
                )
                .scalars()
                .all()
            }

        tags_by: dict[int, list[Tag]] = {rid: [] for rid in recipe_ids}
        for recipe_id, tag in (
            await self._session.execute(
                select(recipe_tags.c.recipe_id, Tag)
                .join(Tag, Tag.id == recipe_tags.c.tag_id)
                .where(recipe_tags.c.recipe_id.in_(recipe_ids))
                .order_by(Tag.is_system.desc(), Tag.name, Tag.id)
            )
        ).all():
            tags_by[recipe_id].append(tag)

        averages: dict[int, tuple[Decimal, int]] = {}
        for recipe_id, average, count in (
            await self._session.execute(
                select(
                    RecipeRating.recipe_id,
                    func.avg(RecipeRating.rating),
                    func.count(),
                )
                .where(RecipeRating.recipe_id.in_(recipe_ids))
                .group_by(RecipeRating.recipe_id)
            )
        ).all():
            averages[recipe_id] = (
                Decimal(average).quantize(_RATING_QUANTUM, rounding=ROUND_HALF_UP),
                int(count),
            )

        my_ratings: dict[int, int] = dict(
            (
                await self._session.execute(
                    select(RecipeRating.recipe_id, RecipeRating.rating).where(
                        RecipeRating.recipe_id.in_(recipe_ids),
                        RecipeRating.user_id == user.id,
                    )
                )
            ).all()  # type: ignore[arg-type]  # wiersze (recipe_id, rating) to pary int
        )

        computed: list[_ComputedRecipe] = []
        for recipe in recipes:
            pairs = [
                (ingredient, products[ingredient.product_id])
                for ingredient in ingredients_by[recipe.id]
            ]
            total = recipe_nutrition(
                [_ingredient_values(ingredient, product) for ingredient, product in pairs]
            )
            portion_raw = portion_nutrition(total, recipe.base_servings)
            average, count = averages.get(recipe.id, (Decimal("0"), 0))
            computed.append(
                _ComputedRecipe(
                    view=RecipeView(
                        recipe=recipe,
                        tags=tags_by[recipe.id],
                        avg_rating=average if count else None,
                        ratings_count=count,
                        my_rating=my_ratings.get(recipe.id),
                        nutrition=round_for_output(portion_raw),
                    ),
                    portion_raw=portion_raw,
                    pairs=pairs,
                )
            )
        return computed


def _ingredient_values(ingredient: RecipeIngredient, product: CanonicalProduct) -> NutritionValues:
    """Wejście silnika dla jednego składnika — przez adapter, nigdy po kolumnach.

    Gdy `measure_kind` produktu zmieniono PO zapisaniu składnika, stara ilość
    może nie dać się sprowadzić na nową oś „na 100" — wtedy składnik nie wnosi
    wartości, a wynik dostaje `complete=False` z czytelnym komunikatem
    (zamiast 500 na odczycie).
    """
    measure = ProductMeasure(
        measure_kind=product.measure_kind, piece_weight_g=product.piece_weight_g
    )
    try:
        basis_amount = to_basis_amount(
            NormalizedAmount(ingredient.amount, ingredient.amount_unit), measure
        )
    except UnitConversionError:
        # `replace` na elemencie neutralnym: nowe pole liczbowe w kontrakcie
        # NutritionValues (B06+) nie wymaga edycji tego miejsca.
        return replace(
            ZERO_VALUES,
            complete=False,
            missing=(f"{product.name}: {MEASURE_KIND_MISMATCH}",),
        )
    return ingredient_nutrition(basis_amount, nutrition_for(product))


def _similarity(phrase: str) -> ColumnElement[float]:
    """Podobieństwo trigramowe nazwy przepisu do frazy (pg_trgm)."""
    return func.similarity(Recipe.name, phrase)


def _search_condition(phrase: str) -> ColumnElement[bool]:
    """Trafienie: fragment nazwy (bez rozróżniania liter) ALBO podobieństwo trigramowe.

    `autoescape=True` — `%`/`_` z frazy użytkownika nie działają jak
    wieloznaczniki (ta sama lekcja co w katalogu, U14 z review R1).
    """
    threshold = get_settings().catalog_search_similarity_threshold
    return or_(
        Recipe.name.icontains(phrase, autoescape=True),
        func.similarity(Recipe.name, phrase) >= threshold,
    )


async def _recipes_using_product(session: AsyncSession, product_id: int) -> Sequence[UsedInRef]:
    """Licznik referencji dla katalogu: przepisy używające produktu (ADR-012).

    Dzięki temu `DELETE /products/{id}` zwraca 409 z CZYTELNYMI nazwami
    („Gołąbki"), a nie goły konflikt z bazy.
    """
    rows = (
        await session.execute(
            select(Recipe.id, Recipe.name)
            .join(RecipeIngredient, RecipeIngredient.recipe_id == Recipe.id)
            .where(RecipeIngredient.product_id == product_id)
            .distinct()
            .order_by(Recipe.name, Recipe.id)
            .limit(USED_IN_LIMIT)
        )
    ).all()
    return [UsedInRef(type="recipe", id=int(row[0]), name=str(row[1])) for row in rows]


async def _recipes_in_household(session: AsyncSession, household_id: int) -> Sequence[UsedInRef]:
    """Licznik referencji dla modułu households (ustalenie REVIEW R3, dług U16).

    `recipes.household_id` ma `ON DELETE RESTRICT`, więc bez tego licznika ADMIN
    dostawał 409 z pustą listą „Używane w:" i nie wiedział, że rodzinę trzymają
    przepisy.
    """
    rows = (
        await session.execute(
            select(Recipe.id, Recipe.name)
            .where(Recipe.household_id == household_id)
            .order_by(Recipe.name, Recipe.id)
            .limit(USED_IN_LIMIT)
        )
    ).all()
    return [UsedInRef(type="recipe", id=int(row[0]), name=str(row[1])) for row in rows]


# Rejestracja przy imporcie modułu: każdy proces, który buduje aplikację
# (create_app → deps → RecipesService), ma licznik wpięty automatycznie.
register_product_reference_finder(_recipes_using_product)
register_household_reference_finder(_recipes_in_household)
