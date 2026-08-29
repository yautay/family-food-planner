"""Kontrakt HTTP ekranu review importu (`/import/jobs/{id}/…`, 04_API §2-3).

Cztery rzeczy, których pilnuje ten plik:

1. **Macierz uprawnień** (08_TESTING §4): anonim 401/403, cudzy job 404
   (nie 403), właściciel 200, ADMIN widzi wszystko (D16). Staging stoi poza
   wzorcem scope, więc jego widoczność MUSI mieć własny test — `ScopedQuery`
   nie zrobi tego za nas.
2. **Walidacja wejścia**: `resolved_servings ≥ 1`, nieistniejące id dania,
   scalenie bez celu.
3. **Tryb bez klucza AI**: `ai-suggest` odpowiada 503 z komunikatem po polsku,
   a `staged` niesie `ai_available: false`, żeby UI schowało przyciski.
4. **CSRF**: każda mutacja bez nagłówka to 403, jak w każdym innym module.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.importer.models import ImportJobStatus
from tests.factories import (
    create_admin,
    create_category,
    create_import_issue,
    create_import_job,
    create_product,
    create_staged_ingredient,
    create_staged_recipe,
    create_user,
)
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

IMPORT_JOBS = f"{API}/import/jobs"


async def _job_with_dish(session: AsyncSession, owner_email: str):  # type: ignore[no-untyped-def]
    """Job z jednym daniem i jednym niezmapowanym składnikiem."""
    user = await create_user(session, email=owner_email)
    job = await create_import_job(session, owner=user)
    dish = await create_staged_recipe(session, job=job, pdf_kcal=Decimal("635"))
    ingredient = await create_staged_ingredient(
        session, staged_recipe=dish, raw_qty=Decimal("2"), raw_unit="Sztuka"
    )
    return user, job, dish, ingredient


# --- macierz uprawnień --------------------------------------------------------------


async def test_anonim_nie_zobaczy_stagingu(client: AsyncClient) -> None:
    """Odczyt bez sesji to 401 — endpoint nie ma trybu publicznego."""
    response = await client.get(f"{IMPORT_JOBS}/1/staged")

    assert response.status_code == 401


async def test_anonimowa_mutacja_konczy_sie_na_csrf(client: AsyncClient) -> None:
    """Middleware CSRF działa PRZED routingiem — anonim nie dochodzi do sesji."""
    response = await client.post(f"{IMPORT_JOBS}/1/approve", json={})

    assert response.status_code == 403


async def test_cudzy_job_to_404_a_nie_403(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """Ta sama granica, co w BATCH_15: cudzy import po prostu nie istnieje."""
    _, job, _, _ = await _job_with_dish(db_session, "wlasciciel@example.com")
    stranger = await create_user(db_session, email="obcy@example.com")
    await login(db_client, stranger.email)

    for path, method in (("staged", "get"), ("resolve", "post"), ("reject", "post")):
        call = getattr(db_client, method)
        response = await (
            call(f"{IMPORT_JOBS}/{job.id}/{path}")
            if method == "get"
            else call(f"{IMPORT_JOBS}/{job.id}/{path}", json={}, headers=csrf_headers(db_client))
        )
        assert response.status_code == 404, f"/{path} zdradza istnienie cudzego importu"


async def test_admin_widzi_cudzy_staging(db_client: AsyncClient, db_session: AsyncSession) -> None:
    """Decyzja D16: ADMIN widzi wszystkie encje na ścieżkach użytkownika."""
    _, job, _, _ = await _job_with_dish(db_session, "user@example.com")
    admin = await create_admin(db_session, email="admin@example.com")
    await login(db_client, admin.email)

    response = await db_client.get(f"{IMPORT_JOBS}/{job.id}/staged")

    assert response.status_code == 200
    assert len(response.json()["recipes"]) == 1


async def test_wlasciciel_dostaje_komplet_stanu_review(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Odpowiedź `staged` musi wystarczyć do narysowania ekranu bez dociągania."""
    user, job, dish, ingredient = await _job_with_dish(db_session, "owner@example.com")
    await create_import_issue(db_session, job=job, staged_recipe=dish)
    await login(db_client, user.email)

    payload = (await db_client.get(f"{IMPORT_JOBS}/{job.id}/staged")).json()

    assert payload["job"]["id"] == job.id
    recipe = payload["recipes"][0]
    assert recipe["id"] == dish.id
    assert recipe["meal"]["pdf_kcal"] == "635.0"
    assert recipe["ingredients"][0]["id"] == ingredient.id
    # Ilości dziesiętne wychodzą STRINGAMI (ADR-008) — inaczej `fe-types` dałby number.
    assert recipe["ingredients"][0]["grams"] == "100.000"
    assert recipe["ingredients"][0]["raw_qty"] == "2.000"
    assert [item["kind"] for item in recipe["issues"]] == ["multi_portion_suspect"]
    assert payload["ai_available"] is False


# --- walidacja wejścia ---------------------------------------------------------------


async def test_zero_porcji_jest_odrzucane_przez_schemat(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`resolved_servings ≥ 1`: przepis „na zero porcji" nie ma mianownika."""
    user, job, dish, _ = await _job_with_dish(db_session, "servings@example.com")
    await login(db_client, user.email)

    response = await db_client.post(
        f"{IMPORT_JOBS}/{job.id}/resolve",
        json={"recipes": [{"staged_recipe_id": dish.id, "resolved_servings": 0}]},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422


async def test_danie_z_innego_importu_to_404(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Rozstrzygnięcie może dotyczyć wyłącznie dań TEGO joba."""
    user, job, _, _ = await _job_with_dish(db_session, "cross@example.com")
    other_job = await create_import_job(db_session, owner=user)
    other_dish = await create_staged_recipe(db_session, job=other_job)
    await login(db_client, user.email)

    response = await db_client.post(
        f"{IMPORT_JOBS}/{job.id}/resolve",
        json={"recipes": [{"staged_recipe_id": other_dish.id, "resolved_servings": 2}]},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 404


async def test_zatwierdzenie_z_blokada_zwraca_409_z_lista(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 5: 409 z CZYTELNĄ listą blokad, żeby UI mogło pokazać, czego brakuje."""
    user, job, dish, _ = await _job_with_dish(db_session, "blocked@example.com")
    await create_import_issue(db_session, job=job, staged_recipe=dish)
    await login(db_client, user.email)

    response = await db_client.post(
        f"{IMPORT_JOBS}/{job.id}/approve", json={}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 409
    blockers = response.json()["error"]["details"]["blockers"]
    assert {item["kind"] for item in blockers} == {"multi_portion_suspect", "unmapped_product"}
    assert all(item["recipe_name"] for item in blockers)


async def test_mutacja_bez_naglowka_csrf_to_403(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Ta sama reguła, co w każdym module (07_SECURITY §3)."""
    user, job, _, _ = await _job_with_dish(db_session, "csrf@example.com")
    await login(db_client, user.email)

    response = await db_client.post(f"{IMPORT_JOBS}/{job.id}/resolve", json={})

    assert response.status_code == 403


# --- tryb bez klucza AI ----------------------------------------------------------------


async def test_asysta_bez_klucza_odpowiada_503_po_polsku(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """ADR-011: brak klucza to wspierany tryb pracy, nie awaria i nie 404."""
    user, job, _, _ = await _job_with_dish(db_session, "noai@example.com")
    await login(db_client, user.email)

    response = await db_client.post(
        f"{IMPORT_JOBS}/{job.id}/ai-suggest", json={}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 503
    body = response.json()["error"]
    assert body["code"] == "service_unavailable"
    assert "klucza API" in body["message"]


# --- pełny przebieg HTTP ------------------------------------------------------------------


async def test_pelny_przebieg_resolve_approve_przez_http(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Flow z ekranu review od pierwszego kliknięcia do podsumowania (AC 1-6)."""
    user, job, dish, ingredient = await _job_with_dish(db_session, "flow@example.com")
    category = await create_category(db_session, name="Warzywa")
    product = await create_product(
        db_session, category=category, name="Cebula", kcal_100=Decimal("40")
    )
    await login(db_client, user.email)

    resolved = await db_client.post(
        f"{IMPORT_JOBS}/{job.id}/resolve",
        json={
            "recipes": [{"staged_recipe_id": dish.id, "resolved_servings": 1}],
            "ingredients": [{"ingredient_id": ingredient.id, "confirmed_product_id": product.id}],
        },
        headers=csrf_headers(db_client),
    )

    assert resolved.status_code == 200
    body = resolved.json()
    assert body["job"]["status"] == ImportJobStatus.IN_REVIEW.value
    assert body["blockers"] == []
    assert body["recipes"][0]["ingredients"][0]["confirmed_product_name"] == "Cebula"
    # 100 g cebuli po 40 kcal/100 g = 40 kcal wobec 635 z jadłospisu ⇒ ostrzeżenie.
    assert body["recipes"][0]["meal"]["computed_kcal"] == "40"
    assert [item["kind"] for item in body["recipes"][0]["issues"]] == ["kcal_mismatch"]

    approved = await db_client.post(
        f"{IMPORT_JOBS}/{job.id}/approve",
        json={"scope": "private"},
        headers=csrf_headers(db_client),
    )

    assert approved.status_code == 200
    summary = approved.json()
    assert summary["job"]["status"] == ImportJobStatus.APPROVED.value
    assert len(summary["created_recipe_ids"]) == 1
    assert summary["created_product_ids"] == []
    assert summary["unit_weight_rows"] == 0  # „Sztuka" to `piece_weight_g`, nie przelicznik


async def test_odrzucenie_przestawia_status_i_czysci_staging(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 7: `reject` zostawia job jako ślad decyzji, ale bez stagingu."""
    user, job, _, _ = await _job_with_dish(db_session, "rejectapi@example.com")
    await login(db_client, user.email)

    response = await db_client.post(
        f"{IMPORT_JOBS}/{job.id}/reject", json={}, headers=csrf_headers(db_client)
    )

    assert response.status_code == 200
    assert response.json()["status"] == ImportJobStatus.REJECTED.value

    staged = await db_client.get(f"{IMPORT_JOBS}/{job.id}/staged")
    assert staged.json()["recipes"] == []


async def test_rozstrzygniety_import_nie_przyjmuje_juz_decyzji(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Po `reject` job jest zamknięty — kolejne `resolve` to 409, nie cichy zapis."""
    user, job, dish, _ = await _job_with_dish(db_session, "closed@example.com")
    await login(db_client, user.email)
    await db_client.post(f"{IMPORT_JOBS}/{job.id}/reject", json={}, headers=csrf_headers(db_client))

    response = await db_client.post(
        f"{IMPORT_JOBS}/{job.id}/resolve",
        json={"recipes": [{"staged_recipe_id": dish.id, "resolved_servings": 2}]},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 409
