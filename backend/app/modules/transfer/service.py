"""Serwis transferu: eksport do ZIP-a, raport DRY-RUN i zastosowanie importu.

Jedyne miejsce I/O tego modułu (wzorzec ADR-001): zapytania do bazy, plik
tymczasowy paczki i zapis zdjęć. Czyste reguły formatu mieszkają obok —
`serializer.py` (co wchodzi do pliku) i `importer.py` (bezpieczeństwo archiwum,
raport, remapowanie referencji).

Trzy własności, na których stoi ten moduł:

1. **DRY-RUN nie dotyka bazy.** Analiza liczy się z pliku i z indeksu nazw,
   a raport wraca bez ani jednego `INSERT` — także bez wpisu w dzienniku
   (wpis byłby śladem, którego Acceptance Criterion 3 zabrania).
2. **APPLY to JEDNA transakcja.** Wszystkie sekcje idą jednym `commit()` na
   końcu; wyjątek w środku zostawia bazę nietkniętą, a zdjęcia zapisane po
   drodze są kasowane ręcznie (pliki nie cofną się same).
3. **Eksport buduje się na dysku.** `FileResponse` wysyła plik strumieniem,
   więc paczka ze zdjęciami nigdy nie wchodzi w całości do pamięci.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Table, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.scope import HouseholdScopedQuery, Scope, ScopedQuery
from app.core.security import generate_token, hash_password
from app.core.uploads import DEFAULT_IMAGE_MAX_MB, delete_image, save_image
from app.modules.accounts.models import User, UserRole
from app.modules.audit.service import AuditAction, AuditEntity, AuditService
from app.modules.catalog.models import (
    CanonicalProduct,
    Nutrient,
    ProductCategory,
    ProductNutrientValue,
    ProductUnitWeight,
    RetailProduct,
    Store,
    StoreCategoryOrder,
)
from app.modules.catalog.naming import normalize_name
from app.modules.households.models import Household, MemberProfile
from app.modules.nutrition.models import UserNutritionGoal
from app.modules.pantry.models import PantryItem
from app.modules.planning.models import (
    DayTemplate,
    PlanDay,
    PlanItemServing,
    PlanMeal,
    PlanMealItem,
    WeekCycle,
    WeekTemplate,
)
from app.modules.recipes.models import Recipe, RecipeIngredient, RecipeRating, Tag, recipe_tags
from app.modules.shopping.models import (
    GenerationStatus,
    ShoppingGeneration,
    ShoppingList,
    ShoppingListItem,
    ShoppingRoundConfig,
)
from app.modules.transfer.importer import (
    IMPORT_NOT_FOUND,
    INSTANCE_FILE_FOR_USER,
    DryRunResult,
    ExistingEntity,
    IdMap,
    TransferValidationError,
    analyze,
    assert_within_limit,
    assert_zip_signature,
    decisions_by_key,
    display_name,
    mark_blocked,
    natural_key,
    open_archive,
    parent_blocked,
    photo_names,
    read_document,
    remap_cycle_templates,
    remap_template_payload,
    remap_week_payload,
    resolve_references,
    unique_name,
)
from app.modules.transfer.schemas import (
    PHOTOS_PREFIX,
    CollisionAction,
    CollisionDecision,
    ImportSummary,
    TransferScope,
)
from app.modules.transfer.serializer import (
    Section,
    build_document,
    photo_paths,
    row_to_dict,
    section_columns,
    section_references,
    sections_for,
    write_archive,
)

#: Podkatalog uploadów na paczki transferu (budowane i wgrywane). Poza web-rootem
#: jak reszta uploadów; serwowany WYŁĄCZNIE przez endpoint eksportu.
SCRATCH_SUBDIR = "transfer"
#: Podkatalog zdjęć tworzonych przez import (`core/uploads.save_image`).
IMPORT_PHOTO_SUBDIR = "transfer-import"
#: Po tylu godzinach nieużyta paczka dry-runu jest kasowana (karta B14 §Backend).
SCRATCH_TTL = timedelta(hours=24)

EXPORT_FILENAME = "pasnik-export-{day}.zip"

INSTANCE_REQUIRES_ADMIN = "Eksport całej instancji wymaga uprawnień administratora."
NOTHING_TO_IMPORT = "Plik nie zawiera żadnych danych do zaimportowania."
IMPORT_CONFLICT = (
    "Import kolidowałby z danymi, które już masz (np. plan na tę samą datę "
    "albo cel żywieniowy od tego samego dnia). Nic nie zostało zapisane."
)

_RECIPES = ScopedQuery(Recipe, not_found_message="Nie znaleziono przepisu.")
_PLAN_DAYS = ScopedQuery(PlanDay, not_found_message="Nie znaleziono dnia planu.")
_DAY_TEMPLATES = ScopedQuery(DayTemplate, not_found_message="Nie znaleziono szablonu.")
_WEEK_TEMPLATES = ScopedQuery(WeekTemplate, not_found_message="Nie znaleziono szablonu.")
_CYCLES = ScopedQuery(WeekCycle, not_found_message="Nie znaleziono cyklu.")
_ROUND_CONFIGS = ScopedQuery(ShoppingRoundConfig, not_found_message="Nie znaleziono tury.")
_GENERATIONS = ScopedQuery(ShoppingGeneration, not_found_message="Nie znaleziono generacji.")
_LISTS = ScopedQuery(ShoppingList, not_found_message="Nie znaleziono listy.")
_PANTRY = HouseholdScopedQuery(PantryItem, not_found_message="Nie znaleziono pozycji spiżarni.")


@dataclass(frozen=True)
class ExportResult:
    """Gotowa paczka na dysku — wołający wysyła ją `FileResponse` i sprząta."""

    path: Path
    filename: str
    warnings: list[str]


def section_table(section: Section) -> Table:
    """Tabela SQLAlchemy sekcji (model ORM albo gotowa tabela asocjacyjna)."""
    return section.model if isinstance(section.model, Table) else section.model.__table__


def coerce_value(column: sa.Column[Any], value: Any) -> Any:
    """Wartość z JSON-a → typ kolumny (ADR-008: NUMERIC przez `Decimal`, nie float)."""
    if value is None:
        return None
    kind = column.type
    if isinstance(kind, sa.Enum) and kind.enum_class is not None:
        return kind.enum_class(value)
    if isinstance(kind, sa.Numeric) and not isinstance(kind, sa.Float):
        try:
            return Decimal(str(value))
        except InvalidOperation as exc:
            raise TransferValidationError(
                f"Wartość „{value}” w kolumnie {column.name} nie jest liczbą."
            ) from exc
    if isinstance(kind, sa.DateTime) and isinstance(value, str):
        return datetime.fromisoformat(value)
    if isinstance(kind, sa.Date) and isinstance(value, str):
        return sa.Date().python_type.fromisoformat(value)
    return value


class TransferService:
    """Eksport i import logiczny danych (02_DOMAIN §11)."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        uploads_dir: str,
        max_zip_mb: int,
        image_max_mb: int = DEFAULT_IMAGE_MAX_MB,
    ) -> None:
        self._session = session
        self._audit = AuditService(session)
        self._uploads_root = Path(uploads_dir)
        self._scratch = self._uploads_root / SCRATCH_SUBDIR
        self._max_zip_mb = max_zip_mb
        # Ten sam limit co przy zwykłym uploadzie (`IMAGE_MAX_UPLOAD_MB`): zdjęcie,
        # które instancja przyjęła, musi wrócić z jej własnego eksportu.
        self._image_max_bytes = image_max_mb * 1024 * 1024

    # --- eksport ---------------------------------------------------------------------

    async def export(
        self, actor: User, *, scope: TransferScope, app_version: str, now: datetime
    ) -> ExportResult:
        """Zbuduj paczkę ZIP z danymi użytkownika albo całej instancji."""
        if scope is TransferScope.INSTANCE and actor.role is not UserRole.ADMIN:
            raise ForbiddenError(INSTANCE_REQUIRES_ADMIN)

        rows = (
            await self._collect_instance(actor)
            if scope is TransferScope.INSTANCE
            else await self._collect_user(actor)
        )

        data: dict[str, list[dict[str, Any]]] = {}
        photos: list[str] = []
        for section in sections_for(scope):
            section_rows = rows.get(section.name, [])
            data[section.name] = [row_to_dict(section, row) for row in section_rows]
            photos.extend(photo_paths(section, section_rows))

        _drop_dangling_generations(data)
        document = build_document(scope=scope, app_version=app_version, exported_at=now, data=data)
        self._scratch.mkdir(parents=True, exist_ok=True)
        target = self._scratch / f"export-{uuid4().hex}.zip"
        warnings = await run_in_threadpool(
            write_archive,
            document,
            photos=photos,
            uploads_root=self._uploads_root,
            target=target,
        )

        self._audit.record(
            action=AuditAction.TRANSFER_EXPORT,
            entity_type=AuditEntity.TRANSFER,
            entity_id=None,
            actor_id=actor.id,
            payload={
                "scope": scope.value,
                "counts": {name: len(items) for name, items in data.items() if items},
                "photos": len(set(photos)),
            },
        )
        await self._session.commit()

        return ExportResult(
            path=target,
            filename=EXPORT_FILENAME.format(day=now.date().isoformat()),
            warnings=warnings,
        )

    async def _collect_instance(self, actor: User) -> dict[str, list[Any]]:
        """Cała instancja — każda sekcja w całości, posortowana po kluczu głównym."""
        collected: dict[str, list[Any]] = {}
        for section in sections_for(TransferScope.INSTANCE):
            table = section_table(section)
            statement = select(table)
            if section.pk is not None:
                statement = statement.order_by(table.c[section.pk])
            if section.name == "shopping_generations":
                statement = statement.where(
                    table.c.status.in_(
                        (GenerationStatus.FINAL.value, GenerationStatus.DISCARDED.value)
                    )
                )
            collected[section.name] = list((await self._session.execute(statement)).all())
        return collected

    async def _collect_user(self, actor: User) -> dict[str, list[Any]]:
        """Dane NALEŻĄCE do użytkownika + słowniki, do których się odwołują.

        Kolejność zbierania nie jest przypadkowa: najpierw encje właścicielskie,
        potem — z ich kluczy obcych — dokładnie te wiersze słowników, bez których
        plik nie byłby samowystarczalny. Eksport „całego katalogu" byłby prostszy,
        ale robiłby z prywatnego pliku kopię globalnego słownika instancji.
        """
        session = self._session
        collected: dict[str, list[Any]] = {}

        async def fetch(statement: sa.Select[Any]) -> list[Any]:
            return list((await session.execute(statement)).scalars().all())

        recipes = await fetch(_RECIPES.select_owned(actor).order_by(Recipe.id))
        recipe_ids = [row.id for row in recipes]
        ingredients = await fetch(
            select(RecipeIngredient)
            .where(RecipeIngredient.recipe_id.in_(recipe_ids))
            .order_by(RecipeIngredient.id)
        )
        tag_links = list(
            (
                await session.execute(
                    select(recipe_tags)
                    .where(recipe_tags.c.recipe_id.in_(recipe_ids))
                    .order_by(recipe_tags.c.recipe_id, recipe_tags.c.tag_id)
                )
            ).all()
        )
        ratings = await fetch(
            # Cudze oceny NIE wychodzą: ocena jest opinią konkretnej osoby,
            # a po imporcie nie ma komu jej przypisać (rekomendacja karty B14).
            select(RecipeRating)
            .where(RecipeRating.recipe_id.in_(recipe_ids), RecipeRating.user_id == actor.id)
            .order_by(RecipeRating.id)
        )

        days = await fetch(_PLAN_DAYS.select_owned(actor).order_by(PlanDay.id))
        day_ids = [row.id for row in days]
        meals = await fetch(
            select(PlanMeal).where(PlanMeal.plan_day_id.in_(day_ids)).order_by(PlanMeal.id)
        )
        meal_ids = [row.id for row in meals]
        items = await fetch(
            select(PlanMealItem)
            .where(PlanMealItem.plan_meal_id.in_(meal_ids))
            .order_by(PlanMealItem.id)
        )
        # Pozycja planu może wskazywać przepis, którego JUŻ nie widać: członek
        # rodziny przestawił swój przepis na `private` PO tym, jak trafił do
        # cudzego planu (FK RESTRICT trzyma pozycję przy życiu). Taka pozycja nie
        # ma pokrycia w sekcji `recipes`, więc plik byłby nie do zaimportowania
        # przez własny importer — a wyeksportowanie cudzego prywatnego przepisu
        # byłoby wyciekiem. Pozycja wypada z pliku razem ze swoim rozkładem porcji.
        exportable = set(recipe_ids)
        items = [row for row in items if row.recipe_id is None or row.recipe_id in exportable]
        item_ids = [row.id for row in items]
        splits = await fetch(
            select(PlanItemServing)
            .where(PlanItemServing.plan_meal_item_id.in_(item_ids))
            .order_by(PlanItemServing.id)
        )

        day_templates = await fetch(_DAY_TEMPLATES.select_owned(actor).order_by(DayTemplate.id))
        week_templates = await fetch(_WEEK_TEMPLATES.select_owned(actor).order_by(WeekTemplate.id))
        cycles = await fetch(_CYCLES.select_owned(actor).order_by(WeekCycle.id))

        pantry = await fetch(_PANTRY.select_own_household(actor).order_by(PantryItem.id))
        profiles = await fetch(self._profiles_statement(actor).order_by(MemberProfile.id))
        goals = await fetch(
            select(UserNutritionGoal)
            .where(UserNutritionGoal.user_id == actor.id)
            .order_by(UserNutritionGoal.id)
        )

        configs = await fetch(_ROUND_CONFIGS.select_owned(actor).order_by(ShoppingRoundConfig.id))
        generations = await fetch(
            _GENERATIONS.select_owned(actor)
            # Tylko HISTORIA: generacja `preview` jest szkicem, którego `params`
            # wskazują żywe pozycje planu instancji źródłowej. Po imporcie jej
            # finalizacja tworzyłaby pozycje list z cudzymi identyfikatorami.
            .where(
                ShoppingGeneration.status.in_((GenerationStatus.FINAL, GenerationStatus.DISCARDED))
            )
            .order_by(ShoppingGeneration.id)
        )
        lists = await fetch(_LISTS.select_owned(actor).order_by(ShoppingList.id))
        list_items = await fetch(
            select(ShoppingListItem)
            .where(ShoppingListItem.list_id.in_([row.id for row in lists]))
            .order_by(ShoppingListItem.id)
        )

        # --- słowniki: dokładnie to, na co wskazują encje wyżej -------------------
        product_ids = {row.product_id for row in ingredients}
        product_ids |= {row.product_id for row in items if row.product_id}
        product_ids |= {row.product_id for row in pantry if row.product_id}
        product_ids |= {row.product_id for row in list_items if row.product_id}
        for template in day_templates:
            product_ids |= _payload_product_ids(template.payload)
        for template in week_templates:
            for entry in template.payload.get("days") or []:
                product_ids |= _payload_product_ids(entry.get("day") or {})

        retail_ids = {row.retail_product_id for row in pantry if row.retail_product_id}
        retail_ids |= {row.retail_product_id for row in list_items if row.retail_product_id}
        retail = await fetch(
            select(RetailProduct).where(RetailProduct.id.in_(retail_ids)).order_by(RetailProduct.id)
        )
        product_ids |= {row.canonical_product_id for row in retail}
        product_ids.discard(None)

        products = await fetch(
            select(CanonicalProduct)
            .where(CanonicalProduct.id.in_(product_ids))
            .order_by(CanonicalProduct.id)
        )
        unit_weights = await fetch(
            select(ProductUnitWeight)
            .where(ProductUnitWeight.product_id.in_(product_ids))
            .order_by(ProductUnitWeight.id)
        )
        nutrient_values = await fetch(
            select(ProductNutrientValue)
            .where(ProductNutrientValue.product_id.in_(product_ids))
            .order_by(ProductNutrientValue.id)
        )
        nutrients = await fetch(
            select(Nutrient)
            .where(Nutrient.code.in_({row.nutrient_code for row in nutrient_values}))
            .order_by(Nutrient.code)
        )

        store_ids = {row.store_id for row in retail if row.store_id}
        store_ids |= {row.store_id for row in lists if row.store_id}
        stores = await fetch(select(Store).where(Store.id.in_(store_ids)).order_by(Store.id))
        category_order = list(
            (
                await session.execute(
                    select(StoreCategoryOrder)
                    .where(StoreCategoryOrder.store_id.in_(store_ids))
                    .order_by(StoreCategoryOrder.store_id, StoreCategoryOrder.position)
                )
            )
            .scalars()
            .all()
        )

        category_ids = {row.category_id for row in products}
        category_ids |= {row.category_id for row in list_items}
        category_ids |= {row.category_id for row in category_order}
        categories = await fetch(
            select(ProductCategory)
            .where(ProductCategory.id.in_(category_ids))
            .order_by(ProductCategory.position, ProductCategory.id)
        )

        tags = await fetch(
            select(Tag).where(Tag.id.in_({row.tag_id for row in tag_links})).order_by(Tag.id)
        )

        collected.update(
            product_categories=categories,
            nutrients=nutrients,
            tags=tags,
            stores=stores,
            store_category_order=category_order,
            canonical_products=products,
            product_unit_weights=unit_weights,
            product_nutrient_values=nutrient_values,
            retail_products=retail,
            member_profiles=profiles,
            user_nutrition_goals=goals,
            recipes=recipes,
            recipe_ingredients=ingredients,
            recipe_tags=tag_links,
            recipe_ratings=ratings,
            plan_days=days,
            plan_meals=meals,
            plan_meal_items=items,
            plan_item_servings=splits,
            day_templates=day_templates,
            week_templates=week_templates,
            week_cycles=cycles,
            pantry_items=pantry,
            shopping_round_configs=configs,
            shopping_generations=generations,
            shopping_lists=lists,
            shopping_list_items=list_items,
        )
        return collected

    @staticmethod
    def _profiles_statement(actor: User) -> sa.Select[Any]:
        """Profile członków MOJEJ rodziny (bez rodziny — moje własne, 03_DATABASE §2)."""
        if actor.household_id is None:
            return select(MemberProfile).where(
                MemberProfile.household_id.is_(None),
                MemberProfile.owner_user_id == actor.id,
            )
        return select(MemberProfile).where(MemberProfile.household_id == actor.household_id)

    # --- import: dry-run -------------------------------------------------------------

    async def dry_run(self, actor: User, *, filename: str, data: bytes) -> tuple[str, DryRunResult]:
        """Zwaliduj paczkę, odłóż ją w scratchu i policz raport. NIC nie zapisuje w bazie."""
        assert_within_limit(len(data), limit_mb=self._max_zip_mb)
        assert_zip_signature(data)

        self._scratch.mkdir(parents=True, exist_ok=True)
        await run_in_threadpool(self._prune_scratch)

        import_id = uuid4().hex
        archive_path = self._scratch / f"{import_id}.zip"
        await run_in_threadpool(archive_path.write_bytes, data)

        try:
            document, available = await run_in_threadpool(self._read_archive, archive_path)
            self._assert_scope_allowed(actor, document.scope)
            existing = await self._existing_index(actor, document.scope)
            result = analyze(document, existing=existing, archive_photos=available)
        except Exception:
            archive_path.unlink(missing_ok=True)
            raise

        (self._scratch / f"{import_id}.json").write_text(
            json.dumps(
                {
                    "user_id": actor.id,
                    "scope": document.scope.value,
                    "filename": filename,
                }
            ),
            encoding="utf-8",
        )
        return import_id, result

    def _read_archive(self, path: Path) -> tuple[Any, set[str]]:
        """Otwórz archiwum, wyjmij dokument i listę zdjęć (synchronicznie — I/O na pliku)."""
        with open_archive(path) as archive:
            return read_document(archive), photo_names(archive)

    def _prune_scratch(self) -> None:
        """Skasuj paczki starsze niż TTL — dry-run bez `apply` nie ma zostawać na zawsze."""
        if not self._scratch.is_dir():
            return
        deadline = datetime.now().timestamp() - SCRATCH_TTL.total_seconds()
        for entry in self._scratch.iterdir():
            try:
                if entry.is_file() and entry.stat().st_mtime < deadline:
                    entry.unlink(missing_ok=True)
            except OSError:  # pragma: no cover — sprzątanie nie ma prawa wywrócić importu
                continue

    @staticmethod
    def _assert_scope_allowed(actor: User, scope: TransferScope) -> None:
        """Plik instancji wolno wgrać wyłącznie ADMIN-owi (§Security karty B14)."""
        if scope is TransferScope.INSTANCE and actor.role is not UserRole.ADMIN:
            raise ForbiddenError(INSTANCE_FILE_FOR_USER)

    async def _existing_index(
        self, actor: User, scope: TransferScope
    ) -> dict[str, dict[str, ExistingEntity]]:
        """Nazwy, które JUŻ są w bazie — materiał do wykrywania kolizji.

        Słowniki globalne (kategorie, sklepy, tagi, produkty) mają klucze
        unikalne w całej instancji, więc szukamy w całej tabeli. Encje ze scope
        (przepisy, szablony) porównujemy z tym, co NALEŻY do importującego —
        „kolizja" z cudzym prywatnym przepisem nie jest kolizją, bo baza pozwala
        obu istnieć obok siebie.
        """
        index: dict[str, dict[str, ExistingEntity]] = {}

        async def global_index(model: Any, key: str, label: str, pk: str = "id") -> None:
            rows = (
                await self._session.execute(
                    select(getattr(model, pk), getattr(model, key), getattr(model, label))
                )
            ).all()
            index[model.__tablename__] = {
                str(row[1]): ExistingEntity(id=row[0], name=str(row[2])) for row in rows
            }

        await global_index(ProductCategory, "name", "name")
        await global_index(Nutrient, "code", "name", pk="code")
        await global_index(Tag, "name", "name")
        await global_index(Store, "name", "name")
        await global_index(CanonicalProduct, "normalized_name", "name")

        if scope is TransferScope.INSTANCE:
            await global_index(Household, "name", "name")
            await global_index(User, "email", "display_name")

        for model, query in (
            (Recipe, _RECIPES.select_owned(actor)),
            (DayTemplate, _DAY_TEMPLATES.select_owned(actor)),
            (WeekTemplate, _WEEK_TEMPLATES.select_owned(actor)),
        ):
            rows = (await self._session.execute(query)).scalars().all()
            index[model.__tablename__] = {
                row.name: ExistingEntity(id=row.id, name=row.name) for row in rows
            }
        return index

    # --- import: apply ---------------------------------------------------------------

    async def apply(
        self, actor: User, *, import_id: str, decisions: Sequence[CollisionDecision]
    ) -> ImportSummary:
        """Zastosuj odłożoną paczkę w JEDNEJ transakcji (Acceptance Criterion 5)."""
        archive_path = self._stored_import(actor, import_id)
        document, available = await run_in_threadpool(self._read_archive, archive_path)
        self._assert_scope_allowed(actor, document.scope)

        existing = await self._existing_index(actor, document.scope)
        chosen = decisions_by_key(decisions)
        id_map = IdMap(actor_user_id=actor.id, actor_household_id=actor.household_id)
        taken = {name: set(values) for name, values in existing.items()}
        created: dict[str, int] = {}
        reused: dict[str, int] = {}
        warnings: list[str] = []
        saved_photos: list[str] = []
        # Identyfikatory Z PLIKU tych wierszy, których zawartości import NIE tyka:
        # reużytych rodziców i wszystkiego, co przez nich pominięte (D22).
        blocked: dict[str, set[Any]] = {}

        try:
            for section in sections_for(document.scope):
                rows = document.data.get(section.name) or []
                for row in rows:
                    outcome = await self._import_row(
                        section,
                        row,
                        actor=actor,
                        archive_path=archive_path,
                        available=available,
                        existing=existing,
                        taken=taken,
                        chosen=chosen,
                        id_map=id_map,
                        blocked=blocked,
                        warnings=warnings,
                        saved_photos=saved_photos,
                    )
                    bucket = created if outcome == "created" else reused
                    if outcome != "skipped":
                        bucket[section.name] = bucket.get(section.name, 0) + 1

            if not created and not reused:
                raise TransferValidationError(NOTHING_TO_IMPORT)

            self._audit.record(
                action=AuditAction.TRANSFER_IMPORT,
                entity_type=AuditEntity.TRANSFER,
                entity_id=None,
                actor_id=actor.id,
                payload={
                    "scope": document.scope.value,
                    "created": created,
                    "reused": reused,
                    "decisions": [
                        {"entity": entity, "source_id": source_id, "action": action.value}
                        for (entity, source_id), action in sorted(chosen.items())
                    ],
                },
            )
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            for path in saved_photos:
                delete_image(path, uploads_root=self._uploads_root)
            raise ConflictError(IMPORT_CONFLICT) from exc
        except Exception:
            await self._session.rollback()
            # Pliki nie cofną się z transakcją — kasujemy je ręcznie, inaczej
            # nieudany import zostawiłby w magazynie zdjęcia bez właściciela.
            for path in saved_photos:
                delete_image(path, uploads_root=self._uploads_root)
            raise

        await run_in_threadpool(self._forget_import, import_id)
        return ImportSummary(
            created=created,
            reused=reused,
            photos_imported=len(saved_photos),
            warnings=warnings,
        )

    def _stored_import(self, actor: User, import_id: str) -> Path:
        """Odłożona paczka tego użytkownika; cudza albo nieznana = identyczne 404."""
        if not import_id.isalnum() or len(import_id) != 32:
            raise NotFoundError(IMPORT_NOT_FOUND)
        archive_path = self._scratch / f"{import_id}.zip"
        meta_path = self._scratch / f"{import_id}.json"
        if not archive_path.is_file() or not meta_path.is_file():
            raise NotFoundError(IMPORT_NOT_FOUND)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("user_id") != actor.id:
            raise NotFoundError(IMPORT_NOT_FOUND)
        return archive_path

    def _forget_import(self, import_id: str) -> None:
        """Paczka po zastosowaniu jest niepotrzebna — kasujemy ją od razu."""
        (self._scratch / f"{import_id}.zip").unlink(missing_ok=True)
        (self._scratch / f"{import_id}.json").unlink(missing_ok=True)

    async def _import_row(
        self,
        section: Section,
        row: Mapping[str, Any],
        *,
        actor: User,
        archive_path: Path,
        available: set[str],
        existing: Mapping[str, Mapping[str, ExistingEntity]],
        taken: dict[str, set[str]],
        chosen: Mapping[tuple[str, int], CollisionAction],
        id_map: IdMap,
        blocked: dict[str, set[Any]],
        warnings: list[str],
        saved_photos: list[str],
    ) -> str:
        """Wstaw jeden wiersz sekcji. Zwraca `created` / `reused` / `skipped`."""
        # D22: rodzic REUŻYTY (albo sam pominięty) zostaje ze swoją zawartością
        # nietknięty. Sprawdzamy to PRZED `resolve_references`, bo pominięte
        # dziecko nie trafia do `id_map` i jego własne dzieci nie miałyby czego
        # rozwiązać — dostałyby „martwą referencję" i wywróciłyby cały import.
        if parent_blocked(section, row, blocked):
            mark_blocked(section, row, blocked)
            return "skipped"

        table = section_table(section)
        references = section_references(section)
        resolved = resolve_references(section, row, id_map, references)

        values: dict[str, Any] = {}
        for column in section_columns(section):
            if column in row:
                values[column] = coerce_value(table.c[column], row[column])
        values.update(resolved)

        key = natural_key(section, row)
        section_existing = existing.get(section.name, {})
        match = section_existing.get(key) if key is not None else None
        if match is not None:
            source_id = row.get(section.pk) if section.pk else None
            action = (
                CollisionAction.USE_EXISTING
                if section.auto_reuse
                else chosen.get(
                    (section.name, source_id if isinstance(source_id, int) else -1),
                    CollisionAction.USE_EXISTING,
                )
            )
            if action is CollisionAction.USE_EXISTING:
                if section.pk is not None:
                    id_map.record(section.name, row.get(section.pk), match.id)
                mark_blocked(section, row, blocked)
                return "reused"
            key = self._rename_copy(section, values, taken.setdefault(section.name, set()))

        if section.name == "users":
            # Hasło NIGDY nie opuszcza bazy, więc konto z importu dostaje losowe,
            # nieodgadywalne — ADMIN nadaje właściwe przez `PATCH /admin/users/{id}`.
            # argon2 jest CPU-bound (~50 ms), więc idzie do puli wątków: import
            # instancji z kilkudziesięcioma kontami inaczej zatrzymałby pętlę
            # zdarzeń na kilka sekund (ADR-015, wzorzec `accounts/service.py`).
            values["password_hash"] = await run_in_threadpool(hash_password, generate_token())
            warnings.append(
                f"Konto {values.get('email')} powstało bez hasła — ustaw je w sekcji Użytkownicy."
            )

        self._apply_section_quirks(section, values, id_map=id_map, warnings=warnings)
        if section.name == "week_cycles" and not values.get("template_ids"):
            warnings.append(f"Pominięto cykl „{display_name(section, row)}” — brak szablonów.")
            return "skipped"

        if section.photo is not None:
            values[section.photo] = await self._import_photo(
                archive_path,
                relative=row.get(section.photo),
                available=available,
                saved_photos=saved_photos,
                warnings=warnings,
            )

        if section.pk is None:
            # Tabela asocjacyjna: para kluczy JEST kluczem głównym, więc powtórka
            # z pliku (albo istniejące powiązanie) nie jest błędem.
            await self._session.execute(pg_insert(table).values(**values).on_conflict_do_nothing())
            return "created"

        if section.idempotent:
            # UNIQUE tej sekcji wyraża FAKT (przelicznik, ocena, cel na datę),
            # który reużyty rodzic już ma — powtórka nie jest błędem importu.
            # `RETURNING` zamiast `rowcount`: pominięty wiersz nie zwraca nic,
            # więc od razu wiadomo, czy powstał, czy zadziałał konflikt.
            skipped = (
                await self._session.execute(
                    pg_insert(table)
                    .values(**values)
                    .on_conflict_do_nothing()
                    .returning(table.c[section.pk])
                )
            ).scalar_one_or_none()
            if skipped is None:
                mark_blocked(section, row, blocked)
                return "reused"
            return "created"

        if section.merge_key is not None:
            new_id = (
                await self._session.execute(
                    pg_insert(table)
                    .values(**values)
                    .on_conflict_do_nothing()
                    .returning(table.c[section.pk])
                )
            ).scalar_one_or_none()
            if new_id is None:
                new_id = (
                    await self._session.execute(
                        select(table.c[section.pk]).where(
                            *[table.c[column] == values[column] for column in section.merge_key]
                        )
                    )
                ).scalar_one()
                id_map.record(section.name, row.get(section.pk), new_id)
                mark_blocked(section, row, blocked)
                return "reused"
            id_map.record(section.name, row.get(section.pk), new_id)
            return "created"

        new_id = (
            await self._session.execute(
                pg_insert(table).values(**values).returning(table.c[section.pk])
            )
        ).scalar_one()
        id_map.record(section.name, row.get(section.pk), new_id)
        if key is not None:
            taken.setdefault(section.name, set()).add(key)
        return "created"

    @staticmethod
    def _rename_copy(section: Section, values: dict[str, Any], taken: set[str]) -> str:
        """„Utwórz kopię": nazwa z sufiksem „(import)" i spójny klucz naturalny."""
        label_column = section.label or section.key
        assert label_column is not None  # sekcja z kolizją zawsze ma nazwę
        base = str(values.get(label_column, ""))
        if section.key == "normalized_name":
            fresh = unique_name(base, taken, normalize=normalize_name)
            values[label_column] = fresh
            normalized = normalize_name(fresh)
            values["normalized_name"] = normalized
            return normalized
        fresh = unique_name(base, taken)
        values[label_column] = fresh
        return fresh

    @staticmethod
    def _apply_section_quirks(
        section: Section,
        values: dict[str, Any],
        *,
        id_map: IdMap,
        warnings: list[str],
    ) -> None:
        """Wyjątki formatu, których nie da się opisać kolumnami sekcji."""
        # Bez rodziny scope HOUSEHOLD jest niedozwolony (CHECK w bazie), więc
        # import na konto bez rodziny zapisuje encje jako prywatne.
        if section.scoped and values.get("household_id") is None:
            values["scope"] = Scope.PRIVATE
        if section.name == "day_templates":
            values["payload"] = remap_template_payload(
                values.get("payload") or {}, id_map, warnings=warnings
            )
        if section.name == "week_templates":
            values["payload"] = remap_week_payload(
                values.get("payload") or {}, id_map, warnings=warnings
            )
        if section.name == "week_cycles":
            values["template_ids"] = remap_cycle_templates(
                values.get("template_ids") or [], id_map, warnings=warnings
            )

    async def _import_photo(
        self,
        archive_path: Path,
        *,
        relative: Any,
        available: set[str],
        saved_photos: list[str],
        warnings: list[str],
    ) -> str | None:
        """Zdjęcie z archiwum → nowy plik przez ten sam pipeline, co upload (07_SECURITY §6)."""
        if not relative or str(relative) not in available:
            return None

        def read_and_save() -> str:
            with open_archive(archive_path) as archive:
                payload = archive.read(f"{PHOTOS_PREFIX}{relative}")
            saved = save_image(
                payload,
                uploads_root=self._uploads_root,
                subdir=IMPORT_PHOTO_SUBDIR,
                max_bytes=self._image_max_bytes,
            )
            return saved.path

        try:
            path = await run_in_threadpool(read_and_save)
        except Exception:
            # Zdjęcie nie jest blokerem importu (Implementation Notes karty B14),
            # ale MUSI zostawić ślad: dry-run ostrzega tylko o zdjęciach, których
            # w archiwum NIE MA, a to jest wpis obecny i nieczytelny.
            warnings.append(f"Nie udało się wczytać zdjęcia {relative} — pozycja bez zdjęcia.")
            return None
        saved_photos.append(path)
        return path


def _drop_dangling_generations(data: dict[str, list[dict[str, Any]]]) -> None:
    """Wyzeruj `generation_id` list, których generacji nie ma w pliku.

    Eksport pomija generacje w stanie `preview` (szkice), więc lista mogłaby
    zostać z odnośnikiem donikąd. Kolumna jest NULL-owalna, a treść listy jest
    kompletna sama w sobie — traci wyłącznie link do historii generacji.
    """
    known = {row["id"] for row in data.get("shopping_generations", [])}
    for row in data.get("shopping_lists", []):
        if row.get("generation_id") not in known:
            row["generation_id"] = None


def _payload_product_ids(payload: Mapping[str, Any]) -> set[int]:
    """Identyfikatory produktów wskazane w payloadzie szablonu dnia."""
    found: set[int] = set()
    for meal in payload.get("meals") or []:
        for item in meal.get("items") or []:
            product_id = item.get("product_id")
            if isinstance(product_id, int):
                found.add(product_id)
    return found


def cleanup_file(path: Path) -> None:
    """Skasuj plik paczki po wysłaniu odpowiedzi (BackgroundTask routera)."""
    path.unlink(missing_ok=True)


__all__ = [
    "ExportResult",
    "TransferService",
    "cleanup_file",
    "coerce_value",
    "section_table",
]
