"""Serwis importera: upload PDF-a, ekstrakcja, staging i sugestie EXACT.

Jedyne miejsce I/O modułu (wzorzec ADR-001): plik na dysku, pdfplumber i baza.
Reguły struktury dokumentu mieszkają obok, w czystym `parser.py`, a mapowanie
nazw w `matching.py`.

Cztery własności, na których stoi ten moduł:

1. **Parsowanie jest SYNCHRONICZNE względem żądania uploadu** (karta B15):
   8—10 stron to sekundy, a własna kolejka zadań łamałaby ADR-001. Ciężką
   pracę (pdfplumber) wypycha `run_in_threadpool`, więc pętla zdarzeń stoi
   wolna; całość jest ograniczona `PDF_PARSE_TIMEOUT_S`.
2. **Błąd parsowania NIE jest błędem żądania.** Job dostaje status `failed`
   z komunikatem po polsku, plik zostaje na dysku do diagnozy, a użytkownik
   widzi to na liście — zamiast 500 bez śladu (Acceptance Criterion 1).
3. **Nic nie trafia do danych aplikacji** (niezmiennik 02_DOMAIN §13.6):
   zapisujemy WYŁĄCZNIE cztery tabele stagingu. Produkty kanoniczne są tu
   czytane, nigdy tworzone — zakładanie brakujących to decyzja review (B16).
4. **Job należy do osoby, nie do rodziny.** Dieta to dane zdrowotne pacjenta,
   więc widoczność jest właścicielska (`owner_user_id`), z wyjątkiem ADMIN-a
   zgodnym z D16. Cudzy job to 404, nie 403 (07_SECURITY §4).
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from sqlalchemy import ColumnElement, func, select, true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.deletion import USED_IN_LIMIT, UsedInRef
from app.core.errors import ConflictError, NotFoundError
from app.core.uploads import InvalidUploadError, UploadTooLargeError
from app.modules.accounts.models import User, UserRole
from app.modules.audit.service import AuditAction, AuditEntity, AuditService
from app.modules.catalog.models import CanonicalProduct
from app.modules.catalog.service import register_product_reference_finder
from app.modules.importer.matching import exact_matches, normalized_keys
from app.modules.importer.models import (
    ImportIssue,
    ImportIssueKind,
    ImportIssueSeverity,
    ImportJob,
    ImportJobStatus,
    MatchKind,
    StagedIngredient,
    StagedRecipe,
)
from app.modules.importer.parser import ParsedDocument, build_parse_report, parse_document
from app.modules.recipes.service import register_recipe_reference_finder

__all__ = [
    "DELETABLE_STATUSES",
    "IMPORT_PDF_SUBDIR",
    "PDF_PARSE_TIMEOUT_S",
    "ImporterService",
]

#: Podkatalog uploadów na wgrane PDF-y. Jest w `core.uploads.PRIVATE_SUBDIRS`:
#: `/uploads/{path}` sprawdza WYŁĄCZNIE sesję, a jadłospis to dane zdrowotne
#: jednej osoby — bez tej bariery wystarczyłaby znajomość ścieżki (ustalenie
#: review BATCH_14, przeniesione tu wprost).
IMPORT_PDF_SUBDIR = "import-pdf"

#: Sufit czasu na ekstrakcję i parsowanie jednego pliku (07_SECURITY §6).
#: UWAGA: przerywa ŻĄDANIE, nie sam wątek — CPU-bound kod w Pythonie nie da się
#: zabić z zewnątrz. Job dostaje wtedy `failed`, a wątek dobiega końca sam.
PDF_PARSE_TIMEOUT_S = 60.0

#: Statusy, w których job wolno usunąć (karta B15 §Backend). `approved`
#: i `rejected` są historią decyzji — te zostają.
DELETABLE_STATUSES = (
    ImportJobStatus.UPLOADED,
    ImportJobStatus.PARSED,
    ImportJobStatus.FAILED,
)

JOB_NOT_FOUND = "Nie znaleziono importu."
NOT_A_PDF = "Przesłany plik nie jest dokumentem PDF."
TOO_LARGE = "Plik jest za duży — PDF może mieć najwyżej {limit} MB."
PARSE_FAILED = (
    "Nie udało się odczytać tego PDF-a. Plik został zapisany — sprawdź, czy to "
    "jadłospis w formacie, który obsługujemy."
)
PARSE_TIMEOUT = "Odczyt pliku trwał zbyt długo i został przerwany."
DUPLICATE_UPLOAD = "Ten sam plik był już wgrywany wcześniej (import {job_id})."
JOB_NOT_DELETABLE = (
    "Tego importu nie można usunąć — jest już rozstrzygnięty. Usuwać wolno "
    "wyłącznie importy wgrane, sparsowane i zakończone błędem."
)

#: Sygnatura PDF-a sprawdzana PO TREŚCI, nie po rozszerzeniu ani MIME (§6).
_PDF_MAGIC = b"%PDF"


@dataclass(frozen=True)
class _StagingCounts:
    """Liczby potrzebne raportowi — zbierane przy zapisie, nie liczone dwa razy."""

    exact: int
    none: int
    blocker: int
    warning: int


class ImporterService:
    """Upload PDF-a → job → staging (02_DOMAIN §10, ADR-011)."""

    def __init__(self, session: AsyncSession, *, uploads_dir: str, max_pdf_mb: int) -> None:
        self._session = session
        self._audit = AuditService(session)
        self._uploads_root = Path(uploads_dir)
        self._max_pdf_mb = max_pdf_mb

    @property
    def max_pdf_bytes(self) -> int:
        """Limit uploadu w bajtach — router czyta z sufitem `limit + 1`."""
        return self._max_pdf_mb * 1024 * 1024

    # --- widoczność ------------------------------------------------------------

    def _visible_condition(self, actor: User) -> ColumnElement[bool]:
        """Job widzi jego właściciel; ADMIN widzi wszystkie (D16).

        `ScopedQuery` tu nie pasuje i nie ma pasować: wymaga kolumn `scope`
        i `household_id`, których staging nie ma (03_DATABASE §9) — dieta jednej
        osoby nie jest stanem domowym. Wzorzec jest ten sam, co dla celów
        żywieniowych (`nutrition/service.py`): jawny warunek właścicielski
        w serwisie encji, która świadomie stoi poza wzorcem scope.
        """
        if actor.role is UserRole.ADMIN:
            return true()
        return ImportJob.owner_user_id == actor.id

    async def get_job(self, job_id: int, *, actor: User) -> ImportJob:
        """Job po id — cudzy albo nieistniejący kończy się identycznym 404."""
        job = (
            await self._session.execute(
                select(ImportJob).where(ImportJob.id == job_id, self._visible_condition(actor))
            )
        ).scalar_one_or_none()
        if job is None:
            raise NotFoundError(JOB_NOT_FOUND)
        return job

    async def list_jobs(
        self, *, actor: User, limit: int, offset: int
    ) -> tuple[list[ImportJob], int]:
        """Joby użytkownika, najnowsze pierwsze."""
        statement = select(ImportJob).where(self._visible_condition(actor))
        total = (
            await self._session.execute(select(func.count()).select_from(statement.subquery()))
        ).scalar_one()
        rows = (
            (
                await self._session.execute(
                    statement.order_by(ImportJob.created_at.desc(), ImportJob.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    # --- upload i parsowanie ---------------------------------------------------

    async def upload(self, *, actor: User, filename: str, data: bytes) -> ImportJob:
        """Zapisz PDF, sparsuj go i zbuduj staging. Jeden commit na końcu.

        Kolejność jest częścią kontraktu bezpieczeństwa (07_SECURITY §6): limit
        rozmiaru PRZED czymkolwiek, sygnatura treści PRZED zapisem, a na dysk
        trafia plik pod LOSOWĄ nazwą, poza web-rootem.
        """
        if len(data) > self.max_pdf_bytes:
            raise UploadTooLargeError(TOO_LARGE.format(limit=self._max_pdf_mb))
        if not data.startswith(_PDF_MAGIC):
            raise InvalidUploadError(NOT_A_PDF)

        digest = hashlib.sha256(data).hexdigest()
        duplicate_of = await self._previous_upload(digest, actor=actor)

        relative = await run_in_threadpool(self._write_pdf, data)
        job = ImportJob(
            owner_user_id=actor.id,
            filename=filename,
            file_path=relative,
            file_sha256=digest,
            status=ImportJobStatus.UPLOADED,
        )
        self._session.add(job)
        await self._session.flush()

        warnings: list[str] = []
        if duplicate_of is not None:
            # Deduplikacja jest INFORMACYJNA (karta §Security): ten sam
            # jadłospis wolno wgrać drugi raz, np. po usunięciu poprzedniego joba.
            warnings.append(DUPLICATE_UPLOAD.format(job_id=duplicate_of))

        try:
            document = await asyncio.wait_for(
                run_in_threadpool(self._extract_and_parse, relative),
                timeout=PDF_PARSE_TIMEOUT_S,
            )
        except TimeoutError:
            return await self._fail(job, PARSE_TIMEOUT, actor=actor)
        except Exception:  # każdy błąd biblioteki to `failed`, nie 500 (AC 1)
            return await self._fail(job, PARSE_FAILED, actor=actor)

        counts = await self._store_staging(job, document)
        job.parse_report = build_parse_report(
            document,
            match_counts={"exact": counts.exact, "none": counts.none},
            issue_counts={"blocker": counts.blocker, "warning": counts.warning},
            warnings=warnings,
        )
        job.status = ImportJobStatus.PARSED
        self._audit.record(
            action=AuditAction.IMPORT_UPLOAD,
            entity_type=AuditEntity.IMPORT_JOB,
            entity_id=job.id,
            actor_id=actor.id,
            # Wyłącznie liczby i status — nigdy treść jadłospisu (07_SECURITY §8).
            payload={
                "status": job.status.value,
                "staged_recipes": len(document.dishes),
                "ingredients": sum(len(dish.ingredients) for dish in document.dishes),
                "blockers": counts.blocker,
                "warnings": counts.warning,
            },
        )
        await self._session.commit()
        await self._session.refresh(job)
        return job

    async def _previous_upload(self, digest: str, *, actor: User) -> int | None:
        """Id wcześniejszego joba tego samego użytkownika o tej samej treści."""
        return (
            await self._session.execute(
                select(ImportJob.id)
                .where(
                    ImportJob.file_sha256 == digest,
                    ImportJob.owner_user_id == actor.id,
                )
                .order_by(ImportJob.id)
                .limit(1)
            )
        ).scalar_one_or_none()

    async def _fail(self, job: ImportJob, message: str, *, actor: User) -> ImportJob:
        """Zamknij joba statusem `failed`; plik ZOSTAJE na dysku do diagnozy."""
        job.status = ImportJobStatus.FAILED
        job.error = message
        self._audit.record(
            action=AuditAction.IMPORT_UPLOAD,
            entity_type=AuditEntity.IMPORT_JOB,
            entity_id=job.id,
            actor_id=actor.id,
            payload={"status": job.status.value},
        )
        await self._session.commit()
        await self._session.refresh(job)
        return job

    def _write_pdf(self, data: bytes) -> str:
        """Zapisz plik pod losową nazwą; zwróć ścieżkę WZGLĘDNĄ do bazy."""
        target_dir = self._uploads_root / IMPORT_PDF_SUBDIR
        target_dir.mkdir(parents=True, exist_ok=True)
        name = f"{uuid4().hex}.pdf"
        (target_dir / name).write_bytes(data)
        return f"{IMPORT_PDF_SUBDIR}/{name}"

    def _extract_and_parse(self, relative: str) -> ParsedDocument:
        """pdfplumber → teksty stron → `parse_document`. Synchronicznie (threadpool).

        Import biblioteki jest lokalny: `pdfplumber` ciągnie pdfminer, a start
        aplikacji nie ma powodu płacić za to sekundy, skoro poza importem PDF-a
        nikt go nie potrzebuje.
        """
        import pdfplumber

        path = self._uploads_root / relative
        with pdfplumber.open(path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return parse_document(pages)

    # --- staging ---------------------------------------------------------------

    async def _store_staging(self, job: ImportJob, document: ParsedDocument) -> _StagingCounts:
        """Zapisz dania, składniki i issues; dolicz sugestie EXACT."""
        catalog_index = await self._catalog_index(document)

        staged: list[StagedRecipe] = []
        exact = none = 0
        for day in document.days:
            for meal in day.meals:
                for dish in meal.dishes:
                    recipe = StagedRecipe(
                        import_job_id=job.id,
                        name=dish.name,
                        day_label=day.label,
                        meal_label=meal.label,
                        instructions=dish.instructions,
                        comment=dish.comment,
                        declared_servings=dish.declared_servings,
                        pdf_kcal=meal.pdf_kcal,
                        pdf_macros=dict(meal.pdf_macros),
                    )
                    self._session.add(recipe)
                    staged.append(recipe)

                    matches = exact_matches(
                        (item.raw_name for item in dish.ingredients),
                        catalog_index=catalog_index,
                    )
                    for item in dish.ingredients:
                        product_id = matches.get(item.raw_name)
                        if product_id is None:
                            none += 1
                        else:
                            exact += 1
                        recipe.ingredients.append(
                            StagedIngredient(
                                raw_name=item.raw_name,
                                raw_qty=item.raw_qty,
                                raw_unit=item.raw_unit,
                                grams=item.grams,
                                from_extras_section=item.from_extras_section,
                                suggested_product_id=product_id,
                                match_kind=(
                                    MatchKind.NONE if product_id is None else MatchKind.EXACT
                                ),
                            )
                        )
        # Bez `flush` wiersze issues nie miałyby czego wskazać: `dish_index`
        # z parsera zamienia się na `staged_recipe_id` dopiero po nadaniu id.
        await self._session.flush()

        blocker = warning = 0
        for finding in document.findings:
            staged_recipe_id = (
                staged[finding.dish_index].id
                if finding.dish_index is not None and finding.dish_index < len(staged)
                else None
            )
            severity = ImportIssueSeverity(finding.severity.value)
            if severity is ImportIssueSeverity.BLOCKER:
                blocker += 1
            else:
                warning += 1
            self._session.add(
                ImportIssue(
                    import_job_id=job.id,
                    staged_recipe_id=staged_recipe_id,
                    kind=ImportIssueKind(finding.kind.value),
                    severity=severity,
                    details={
                        **finding.details,
                        "dzień": finding.day_label,
                        "posiłek": finding.meal_label,
                    },
                )
            )
        return _StagingCounts(exact=exact, none=none, blocker=blocker, warning=warning)

    async def _catalog_index(self, document: ParsedDocument) -> dict[str, int]:
        """`{normalized_name: id}` dla nazw występujących w dokumencie.

        Produkty ZARCHIWIZOWANE też wchodzą do indeksu. To nie przeoczenie:
        `normalized_name` jest unikalny globalnie, więc pominięcie archiwalnego
        wiersza dałoby `match_kind=none`, a review (B16) próbowałoby założyć
        produkt, który natychmiast padłby na UNIQUE. Decyzję „odarchiwizować czy
        wskazać inny produkt" podejmuje człowiek, mając sugestię przed oczami.
        """
        keys = normalized_keys(
            item.raw_name for dish in document.dishes for item in dish.ingredients
        )
        if not keys:
            return {}
        rows = (
            await self._session.execute(
                select(CanonicalProduct.normalized_name, CanonicalProduct.id).where(
                    CanonicalProduct.normalized_name.in_(keys)
                )
            )
        ).all()
        return {str(row[0]): int(row[1]) for row in rows}

    # --- usuwanie --------------------------------------------------------------

    async def delete_job(self, job_id: int, *, actor: User) -> None:
        """Usuń joba razem z całym stagingiem i plikiem na dysku.

        Kolejność jest celowa: najpierw commit bazy, potem plik. Odwrotna
        zostawiałaby po nieudanym commicie joba wskazującego w pustkę, a plik
        osierocony przez błąd kasowania jest problemem sprzątania, nie spójności.
        """
        job = await self.get_job(job_id, actor=actor)
        if job.status not in DELETABLE_STATUSES:
            raise ConflictError(JOB_NOT_DELETABLE)

        # Ścieżkę i status czytamy PRZED `delete()`: po nim instancja jest
        # w stanie „do skasowania" i poleganie na jej atrybutach jest kruche.
        status = job.status.value
        path = self._safe_upload_path(job.file_path)
        await self._session.delete(job)
        self._audit.record(
            action=AuditAction.IMPORT_DELETE,
            entity_type=AuditEntity.IMPORT_JOB,
            entity_id=job_id,
            actor_id=actor.id,
            payload={"status": status},
        )
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(JOB_NOT_DELETABLE) from exc
        if path is not None:
            await run_in_threadpool(path.unlink, missing_ok=True)

    def _safe_upload_path(self, relative: str) -> Path | None:
        """Ścieżka pliku joba, o ile na pewno leży w katalogu uploadów.

        `file_path` pisze wyłącznie `_write_pdf` (uuid4 pod stałym podkatalogiem),
        więc w praktyce zawsze jest bezpieczna. Kontrola i tak zostaje: to jedyne
        miejsce w module, które KASUJE plik, a wiersz z popsutą ścieżką (ręczna
        edycja bazy, import z innej instalacji) nie ma prawa skasować niczego
        poza katalogiem uploadów. `None` = nie ruszamy dysku.
        """
        root = self._uploads_root.resolve()
        candidate = (root / relative).resolve()
        return candidate if candidate.is_relative_to(root) else None


async def _staging_using_product(session: AsyncSession, product_id: int) -> list[UsedInRef]:
    """Dania stagingu, które wskazują ten produkt (sugestia albo potwierdzenie).

    Bez tego licznika ADMIN kasujący produkt dostałby 409 z PUSTĄ listą „Używane
    w:" — FK ma RESTRICT, więc baza i tak by nie pozwoliła (R3, dług U16).
    """
    rows = (
        await session.execute(
            select(StagedRecipe.id, StagedRecipe.name)
            .join(StagedIngredient, StagedIngredient.staged_recipe_id == StagedRecipe.id)
            .where(
                (StagedIngredient.suggested_product_id == product_id)
                | (StagedIngredient.confirmed_product_id == product_id)
            )
            .order_by(StagedRecipe.name, StagedRecipe.id)
            .distinct()
            .limit(USED_IN_LIMIT)
        )
    ).all()
    return [UsedInRef(type="staged_recipe", id=int(row[0]), name=str(row[1])) for row in rows]


async def _staging_using_recipe(session: AsyncSession, recipe_id: int) -> list[UsedInRef]:
    """Dania stagingu wskazane do scalenia z tym przepisem (`target_recipe_id`, B16)."""
    rows = (
        await session.execute(
            select(StagedRecipe.id, StagedRecipe.name)
            .where(StagedRecipe.target_recipe_id == recipe_id)
            .order_by(StagedRecipe.name, StagedRecipe.id)
            .limit(USED_IN_LIMIT)
        )
    ).all()
    return [UsedInRef(type="staged_recipe", id=int(row[0]), name=str(row[1])) for row in rows]


# Rejestracja przy imporcie modułu — każdy proces budujący aplikację
# (create_app → deps → ImporterService) ma liczniki wpięte automatycznie.
register_product_reference_finder(_staging_using_product)
register_recipe_reference_finder(_staging_using_recipe)
