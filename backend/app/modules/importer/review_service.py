"""Review importu PDF: rozstrzygnięcia człowieka, zatwierdzenie i odrzucenie.

DRUGI serwis modułu importer (obok `service.py`, które kończy się na `parsed`).
Podział jest taki sam jak w module shopping (`service.py` generuje, a
`lists_service.py` prowadzi życie gotowej listy): tam kończy się maszyna, tu
zaczyna się człowiek.

Cztery reguły, na których stoi ten plik:

1. **Nic nie powstaje przed `approve`** (niezmiennik 02_DOMAIN §13.6). `resolve`
   i `ai-suggest` piszą WYŁĄCZNIE do czterech tabel stagingu. Dopiero
   `approve` tworzy przepisy, produkty i próbki przeliczników — i robi to
   w JEDNEJ transakcji, bo połowa zaimportowanego jadłospisu jest gorsza niż
   jego brak (ADR-011).
2. **Issues pochodne przelicza się od zera przy każdym `resolve`.**
   `unmapped_product` i `kcal_mismatch` wynikają ze stanu mapowań, więc zamiast
   „aktualizować" je punktowo, kasujemy i wyliczamy ponownie. Dzięki temu
   auto-rozwiązanie („poprawiłem mapowanie, mismatch znika") jest własnością
   algorytmu, a nie osobną ścieżką, którą trzeba pamiętać.
3. **Walidacja kcal liczy się PER POSIŁEK, nie per danie.** `pdf_kcal` opisuje
   w dokumencie posiłek (01_PDF_AUDIT §3.1) i BATCH_15 skopiował tę wartość do
   każdego dania posiłku. Porównanie jednego z dwóch dań kolacji z kcal całej
   kolacji zgłaszałoby rozjazd tam, gdzie go nie ma — to ta sama poprawka,
   którą errata §9.1 zrobiła dla progu wieloporcyjności. Odstępstwo od karty
   B16 („komplet mapowań DANIA"), świadome i opisane w Completion notes.
4. **Sekcja `Produkty` nie dzieli się przez liczbę porcji.** Dodatek z tej
   sekcji jest podany na JEDNĄ porcję, a reszta przepisu na całość
   (01_PDF_AUDIT §7). Przy zapisie mnożymy go więc przez `base_servings`, żeby
   po podzieleniu wrócił do gramatury z dokumentu (dług U22, kolumna
   `from_extras_section` z migracji `0015`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from app.core.errors import ConflictError, NotFoundError, ServiceUnavailableError
from app.core.scope import Scope
from app.modules.accounts.models import User
from app.modules.audit.service import AuditAction, AuditEntity, AuditService
from app.modules.catalog.models import CanonicalProduct, MeasureKind, ProductCategory
from app.modules.catalog.naming import normalize_name
from app.modules.catalog.nutrition_adapter import measure_for, nutrition_for
from app.modules.catalog.service import CatalogService
from app.modules.catalog.units import (
    UnitConversionError,
    canonical_unit_label,
    normalize_amount,
    to_basis_amount,
)
from app.modules.importer.ai_assist import (
    AI_UNAVAILABLE,
    CANDIDATES_PER_NAME,
    AiAssistant,
    AiSuggestions,
    CatalogCandidate,
    RecipeToMatch,
    UnmappedName,
)
from app.modules.importer.models import (
    ImportIssue,
    ImportIssueKind,
    ImportIssueSeverity,
    ImportJob,
    ImportJobStatus,
    MatchKind,
    StagedIngredient,
    StagedRecipe,
    StagedRecipeResolution,
)
from app.modules.importer.service import ImporterService
from app.modules.nutrition.engine import aggregate, ingredient_nutrition, round_for_output
from app.modules.nutrition.types import ZERO_VALUES, NutritionValues
from app.modules.recipes.service import ImportedIngredient, RecipesService

__all__ = [
    "DEFAULT_NEW_PRODUCT_CATEGORY",
    "KCAL_TOLERANCE",
    "REVIEWABLE_STATUSES",
    "UNIT_WEIGHT_SOURCE",
    "ApproveResult",
    "Blocker",
    "IngredientDecision",
    "IssueDecision",
    "RecipeDecision",
    "ReviewService",
    "StagedIngredientView",
    "StagedJobView",
    "StagedRecipeView",
]

#: Statusy, w których job wolno rozstrzygać i zatwierdzać. `approved`/`rejected`
#: są historią decyzji, a `uploaded`/`failed` nie mają stagingu.
REVIEWABLE_STATUSES = (ImportJobStatus.PARSED, ImportJobStatus.IN_REVIEW)

#: Dopuszczalny rozjazd kcal wyliczonych wobec `pdf_kcal` (ADR-011: „ponad próg
#: — proponowane 10% — ⇒ issue"). Wyżej byłby fałszywy spokój, niżej szum:
#: gramatury z jadłospisu są zaokrąglane, a wartości produktów pochodzą z tabel.
KCAL_TOLERANCE = Decimal("0.10")

#: Źródło próbek przeliczników wnoszonych importem. Wiersze o INNYM źródle
#: (ręczne, bez etykiety) są nietykalne — patrz `record_unit_weight_samples`.
UNIT_WEIGHT_SOURCE = "pdf_import"

#: Kategoria produktów zakładanych flagą `create_new_product` bez danych.
#: Ścieżka UI używa `ProductCreateDrawer` (create-in-context, 06_UIUX §3.1)
#: i przysyła gotowy `confirmed_product_id`; ta stała ratuje ścieżkę czysto
#: API-ową, żeby import nie wymagał klikania w UI.
DEFAULT_NEW_PRODUCT_CATEGORY = "Inne"

#: Ilu istniejących przepisów pokazujemy AI przy szukaniu duplikatów. Sufit,
#: nie filtr: przy większym katalogu prompt przestałby być zadaniem.
DUPLICATE_CANDIDATES = 300

JOB_NOT_REVIEWABLE = (
    "Tego importu nie da się już rozstrzygać — jest zatwierdzony, odrzucony "
    "albo zakończył się błędem odczytu."
)
STAGED_RECIPE_NOT_FOUND = "To danie nie należy do tego importu."
STAGED_INGREDIENT_NOT_FOUND = "Ten składnik nie należy do tego importu."
ISSUE_NOT_FOUND = "Ta uwaga nie należy do tego importu."
PRODUCT_NOT_FOUND = "Wskazany produkt nie istnieje w katalogu."
MERGE_TARGET_REQUIRED = "Scalenie wymaga wskazania przepisu, z którym danie ma się połączyć."
MERGE_TARGET_UNEXPECTED = "Przepis docelowy ma sens wyłącznie przy scaleniu z istniejącym."
APPROVE_BLOCKED = (
    "Nie można zatwierdzić importu, dopóki są nierozstrzygnięte blokady. "
    "Uzupełnij je na ekranie review i spróbuj ponownie."
)
NOTHING_TO_APPROVE = (
    "Wszystkie dania tego importu są pominięte — nie ma czego zatwierdzić. "
    "Odrzuć import albo zmień decyzję przy którymś daniu."
)
CATEGORY_MISSING = (
    "W katalogu nie ma kategorii „Inne”, do której trafiają produkty zakładane "
    "importem. Uzupełnij słownik kategorii i spróbuj ponownie."
)

#: Kwant różnicy procentowej w odpowiedziach — zaokrąglamy wyłącznie na wyjściu.
_PCT_QUANTUM = Decimal("0.1")


# --- wejście (decyzje człowieka) --------------------------------------------------


@dataclass(frozen=True)
class IngredientDecision:
    """Rozstrzygnięcie mapowania jednego składnika."""

    ingredient_id: int
    #: `None` = wyczyść potwierdzenie (człowiek się rozmyślił).
    confirmed_product_id: int | None = None
    create_new_product: bool = False


@dataclass(frozen=True)
class RecipeDecision:
    """Rozstrzygnięcia dotyczące jednego dania ze stagingu."""

    staged_recipe_id: int
    #: Poprawiona nazwa — 3 ze 103 nazw dań są ucięte przez zawijanie kolumn
    #: (errata 01_PDF_AUDIT §9.5), a parser świadomie ich nie zgaduje.
    name: str | None = None
    resolution: StagedRecipeResolution | None = None
    target_recipe_id: int | None = None
    resolved_servings: int | None = None


@dataclass(frozen=True)
class IssueDecision:
    """Ręczne zamknięcie uwagi (np. „to jednak osobny przepis")."""

    issue_id: int
    resolution: str


# --- wyjście (widok review) -------------------------------------------------------


@dataclass(frozen=True)
class StagedIngredientView:
    """Wiersz składnika razem z nazwami produktów, żeby UI nie dociągał ich osobno."""

    ingredient: StagedIngredient
    suggested_product: CanonicalProduct | None
    confirmed_product: CanonicalProduct | None


@dataclass(frozen=True)
class MealNutrition:
    """Wynik walidacji kcal JEDNEGO posiłku (może mieć kilka dań)."""

    #: `None` = nie da się policzyć (brak mapowań albo brak wartości produktów).
    computed_kcal: Decimal | None
    pdf_kcal: Decimal | None
    delta_pct: Decimal | None
    #: Czemu nie policzono — gotowy komunikat dla UI albo pusty string.
    reason: str = ""


@dataclass(frozen=True)
class StagedRecipeView:
    """Danie ze stagingu ze wszystkim, czego potrzebuje karta w review."""

    recipe: StagedRecipe
    ingredients: list[StagedIngredientView]
    issues: list[ImportIssue]
    #: Wartości POSIŁKU, do którego należy danie (patrz reguła 3 w nagłówku).
    meal: MealNutrition


@dataclass(frozen=True)
class Blocker:
    """Jedna rzecz blokująca zatwierdzenie — trafia wprost do `details` 409."""

    staged_recipe_id: int | None
    recipe_name: str
    kind: ImportIssueKind
    message: str


@dataclass(frozen=True)
class StagedJobView:
    """Kompletny stan review jednego joba."""

    job: ImportJob
    recipes: list[StagedRecipeView]
    #: Uwagi dotyczące CAŁEGO joba (bez `staged_recipe_id`), np. `parse_warning`.
    job_issues: list[ImportIssue]
    blockers: list[Blocker]
    ai_available: bool


@dataclass(frozen=True)
class ApproveResult:
    """Podsumowanie zatwierdzenia — liczby, które UI pokazuje człowiekowi."""

    job: ImportJob
    created_recipe_ids: list[int]
    created_product_ids: list[int]
    merged_count: int
    skipped_count: int
    unit_weight_rows: int


class ReviewService:
    """Rozstrzyganie, zatwierdzanie i odrzucanie importów PDF (BATCH_16)."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        uploads_dir: str,
        max_pdf_mb: int,
        assistant: AiAssistant,
    ) -> None:
        self._session = session
        self._audit = AuditService(session)
        self._uploads_root = Path(uploads_dir)
        self._assistant = assistant
        self._jobs = ImporterService(session, uploads_dir=uploads_dir, max_pdf_mb=max_pdf_mb)
        self._catalog = CatalogService(session)
        self._recipes = RecipesService(session)

    # --- odczyt ------------------------------------------------------------------

    async def staged(self, job_id: int, *, actor: User) -> StagedJobView:
        """Stan review joba: dania, składniki, uwagi i lista blokad."""
        job = await self._jobs.get_job(job_id, actor=actor)
        return await self._view(job)

    # --- rozstrzyganie -----------------------------------------------------------

    async def resolve(
        self,
        job_id: int,
        *,
        actor: User,
        recipes: list[RecipeDecision],
        ingredients: list[IngredientDecision],
        issues: list[IssueDecision],
    ) -> StagedJobView:
        """Zapisz decyzje człowieka. Przyrostowo — wołane po każdej akcji w UI.

        Pierwszy `resolve` przestawia job `parsed → in_review`: od tego momentu
        wiadomo, że ktoś przy nim siedzi, a lista importów pokazuje to wprost.
        """
        job = await self._reviewable_job(job_id, actor=actor)
        staged = await self._staged_recipes(job.id)
        by_id = {row.id: row for row in staged}

        await self._apply_recipe_decisions(recipes, by_id, actor=actor)
        await self._apply_ingredient_decisions(ingredients, by_id)
        await self._apply_issue_decisions(issues, job)

        await self._session.flush()
        await self._refresh_derived_issues(job)
        if job.status is ImportJobStatus.PARSED:
            job.status = ImportJobStatus.IN_REVIEW
        await self._session.commit()

        return await self._view(await self._jobs.get_job(job_id, actor=actor))

    async def ai_suggest(self, job_id: int, *, actor: User) -> StagedJobView:
        """Uruchom AI-asystę: fuzzy mapowania, duplikaty, podpowiedzi porcji.

        Idempotentne w tym sensie, że nadpisuje WYŁĄCZNIE propozycje
        (`suggested_product_id`, `match_kind`, `confidence`) składników jeszcze
        niepotwierdzonych. Potwierdzone mapowanie jest decyzją człowieka i AI
        nie ma prawa go ruszyć (ADR-011).
        """
        if not self._assistant.available:
            raise ServiceUnavailableError(AI_UNAVAILABLE)

        job = await self._reviewable_job(job_id, actor=actor)
        staged = await self._staged_recipes(job.id)
        suggestions = await self._ask_assistant(staged, actor=actor)

        await self._store_mapping_suggestions(staged, suggestions)
        await self._store_duplicate_issues(job, staged, suggestions)
        self._store_servings_hints(await self._issues(job.id), suggestions)

        await self._session.flush()
        await self._refresh_derived_issues(job)
        if job.status is ImportJobStatus.PARSED:
            job.status = ImportJobStatus.IN_REVIEW
        await self._session.commit()

        return await self._view(await self._jobs.get_job(job_id, actor=actor))

    # --- zatwierdzenie i odrzucenie ----------------------------------------------

    async def approve(self, job_id: int, *, actor: User, scope: Scope) -> ApproveResult:
        """Zatwierdź import: przepisy, produkty i próbki przeliczników w JEDNEJ transakcji.

        Kolejność jest wymuszona przez zależności, nie przez gust: najpierw
        produkty (przepis nie może wskazać czegoś, czego nie ma), potem przepisy,
        na końcu próbki przeliczników — te ostatnie liczą się z tych samych
        wierszy stagingu, ale nie zależą od powstania przepisu, więc wnoszą je
        także dania scalane z istniejącym przepisem.
        """
        job = await self._reviewable_job(job_id, actor=actor)
        staged = await self._staged_recipes(job.id)

        await self._refresh_derived_issues(job)
        await self._session.flush()

        blockers = await self._blockers(job, staged)
        if blockers:
            raise ConflictError(
                APPROVE_BLOCKED,
                details={"blockers": [_blocker_payload(item) for item in blockers]},
            )

        active = [row for row in staged if row.resolution is not StagedRecipeResolution.SKIP]
        if not active:
            raise ConflictError(NOTHING_TO_APPROVE)

        created_products = await self._create_pending_products(active, actor=actor)
        created_recipes: list[int] = []
        merged = 0
        for row in active:
            if row.resolution is StagedRecipeResolution.MERGE_INTO_EXISTING:
                merged += 1
                continue
            recipe = await self._recipes.create_imported_recipe(
                actor=actor,
                scope=scope,
                import_job_id=job.id,
                name=row.name,
                instructions=_instructions_for(row),
                base_servings=_servings_for(row),
                ingredients=_imported_ingredients(row),
            )
            created_recipes.append(recipe.id)

        unit_weight_rows = await self._record_unit_weights(active, actor=actor)

        job.status = ImportJobStatus.APPROVED
        self._audit.record(
            action=AuditAction.IMPORT_APPROVE,
            entity_type=AuditEntity.IMPORT_JOB,
            entity_id=job.id,
            actor_id=actor.id,
            # Wyłącznie liczby (07_SECURITY §8) — nigdy nazw dań ani produktów.
            payload={
                "status": job.status.value,
                "scope": scope.value,
                "recipes_created": len(created_recipes),
                "recipes_merged": merged,
                "recipes_skipped": len(staged) - len(active),
                "products_created": len(created_products),
                "unit_weight_rows": unit_weight_rows,
            },
        )
        await self._session.commit()
        await self._session.refresh(job)
        return ApproveResult(
            job=job,
            created_recipe_ids=created_recipes,
            created_product_ids=created_products,
            merged_count=merged,
            skipped_count=len(staged) - len(active),
            unit_weight_rows=unit_weight_rows,
        )

    async def reject(self, job_id: int, *, actor: User) -> ImportJob:
        """Odrzuć import: kasuje staging i plik PDF, job zostaje jako historia decyzji.

        Job NIE znika, bo `DELETE /import/jobs/{id}` świadomie nie przyjmuje
        statusów rozstrzygniętych (karta B15) — ślad „ten plik wgrano i
        odrzucono" jest wart tyle, ile jeden wiersz.

        Plik kasujemy PO commicie, tą samą kolejnością co `delete_job`: plik
        osierocony przez błąd kasowania jest problemem sprzątania, a wiersz
        wskazujący w pustkę po nieudanym commicie byłby problemem spójności.
        """
        job = await self._reviewable_job(job_id, actor=actor)
        staged_count = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(StagedRecipe)
                    .where(StagedRecipe.import_job_id == job.id)
                )
            ).scalar_one()
        )

        await self._session.execute(
            delete(StagedRecipe).where(StagedRecipe.import_job_id == job.id)
        )
        await self._session.execute(delete(ImportIssue).where(ImportIssue.import_job_id == job.id))
        job.status = ImportJobStatus.REJECTED
        self._audit.record(
            action=AuditAction.IMPORT_REJECT,
            entity_type=AuditEntity.IMPORT_JOB,
            entity_id=job.id,
            actor_id=actor.id,
            payload={"status": job.status.value, "staged_recipes_removed": staged_count},
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(JOB_NOT_REVIEWABLE) from exc

        path = self._safe_upload_path(job.file_path)
        if path is not None:
            await run_in_threadpool(path.unlink, missing_ok=True)
        await self._session.refresh(job)
        return job

    # --- rozstrzygnięcia: zapis ---------------------------------------------------

    async def _apply_recipe_decisions(
        self,
        decisions: list[RecipeDecision],
        by_id: dict[int, StagedRecipe],
        *,
        actor: User,
    ) -> None:
        for decision in decisions:
            row = by_id.get(decision.staged_recipe_id)
            if row is None:
                raise NotFoundError(STAGED_RECIPE_NOT_FOUND)

            if decision.name is not None:
                row.name = decision.name
            if decision.resolved_servings is not None:
                row.resolved_servings = decision.resolved_servings
            if decision.resolution is not None:
                row.resolution = decision.resolution

            resolution = row.resolution
            if resolution is StagedRecipeResolution.MERGE_INTO_EXISTING:
                target = decision.target_recipe_id or row.target_recipe_id
                if target is None:
                    raise ConflictError(MERGE_TARGET_REQUIRED)
                # Widoczność przepisu docelowego liczy MODUŁ RECIPES — własny
                # filtr scope w cudzym serwisie jest błędem review (CLAUDE.md §4).
                await self._recipes.get_visible(target, actor=actor)
                row.target_recipe_id = target
            else:
                if decision.target_recipe_id is not None:
                    raise ConflictError(MERGE_TARGET_UNEXPECTED)
                row.target_recipe_id = None

    async def _apply_ingredient_decisions(
        self, decisions: list[IngredientDecision], by_id: dict[int, StagedRecipe]
    ) -> None:
        if not decisions:
            return
        ingredient_ids = {decision.ingredient_id for decision in decisions}
        rows = {
            row.id: row
            for row in (
                await self._session.execute(
                    select(StagedIngredient).where(StagedIngredient.id.in_(ingredient_ids))
                )
            )
            .scalars()
            .all()
        }
        product_ids = {
            decision.confirmed_product_id
            for decision in decisions
            if decision.confirmed_product_id is not None
        }
        known_products = set(
            (
                await self._session.execute(
                    select(CanonicalProduct.id).where(CanonicalProduct.id.in_(product_ids))
                )
            ).scalars()
        )

        for decision in decisions:
            row = rows.get(decision.ingredient_id)
            if row is None or row.staged_recipe_id not in by_id:
                raise NotFoundError(STAGED_INGREDIENT_NOT_FOUND)
            if (
                decision.confirmed_product_id is not None
                and decision.confirmed_product_id not in known_products
            ):
                raise NotFoundError(PRODUCT_NOT_FOUND)

            row.confirmed_product_id = decision.confirmed_product_id
            # Flagi „załóż nowy" i potwierdzonego produktu wykluczają się: obie
            # naraz znaczyłyby „zmapuj na X i jednocześnie utwórz coś nowego".
            row.create_new_product = decision.create_new_product and (
                decision.confirmed_product_id is None
            )

    async def _apply_issue_decisions(self, decisions: list[IssueDecision], job: ImportJob) -> None:
        if not decisions:
            return
        issue_ids = {decision.issue_id for decision in decisions}
        rows = {
            row.id: row
            for row in (
                await self._session.execute(
                    select(ImportIssue).where(
                        ImportIssue.id.in_(issue_ids), ImportIssue.import_job_id == job.id
                    )
                )
            )
            .scalars()
            .all()
        }
        now = datetime.now(UTC)
        for decision in decisions:
            row = rows.get(decision.issue_id)
            if row is None:
                raise NotFoundError(ISSUE_NOT_FOUND)
            row.resolution = decision.resolution.strip()
            row.resolved_at = now

    # --- issues pochodne ----------------------------------------------------------

    async def _refresh_derived_issues(self, job: ImportJob) -> None:
        """Przelicz `unmapped_product` i `kcal_mismatch` od zera (reguła 2 z nagłówka).

        `multi_portion_suspect` przy okazji zamyka się sam, gdy danie dostało
        liczbę porcji — to jest dokładnie ta informacja, o którą issue prosiło.
        """
        await self._session.execute(
            delete(ImportIssue).where(
                ImportIssue.import_job_id == job.id,
                ImportIssue.kind.in_(
                    [ImportIssueKind.UNMAPPED_PRODUCT, ImportIssueKind.KCAL_MISMATCH]
                ),
            )
        )
        staged = await self._staged_recipes(job.id)
        for row in staged:
            # Blokada dotyczy WYŁĄCZNIE dań, które mają powstać jako przepisy.
            # Pominięte nie wchodzą nigdzie, a scalane z istniejącym przepisem
            # nie wnoszą swoich składników do danych — żądanie zmapowania ośmiu
            # pozycji dania uznanego za duplikat byłoby pracą bez odbiorcy.
            if row.resolution in (
                StagedRecipeResolution.SKIP,
                StagedRecipeResolution.MERGE_INTO_EXISTING,
            ):
                continue
            unmapped = [item.raw_name for item in row.ingredients if not _is_mapped(item)]
            if unmapped:
                self._session.add(
                    ImportIssue(
                        import_job_id=job.id,
                        staged_recipe_id=row.id,
                        kind=ImportIssueKind.UNMAPPED_PRODUCT,
                        severity=ImportIssueSeverity.BLOCKER,
                        details={
                            "powód": "Składniki bez wskazanego produktu z katalogu",
                            "składniki": unmapped[:20],
                            "liczba": len(unmapped),
                        },
                    )
                )

        nutrition = await self._meal_nutrition(staged)
        for key, result in nutrition.items():
            if result.delta_pct is None or abs(result.delta_pct) <= KCAL_TOLERANCE * 100:
                continue
            # Uwagę wieszamy na pierwszym AKTYWNYM daniu posiłku: przypięcie jej
            # do dania pominiętego schowałoby ją przed człowiekiem, bo karta
            # pominiętego dania jest wyszarzona i zwinięta.
            anchor = next(
                row
                for row in staged
                if (row.day_label, row.meal_label) == key
                and row.resolution is not StagedRecipeResolution.SKIP
            )
            self._session.add(
                ImportIssue(
                    import_job_id=job.id,
                    staged_recipe_id=anchor.id,
                    kind=ImportIssueKind.KCAL_MISMATCH,
                    severity=ImportIssueSeverity.WARNING,
                    details={
                        "powód": (
                            "Kalorie wyliczone z produktów różnią się od podanych "
                            "w jadłospisie o więcej niż 10%"
                        ),
                        "wyliczone": _fmt(result.computed_kcal),
                        "z_pdf": _fmt(result.pdf_kcal),
                        "różnica_proc": _fmt(result.delta_pct),
                        "dzień": anchor.day_label,
                        "posiłek": anchor.meal_label,
                    },
                )
            )

        for issue in await self._issues(job.id):
            if (
                issue.kind is ImportIssueKind.MULTI_PORTION_SUSPECT
                and issue.resolved_at is None
                and issue.staged_recipe_id is not None
            ):
                dish = next((row for row in staged if row.id == issue.staged_recipe_id), None)
                if dish is not None and dish.resolved_servings is not None:
                    issue.resolution = f"Ustalono liczbę porcji: {dish.resolved_servings}."
                    issue.resolved_at = datetime.now(UTC)

    # --- walidacja kcal -----------------------------------------------------------

    async def _meal_nutrition(
        self, staged: list[StagedRecipe]
    ) -> dict[tuple[str, str], MealNutrition]:
        """Kalorie na porcję dla każdego POSIŁKU joba (reguła 3 z nagłówka)."""
        product_ids = {
            item.confirmed_product_id
            for row in staged
            for item in row.ingredients
            if item.confirmed_product_id is not None
        }
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

        meals: dict[tuple[str, str], list[StagedRecipe]] = {}
        for row in staged:
            meals.setdefault((row.day_label, row.meal_label), []).append(row)

        results: dict[tuple[str, str], MealNutrition] = {}
        for key, dishes in meals.items():
            results[key] = _meal_result(dishes, products)
        return results

    # --- AI ------------------------------------------------------------------------

    async def _ask_assistant(self, staged: list[StagedRecipe], *, actor: User) -> AiSuggestions:
        """Zbierz materiał dla asysty i odpal oba zadania (ADR-011)."""
        unmapped = await self._unmapped_names(staged)
        mappings = await self._assistant.suggest_mappings(unmapped)

        existing = await self._existing_recipes(actor=actor)
        to_match = [
            RecipeToMatch(staged_recipe_id=row.id, name=row.name)
            for row in staged
            if row.resolution is not StagedRecipeResolution.SKIP
        ]
        instructions = {row.id: row.instructions for row in staged}
        duplicates, servings = await self._assistant.suggest_duplicates_and_servings(
            to_match, existing, instructions
        )
        return AiSuggestions(mappings=mappings, duplicates=duplicates, servings=servings)

    async def _unmapped_names(self, staged: list[StagedRecipe]) -> list[UnmappedName]:
        """Surowe nazwy bez potwierdzenia + kandydaci z katalogu (wyszukiwanie trigramowe)."""
        names = sorted(
            {
                item.raw_name
                for row in staged
                if row.resolution is not StagedRecipeResolution.SKIP
                for item in row.ingredients
                if not _is_mapped(item) and item.suggested_product_id is None
            }
        )
        entries: list[UnmappedName] = []
        for raw_name in names:
            views, _ = await self._catalog.list_products(
                query=raw_name, limit=CANDIDATES_PER_NAME, offset=0, include_archived=False
            )
            entries.append(
                UnmappedName(
                    raw_name=raw_name,
                    candidates=tuple(
                        CatalogCandidate(product_id=view.product.id, name=view.product.name)
                        for view in views
                    ),
                )
            )
        return entries

    async def _existing_recipes(self, *, actor: User) -> list[CatalogCandidate]:
        """WŁASNE przepisy użytkownika — materiał do wykrywania duplikatów.

        `CatalogCandidate` niesie tu przepis, nie produkt: pole `product_id`
        jest po prostu identyfikatorem pozycji na liście kandydatów i nie ma
        powodu mnożyć dataclass o identycznym kształcie.

        Bierzemy przepisy WŁASNE, nie „widoczne": nazwy wychodzą poza instancję,
        a ADMIN widzi wszystkie rodziny (D16) — patrz `RecipesService.owned_names`.
        """
        rows = await self._recipes.owned_names(actor=actor, limit=DUPLICATE_CANDIDATES)
        return [CatalogCandidate(product_id=recipe_id, name=name) for recipe_id, name in rows]

    async def _store_mapping_suggestions(
        self, staged: list[StagedRecipe], suggestions: AiSuggestions
    ) -> None:
        """Zapisz propozycje AI do stagingu — jako SUGESTIE, nigdy potwierdzenia."""
        by_name = {item.raw_name: item for item in suggestions.mappings}
        for row in staged:
            for item in row.ingredients:
                proposal = by_name.get(item.raw_name)
                if proposal is None or _is_mapped(item):
                    continue
                item.suggested_product_id = proposal.product_id
                item.match_kind = MatchKind.AI
                item.confidence = proposal.confidence

    async def _store_duplicate_issues(
        self, job: ImportJob, staged: list[StagedRecipe], suggestions: AiSuggestions
    ) -> None:
        """Propozycje scalenia jako issues `duplicate_recipe` (warning, nie blocker)."""
        await self._session.execute(
            delete(ImportIssue).where(
                ImportIssue.import_job_id == job.id,
                ImportIssue.kind == ImportIssueKind.DUPLICATE_RECIPE,
                ImportIssue.resolved_at.is_(None),
            )
        )
        known = {row.id for row in staged}
        for proposal in suggestions.duplicates:
            if proposal.staged_recipe_id not in known:
                continue
            self._session.add(
                ImportIssue(
                    import_job_id=job.id,
                    staged_recipe_id=proposal.staged_recipe_id,
                    kind=ImportIssueKind.DUPLICATE_RECIPE,
                    severity=ImportIssueSeverity.WARNING,
                    details={
                        "powód": "AI uważa, że taki przepis już jest w aplikacji",
                        "przepis_id": proposal.recipe_id,
                        "przepis_nazwa": proposal.recipe_name,
                        "pewność": _fmt(proposal.confidence),
                    },
                )
            )

    def _store_servings_hints(self, issues: list[ImportIssue], suggestions: AiSuggestions) -> None:
        """Podpowiedź porcji trafia do `details` issue — NIGDY do `resolved_servings`."""
        by_recipe = {item.staged_recipe_id: item for item in suggestions.servings}
        for issue in issues:
            if issue.kind is not ImportIssueKind.MULTI_PORTION_SUSPECT:
                continue
            hint = by_recipe.get(issue.staged_recipe_id or 0)
            if hint is None:
                continue
            issue.details = {
                **issue.details,
                "propozycja_ai_porcje": hint.servings,
                "propozycja_ai_uzasadnienie": hint.rationale,
            }

    # --- approve: encje domenowe ---------------------------------------------------

    async def _create_pending_products(
        self, staged: list[StagedRecipe], *, actor: User
    ) -> list[int]:
        """Załóż produkty dla składników z `create_new_product` (UNVERIFIED, §4.9).

        Ta sama surowa nazwa w kilku daniach daje JEDEN produkt: kluczem jest
        `naming.normalize_name`, czyli dokładnie to, co UNIQUE w katalogu.
        Produkt, który w międzyczasie powstał (np. przez `ProductCreateDrawer`),
        zostaje użyty zamiast założenia duplikatu.
        """
        pending = [
            item
            for row in staged
            for item in row.ingredients
            if item.confirmed_product_id is None and item.create_new_product
        ]
        if not pending:
            return []

        category_id = await self._default_category_id()
        created: list[int] = []
        by_key: dict[str, int] = {}
        for item in pending:
            key = normalize_name(item.raw_name)
            product_id = by_key.get(key)
            if product_id is None:
                existing = await self._catalog.find_by_name(item.raw_name)
                if existing is not None:
                    product_id = existing.id
                else:
                    product = await self._catalog.create_product_pending(
                        actor=actor,
                        name=" ".join(item.raw_name.split()),
                        category_id=category_id,
                        measure_kind=MeasureKind.MASS,
                    )
                    product_id = product.id
                    created.append(product_id)
                by_key[key] = product_id
            item.confirmed_product_id = product_id
            item.create_new_product = False
        await self._session.flush()
        return created

    async def _default_category_id(self) -> int:
        category_id = (
            await self._session.execute(
                select(ProductCategory.id).where(
                    ProductCategory.name == DEFAULT_NEW_PRODUCT_CATEGORY
                )
            )
        ).scalar_one_or_none()
        if category_id is None:
            raise ConflictError(CATEGORY_MISSING)
        return int(category_id)

    async def _record_unit_weights(self, staged: list[StagedRecipe], *, actor: User) -> int:
        """Próbki przeliczników jednostek domowych z par ilość x jednostka x gramy.

        Bierzemy WYŁĄCZNIE wiersze, które niosą komplet pary (§3.2 wariant
        pełny i część zawiniętych) — dwa pozostałe warianty mają samą gramaturę
        i nie mówią nic o przeliczniku.
        """
        samples: dict[int, dict[str, list[Decimal]]] = {}
        for row in staged:
            for item in row.ingredients:
                if item.confirmed_product_id is None:
                    continue
                if item.raw_qty is None or not item.raw_unit or item.raw_qty <= 0:
                    continue
                label = canonical_unit_label(item.raw_unit)
                samples.setdefault(item.confirmed_product_id, {}).setdefault(label, []).append(
                    item.grams / item.raw_qty
                )

        touched = 0
        for product_id, per_label in samples.items():
            rows = await self._catalog.record_unit_weight_samples(
                product_id, actor=actor, samples=per_label, source=UNIT_WEIGHT_SOURCE
            )
            touched += len(rows)
        return touched

    # --- blokady -------------------------------------------------------------------

    async def _blockers(self, job: ImportJob, staged: list[StagedRecipe]) -> list[Blocker]:
        """Wszystko, co nie pozwala zatwierdzić joba (ADR-011: `blocker` blokuje)."""
        names = {row.id: row.name for row in staged}
        blockers: list[Blocker] = []
        for issue in await self._issues(job.id):
            if issue.severity is not ImportIssueSeverity.BLOCKER or issue.resolved_at is not None:
                continue
            blockers.append(
                Blocker(
                    staged_recipe_id=issue.staged_recipe_id,
                    recipe_name=names.get(issue.staged_recipe_id or 0, ""),
                    kind=issue.kind,
                    message=str(issue.details.get("powód", "")),
                )
            )
        return blockers

    # --- pomocnicze -----------------------------------------------------------------

    async def _reviewable_job(self, job_id: int, *, actor: User) -> ImportJob:
        job = await self._jobs.get_job(job_id, actor=actor)
        if job.status not in REVIEWABLE_STATUSES:
            raise ConflictError(JOB_NOT_REVIEWABLE)
        return job

    async def _staged_recipes(self, job_id: int) -> list[StagedRecipe]:
        """Dania joba w kolejności dokumentu, ze składnikami załadowanymi z góry."""
        rows = (
            (
                await self._session.execute(
                    select(StagedRecipe)
                    .where(StagedRecipe.import_job_id == job_id)
                    .options(selectinload(StagedRecipe.ingredients))
                    .order_by(StagedRecipe.id)
                )
            )
            .scalars()
            .unique()
            .all()
        )
        return list(rows)

    async def _issues(self, job_id: int) -> list[ImportIssue]:
        rows = (
            (
                await self._session.execute(
                    select(ImportIssue)
                    .where(ImportIssue.import_job_id == job_id)
                    .order_by(ImportIssue.id)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def _view(self, job: ImportJob) -> StagedJobView:
        staged = await self._staged_recipes(job.id)
        issues = await self._issues(job.id)
        nutrition = await self._meal_nutrition(staged)

        product_ids = {
            pid
            for row in staged
            for item in row.ingredients
            for pid in (item.suggested_product_id, item.confirmed_product_id)
            if pid is not None
        }
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

        by_recipe: dict[int, list[ImportIssue]] = {}
        job_issues: list[ImportIssue] = []
        for issue in issues:
            if issue.staged_recipe_id is None:
                job_issues.append(issue)
            else:
                by_recipe.setdefault(issue.staged_recipe_id, []).append(issue)

        views = [
            StagedRecipeView(
                recipe=row,
                ingredients=[
                    StagedIngredientView(
                        ingredient=item,
                        suggested_product=products.get(item.suggested_product_id or 0),
                        confirmed_product=products.get(item.confirmed_product_id or 0),
                    )
                    for item in row.ingredients
                ],
                issues=by_recipe.get(row.id, []),
                meal=nutrition[(row.day_label, row.meal_label)],
            )
            for row in staged
        ]
        return StagedJobView(
            job=job,
            recipes=views,
            job_issues=job_issues,
            blockers=await self._blockers(job, staged),
            ai_available=self._assistant.available,
        )

    def _safe_upload_path(self, relative: str) -> Path | None:
        """Ścieżka pliku joba, o ile na pewno leży w katalogu uploadów (wzór `service.py`)."""
        root = self._uploads_root.resolve()
        candidate = (root / relative).resolve()
        return candidate if candidate.is_relative_to(root) else None


# --- czyste funkcje pomocnicze -------------------------------------------------------


def _is_mapped(item: StagedIngredient) -> bool:
    """Czy składnik ma rozstrzygnięte mapowanie (potwierdzony produkt albo „załóż nowy")."""
    return item.confirmed_product_id is not None or item.create_new_product


def _servings_for(row: StagedRecipe) -> int:
    """Mianownik przepisu: rozstrzygnięcie człowieka > dokument > 1 (karta B16)."""
    return row.resolved_servings or row.declared_servings or 1


def _instructions_for(row: StagedRecipe) -> str:
    """Instrukcja przepisu razem z komentarzem dietetyczki, gdy jakiś jest."""
    parts = [row.instructions.strip(), row.comment.strip()]
    return "\n\n".join(part for part in parts if part)


def _imported_ingredients(row: StagedRecipe) -> list[ImportedIngredient]:
    """Składniki stagingu → wejście `RecipesService.create_imported_recipe`.

    Tu mieszka reguła 4 z nagłówka modułu: wiersz z sekcji `Produkty` jest
    podany NA PORCJĘ, więc do przepisu (który jest na całość) wchodzi
    przemnożony przez liczbę porcji.
    """
    servings = _servings_for(row)
    result: list[ImportedIngredient] = []
    for item in row.ingredients:
        if item.confirmed_product_id is None:
            continue
        grams = item.grams * servings if item.from_extras_section else item.grams
        result.append(
            ImportedIngredient(
                product_id=item.confirmed_product_id,
                grams=grams,
                display_qty=item.raw_qty,
                display_unit=item.raw_unit,
            )
        )
    return result


def _meal_result(
    dishes: list[StagedRecipe], products: dict[int, CanonicalProduct]
) -> MealNutrition:
    """Kalorie POSIŁKU na porcję vs `pdf_kcal` — albo powód, dla którego się nie da."""
    pdf_kcal = next((dish.pdf_kcal for dish in dishes if dish.pdf_kcal is not None), None)

    active = [dish for dish in dishes if dish.resolution is not StagedRecipeResolution.SKIP]
    if not active:
        return MealNutrition(None, pdf_kcal, None, "Wszystkie dania posiłku są pominięte.")
    if any(not _is_mapped(item) for dish in active for item in dish.ingredients):
        return MealNutrition(None, pdf_kcal, None, "Nie wszystkie składniki mają wskazany produkt.")

    values: list[NutritionValues] = []
    for dish in active:
        servings = Decimal(_servings_for(dish))
        for item in dish.ingredients:
            if item.confirmed_product_id is None:
                # Składnik czeka na założenie produktu przy zatwierdzeniu —
                # nie ma jeszcze czego zapytać o kalorie.
                return MealNutrition(
                    None,
                    pdf_kcal,
                    None,
                    "Nie można zweryfikować — produkty powstaną dopiero przy "
                    "zatwierdzeniu importu.",
                )
            product = products.get(item.confirmed_product_id)
            if product is None or product.kcal_100 is None:
                return MealNutrition(
                    None,
                    pdf_kcal,
                    None,
                    "Nie można zweryfikować — produkty bez wartości odżywczych.",
                )
            per_portion = item.grams if item.from_extras_section else item.grams / servings
            # Konwersję robi JEDYNE do tego uprawnione miejsce (CLAUDE.md §4),
            # nawet jeśli dla gramów jest tożsamościowa: dzięki temu produkt
            # liczony na 100 ml dostanie tu wyjątek, a nie cichy błąd o dwa
            # rzędy wielkości. Przeliczników domowych nie podajemy — gramatura
            # z jadłospisu jest już w gramach.
            measure = measure_for(product, [])
            try:
                basis = to_basis_amount(normalize_amount(per_portion, "g", measure), measure)
            except UnitConversionError:
                return MealNutrition(
                    None,
                    pdf_kcal,
                    None,
                    "Nie można zweryfikować — gramatury z jadłospisu nie da się "
                    "przeliczyć na jednostkę produktu.",
                )
            values.append(ingredient_nutrition(basis, nutrition_for(product)))

    computed = round_for_output(aggregate(values) if values else ZERO_VALUES).kcal
    if pdf_kcal is None or pdf_kcal <= 0:
        return MealNutrition(computed, pdf_kcal, None, "Jadłospis nie podaje kalorii posiłku.")
    delta = (computed - pdf_kcal) / pdf_kcal * 100
    return MealNutrition(computed, pdf_kcal, delta.quantize(_PCT_QUANTUM))


def _fmt(value: Decimal | None) -> str | None:
    """Decimal do JSON-a issue jako STRING dziesiętny (ADR-008)."""
    return None if value is None else format(value, "f")


def _blocker_payload(blocker: Blocker) -> dict[str, object]:
    """Kształt jednej blokady w `details` odpowiedzi 409."""
    return {
        "staged_recipe_id": blocker.staged_recipe_id,
        "recipe_name": blocker.recipe_name,
        "kind": blocker.kind.value,
        "message": blocker.message,
    }
