"""Kontrakt HTTP `/import` — macierz uprawnień i niezmienniki importu (08_TESTING §4).

Cztery rzeczy, które ten plik pilnuje na poziomie HTTP:

1. macierz ról: anonim bez dostępu, cudzy job 404 (nie 403), ADMIN widzi wszystkie (D16),
2. sniffing i limit: plik niebędący PDF-em to 422, ponad limit to 413 — jedno
   i drugie po TREŚCI/rozmiarze, nigdy po nazwie,
3. **niezmiennik 02_DOMAIN §13.6**: po uploadzie i sparsowaniu w encjach
   domenowych nie przybywa ANI JEDEN wiersz,
4. mutacja bez nagłówka CSRF to 403, tak jak w każdym innym module.

Do uploadu idzie prawdziwy `dieta.pdf` z korpusu: test API sprawdza kontrakt
HTTP, ale wynik ma być tym samym, co w testach korpusowych — atrapa PDF-a
przetestowałaby wyłącznie ścieżkę błędu.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.modules.audit.models import AuditEntry
from app.modules.catalog.models import CanonicalProduct
from app.modules.importer.models import ImportIssue, ImportJob, StagedIngredient, StagedRecipe
from app.modules.recipes.models import Recipe, RecipeIngredient
from tests.factories import create_admin, create_category, create_product, create_user
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

IMPORT_PDF = f"{API}/import/pdf"
IMPORT_JOBS = f"{API}/import/jobs"

CORPUS_DIR = Path(__file__).resolve().parents[3] / "data" / "source_pdfs"


@pytest.fixture
def uploads_root() -> Path:
    """Katalog uploadów procesu testowego (`conftest` kieruje go do temp)."""
    return Path(get_settings().uploads_dir)


def _diet_pdf() -> bytes:
    """Realny plik korpusu — ten sam, na którym stoją testy korpusowe."""
    return (CORPUS_DIR / "dieta.pdf").read_bytes()


def _upload(content: bytes, *, filename: str = "dieta.pdf") -> dict[str, tuple[str, bytes, str]]:
    """Część multipart w kształcie, którego oczekuje httpx (nazwa, treść, MIME)."""
    return {"file": (filename, content, "application/pdf")}


async def _domain_counts(session: AsyncSession) -> dict[str, int]:
    """Liczniki encji DOMENOWYCH — import nie ma prawa ich ruszyć (§13.6)."""
    counts = {}
    for label, model in (
        ("recipes", Recipe),
        ("recipe_ingredients", RecipeIngredient),
        ("products", CanonicalProduct),
    ):
        counts[label] = int(
            (await session.execute(select(func.count()).select_from(model))).scalar_one()
        )
    return counts


# --- macierz uprawnień ------------------------------------------------------------


async def test_anonim_nie_wgra_pliku(client: AsyncClient) -> None:
    """Anonimowy upload jest odrzucany, zanim dojdzie do warstwy sesji.

    Middleware CSRF działa przed routingiem, a bez cookie nie ma z czym
    porównać nagłówka (07_SECURITY §3) — kontraktem dla anonimowej MUTACJI
    jest więc 403. Brak sesji jako 401 dowodzi obok
    `test_anonim_nie_zobaczy_listy_jobow` (odczyt).
    """
    response = await client.post(IMPORT_PDF, files=_upload(b"%PDF-1.4 cokolwiek"))

    assert response.status_code == 403


async def test_anonim_nie_zobaczy_listy_jobow(client: AsyncClient) -> None:
    """Lista importów też wymaga sesji."""
    assert (await client.get(IMPORT_JOBS)).status_code == 401


async def test_upload_bez_naglowka_csrf_konczy_sie_403(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Mutacja bez `X-CSRF-Token` to 403 — jednakowo w całej aplikacji."""
    user = await create_user(db_session, email="uploader@example.com")
    await login(db_client, user.email)

    response = await db_client.post(IMPORT_PDF, files=_upload(_diet_pdf()))

    assert response.status_code == 403
    assert db_client.cookies[CSRF_COOKIE_NAME]


async def test_cudzy_job_daje_404_a_nie_403(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Anty-IDOR: cudzy import jest nie do odróżnienia od nieistniejącego."""
    owner = await create_user(db_session, email="wlasciciel@example.com")
    intruder = await create_user(db_session, email="obcy@example.com")
    job = ImportJob(
        owner_user_id=owner.id,
        filename="cudza-dieta.pdf",
        file_path="import-pdf/nieistotne.pdf",
        file_sha256="0" * 64,
    )
    db_session.add(job)
    await db_session.commit()

    await login(db_client, intruder.email)
    response = await db_client.get(f"{IMPORT_JOBS}/{job.id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_cudzy_job_nie_wchodzi_na_liste(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Lista pokazuje wyłącznie własne importy."""
    owner = await create_user(db_session, email="wlasciciel2@example.com")
    intruder = await create_user(db_session, email="obcy2@example.com")
    db_session.add(
        ImportJob(
            owner_user_id=owner.id,
            filename="cudza.pdf",
            file_path="import-pdf/x.pdf",
            file_sha256="1" * 64,
        )
    )
    await db_session.commit()

    await login(db_client, intruder.email)
    body = (await db_client.get(IMPORT_JOBS)).json()

    assert body == {"items": [], "total": 0}


async def test_admin_widzi_cudzy_job(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """D16: ADMIN widzi encje scope'owane i właścicielskie na ścieżkach użytkownika."""
    owner = await create_user(db_session, email="wlasciciel3@example.com")
    admin = await create_admin(db_session, email="admin-import@example.com")
    job = ImportJob(
        owner_user_id=owner.id,
        filename="cudza3.pdf",
        file_path="import-pdf/y.pdf",
        file_sha256="2" * 64,
    )
    db_session.add(job)
    await db_session.commit()

    await login(db_client, admin.email)
    response = await db_client.get(f"{IMPORT_JOBS}/{job.id}")

    assert response.status_code == 200
    assert response.json()["filename"] == "cudza3.pdf"


# --- upload: sniffing i limit ------------------------------------------------------


async def test_plik_bez_sygnatury_pdf_konczy_sie_422(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Sniffing po TREŚCI: `.pdf` w nazwie i `application/pdf` w MIME nie wystarczą."""
    user = await create_user(db_session, email="sniffing@example.com")
    await login(db_client, user.email)

    response = await db_client.post(
        IMPORT_PDF,
        files=_upload(b"To jest zwykly tekst, nie PDF.", filename="udaje.pdf"),
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_plik_ponad_limit_konczy_sie_413(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Limit 25 MB z 07_SECURITY §6 — komunikat mówi, jaki limit obowiązuje."""
    user = await create_user(db_session, email="limit@example.com")
    await login(db_client, user.email)
    oversized = b"%PDF-1.4" + b"0" * (25 * 1024 * 1024)

    response = await db_client.post(
        IMPORT_PDF, files=_upload(oversized), headers=csrf_headers(db_client)
    )

    assert response.status_code == 413
    assert "25 MB" in response.json()["error"]["message"]


async def test_uszkodzony_pdf_daje_status_failed_a_nie_500(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Acceptance Criterion 1: błąd parsowania jest STANEM joba, nie awarią żądania."""
    user = await create_user(db_session, email="uszkodzony@example.com")
    await login(db_client, user.email)

    response = await db_client.post(
        IMPORT_PDF,
        files=_upload(b"%PDF-1.4\nto nie jest poprawna struktura pliku"),
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]
    assert body["parse_report"] is None


# --- happy path --------------------------------------------------------------------


async def test_upload_dieta_pdf_tworzy_job_ze_staginigiem(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Realny plik: 12 posiłków, 13 dań, raport z sumami kontrolnymi (01_PDF_AUDIT §1)."""
    user = await create_user(db_session, email="happy@example.com")
    await login(db_client, user.email)

    response = await db_client.post(
        IMPORT_PDF, files=_upload(_diet_pdf()), headers=csrf_headers(db_client)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "parsed"
    assert body["filename"] == "dieta.pdf"
    report = body["parse_report"]
    assert report["pages"] == {
        "total": 10,
        "days": 5,
        "skipped_shopping": 2,
        "skipped_exchanges": 1,
    }
    assert report["days"] == 3
    assert report["meals"] == 12
    assert report["staged_recipes"] == 13
    assert report["ingredients"] == 85
    assert [checksum["ok"] for checksum in report["day_checksums"]] == [True, True, True]
    # Gołąbki są oznaczone „na 7 porcji", więc w tym pliku nie ma blockerów.
    assert report["issues"] == {"blocker": 0, "warning": 0}

    staged = int(
        (
            await db_session.execute(
                select(func.count())
                .select_from(StagedRecipe)
                .where(StagedRecipe.import_job_id == body["id"])
            )
        ).scalar_one()
    )
    assert staged == 13


async def test_parsowanie_nie_tworzy_zadnej_encji_domenowej(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Niezmiennik 02_DOMAIN §13.6 — import nic nie zapisuje przed APPROVED."""
    user = await create_user(db_session, email="niezmiennik@example.com")
    category = await create_category(db_session, name="Warzywa importowe")
    await create_product(db_session, category=category, name="Cebula")
    await login(db_client, user.email)
    before = await _domain_counts(db_session)

    response = await db_client.post(
        IMPORT_PDF, files=_upload(_diet_pdf()), headers=csrf_headers(db_client)
    )
    assert response.status_code == 201

    assert await _domain_counts(db_session) == before


async def test_skladnik_o_znanej_nazwie_dostaje_sugestie_exact(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Mapowanie EXACT po `normalized_name`; reszta zostaje `none` (zero AI)."""
    user = await create_user(db_session, email="mapowanie@example.com")
    category = await create_category(db_session, name="Warzywa mapowane")
    cebula = await create_product(db_session, category=category, name="Cebula")
    await login(db_client, user.email)

    body = (
        await db_client.post(
            IMPORT_PDF, files=_upload(_diet_pdf()), headers=csrf_headers(db_client)
        )
    ).json()

    assert body["parse_report"]["match"]["exact"] > 0
    matched = (
        await db_session.execute(
            select(StagedIngredient.raw_name, StagedIngredient.match_kind).where(
                StagedIngredient.suggested_product_id == cebula.id
            )
        )
    ).all()
    assert matched
    assert {row[0] for row in matched} == {"Cebula"}
    assert {row[1].value for row in matched} == {"exact"}

    unmatched = int(
        (
            await db_session.execute(
                select(func.count())
                .select_from(StagedIngredient)
                .where(StagedIngredient.suggested_product_id.is_(None))
            )
        ).scalar_one()
    )
    assert unmatched == body["parse_report"]["match"]["none"]


async def test_upload_zostawia_wpis_w_dzienniku_bez_tresci_jadlospisu(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """07_SECURITY §8: payload audytu niesie liczby, nigdy nazwy dań ani produktów."""
    user = await create_user(db_session, email="audyt@example.com")
    await login(db_client, user.email)

    await db_client.post(IMPORT_PDF, files=_upload(_diet_pdf()), headers=csrf_headers(db_client))

    entry = (
        await db_session.execute(select(AuditEntry).where(AuditEntry.action == "import_job.upload"))
    ).scalar_one()
    assert entry.entity_type == "import_job"
    assert set(entry.payload) == {
        "status",
        "staged_recipes",
        "ingredients",
        "blockers",
        "warnings",
    }


async def test_ten_sam_plik_drugi_raz_jest_ostrzezeniem_a_nie_bledem(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Deduplikacja po sha256 jest INFORMACYJNA (karta §Security)."""
    user = await create_user(db_session, email="duplikat@example.com")
    await login(db_client, user.email)
    content = _diet_pdf()

    first = await db_client.post(
        IMPORT_PDF, files=_upload(content), headers=csrf_headers(db_client)
    )
    second = await db_client.post(
        IMPORT_PDF, files=_upload(content), headers=csrf_headers(db_client)
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["status"] == "parsed"
    warnings = second.json()["parse_report"]["warnings"]
    assert len(warnings) == 1
    assert str(first.json()["id"]) in warnings[0]


# --- usuwanie ----------------------------------------------------------------------


async def test_delete_kasuje_staging_i_plik(
    db_client: AsyncClient, db_session: AsyncSession, uploads_root: Path
) -> None:
    """Usunięcie joba zabiera dania, składniki, issues i plik z dysku."""
    user = await create_user(db_session, email="kasowanie@example.com")
    await login(db_client, user.email)
    job = (
        await db_client.post(
            IMPORT_PDF, files=_upload(_diet_pdf()), headers=csrf_headers(db_client)
        )
    ).json()
    stored = (
        await db_session.execute(select(ImportJob.file_path).where(ImportJob.id == job["id"]))
    ).scalar_one()
    assert (uploads_root / stored).is_file()

    response = await db_client.delete(f"{IMPORT_JOBS}/{job['id']}", headers=csrf_headers(db_client))

    assert response.status_code == 204
    assert not (uploads_root / stored).exists()
    for model in (ImportJob, StagedRecipe, StagedIngredient, ImportIssue):
        remaining = int(
            (await db_session.execute(select(func.count()).select_from(model))).scalar_one()
        )
        assert remaining == 0, f"{model.__tablename__} przetrwało usunięcie joba"


async def test_delete_nie_kasuje_pliku_spoza_katalogu_uploadow(
    db_client: AsyncClient, db_session: AsyncSession, uploads_root: Path, tmp_path: Path
) -> None:
    """Wiersz z popsutą `file_path` usuwa się z bazy, ale nie rusza cudzego pliku.

    `file_path` pisze wyłącznie serwis (uuid4 pod `import-pdf/`), więc to obrona
    przed sytuacją, której normalnie nie ma: ręczną edycją bazy albo importem
    z innej instalacji. Kasowanie plików to operacja nieodwracalna — kontrola
    zasięgu kosztuje jedną linijkę.
    """
    outsider = tmp_path / "nie-nasz.pdf"
    outsider.write_bytes(b"%PDF-1.4 cudzy plik")
    user = await create_user(db_session, email="sciezka@example.com")
    job = ImportJob(
        owner_user_id=user.id,
        filename="podejrzana.pdf",
        file_path=f"../../{outsider.name}",
        file_sha256="5" * 64,
    )
    db_session.add(job)
    await db_session.commit()

    await login(db_client, user.email)
    response = await db_client.delete(f"{IMPORT_JOBS}/{job.id}", headers=csrf_headers(db_client))

    assert response.status_code == 204
    assert outsider.is_file(), "usunięcie joba skasowało plik spoza katalogu uploadów"
    assert uploads_root.is_dir()


async def test_delete_cudzego_joba_daje_404(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Ta sama granica, co przy odczycie — cudzy zasób nie istnieje."""
    owner = await create_user(db_session, email="wlasciciel4@example.com")
    intruder = await create_user(db_session, email="obcy4@example.com")
    job = ImportJob(
        owner_user_id=owner.id,
        filename="cudza4.pdf",
        file_path="import-pdf/z.pdf",
        file_sha256="3" * 64,
    )
    db_session.add(job)
    await db_session.commit()

    await login(db_client, intruder.email)
    response = await db_client.delete(f"{IMPORT_JOBS}/{job.id}", headers=csrf_headers(db_client))

    assert response.status_code == 404


async def test_zatwierdzonego_joba_nie_da_sie_usunac(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`approved` to historia decyzji — usuwać wolno tylko wgrane/sparsowane/błędne."""
    from app.modules.importer.models import ImportJobStatus

    user = await create_user(db_session, email="zatwierdzony@example.com")
    job = ImportJob(
        owner_user_id=user.id,
        filename="zatwierdzona.pdf",
        file_path="import-pdf/w.pdf",
        file_sha256="4" * 64,
        status=ImportJobStatus.APPROVED,
    )
    db_session.add(job)
    await db_session.commit()

    await login(db_client, user.email)
    response = await db_client.delete(f"{IMPORT_JOBS}/{job.id}", headers=csrf_headers(db_client))

    assert response.status_code == 409


async def test_endpointy_review_jeszcze_nie_istnieja(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Zakres B15 kończy się na `parsed` — `resolve`/`approve` dostarcza B16."""
    user = await create_user(db_session, email="zakres@example.com")
    await login(db_client, user.email)

    for path in ("staged", "resolve", "approve", "reject"):
        response = await db_client.post(f"{IMPORT_JOBS}/1/{path}", headers=csrf_headers(db_client))
        assert response.status_code == 404, f"/{path} nie powinien istnieć w BATCH_15"


async def test_plik_importu_nie_jest_serwowany_przez_uploads(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Jadłospis to dokument zdrowotny — `/uploads/*` sprawdza tylko sesję (§6)."""
    user = await create_user(db_session, email="prywatnosc@example.com")
    await login(db_client, user.email)
    job = (
        await db_client.post(
            IMPORT_PDF, files=_upload(_diet_pdf()), headers=csrf_headers(db_client)
        )
    ).json()
    stored = (
        await db_session.execute(select(ImportJob.file_path).where(ImportJob.id == job["id"]))
    ).scalar_one()

    response = await db_client.get(f"/uploads/{stored}")

    assert response.status_code == 404


async def test_naglowek_csrf_z_cookie_przechodzi(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Double-submit: token z cookie w nagłówku to jedyny akceptowany wariant."""
    user = await create_user(db_session, email="csrf-ok@example.com")
    await login(db_client, user.email)

    response = await db_client.post(
        IMPORT_PDF,
        files=_upload(_diet_pdf()),
        headers={CSRF_HEADER_NAME: db_client.cookies[CSRF_COOKIE_NAME]},
    )

    assert response.status_code == 201
