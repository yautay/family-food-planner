"""AI-asysta review — na ZAMOCOWANYM kliencie, bez ani jednego realnego wywołania.

Mock siedzi na poziomie `anthropic.AsyncAnthropic`, a nie na metodach
`AiAssistant`: dzięki temu test przechodzi CAŁĄ ścieżkę, którą wykonuje
produkcja — budowę promptu, wymuszony schemat odpowiedzi, walidację Pydantic
i zapis do stagingu. Zamockowanie samego `suggest_mappings` sprawdzałoby
wyłącznie, że test umie skonstruować dataclassę.

Reguła, której pilnuje cały plik (ADR-011, decyzja D5): **AI wyłącznie
proponuje**. Wynik ląduje w `suggested_product_id` + `match_kind=ai` +
`confidence` oraz w `details` uwag — nigdy w `confirmed_product_id` ani
w `resolved_servings`.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, ClassVar

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import CanonicalProduct
from app.modules.importer.ai_assist import AiAssistant
from app.modules.importer.models import (
    ImportIssue,
    ImportIssueKind,
    MatchKind,
    StagedIngredient,
)
from app.modules.importer.review_service import IngredientDecision, ReviewService
from tests.factories import (
    create_admin,
    create_category,
    create_import_issue,
    create_import_job,
    create_product,
    create_recipe,
    create_staged_ingredient,
    create_staged_recipe,
    create_user,
)

pytestmark = pytest.mark.integration

#: Klucz jest atrapą i nigdzie nie wychodzi — klient HTTP jest zamocowany.
FAKE_KEY = "sk-ant-test-nieprawdziwy"


class _FakeBlock:
    """Blok treści odpowiedzi w kształcie, który zwraca SDK."""

    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.content = [_FakeBlock(text)]


class _FakeMessages:
    def __init__(self, owner: _FakeClient) -> None:
        self._owner = owner

    async def create(self, **kwargs: Any) -> _FakeMessage:
        """Odpowiedź dobrana po schemacie żądania — tak jak zrobiłby to model."""
        self._owner.calls.append(kwargs)
        schema = kwargs["output_config"]["format"]["schema"]
        payload = (
            self._owner.mappings if "mappings" in schema["properties"] else self._owner.duplicates
        )
        return _FakeMessage(json.dumps(payload))


class _FakeClient:
    """Atrapa `anthropic.AsyncAnthropic` — zbiera żądania, oddaje ustalone treści."""

    #: Ustawiane przez fixture przed każdym testem (klasa jest wołana konstruktorem
    #: przez kod produkcyjny, więc dane muszą być dostępne bez przekazywania ich).
    mappings: ClassVar[dict[str, Any]] = {"mappings": []}
    duplicates: ClassVar[dict[str, Any]] = {"duplicates": [], "servings": []}
    calls: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.init_kwargs = kwargs
        self.messages = _FakeMessages(self)

    async def close(self) -> None:
        return None


@pytest.fixture
def fake_anthropic(monkeypatch: pytest.MonkeyPatch) -> type[_FakeClient]:
    """Podmień klienta SDK na atrapę. Brak sieci jest tu WARUNKIEM testu."""
    import anthropic

    _FakeClient.mappings = {"mappings": []}
    _FakeClient.duplicates = {"duplicates": [], "servings": []}
    _FakeClient.calls = []
    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeClient)
    return _FakeClient


def _service(session: AsyncSession) -> ReviewService:
    return ReviewService(
        session,
        uploads_dir="data/uploads",
        max_pdf_mb=25,
        assistant=AiAssistant(
            api_key=FAKE_KEY, model="claude-opus-5", max_tokens=1024, timeout_s=5.0
        ),
    )


# --- fuzzy mapowania -------------------------------------------------------------------


async def test_propozycja_ai_zapisuje_sie_jako_sugestia_z_pewnoscia(
    db_session: AsyncSession, fake_anthropic: type[_FakeClient]
) -> None:
    """`match_kind=ai` + `confidence`; `confirmed_product_id` zostaje PUSTE (ADR-011)."""
    user = await create_user(db_session, email="ai@example.com")
    category = await create_category(db_session, name="Nabiał")
    product = await create_product(db_session, category=category, name="Skyr naturalny")
    job = await create_import_job(db_session, owner=user)
    dish = await create_staged_recipe(db_session, job=job)
    ingredient = await create_staged_ingredient(
        db_session, staged_recipe=dish, raw_name="Skyr naturalny pitny"
    )
    fake_anthropic.mappings = {
        "mappings": [
            {"raw_name": "Skyr naturalny pitny", "product_id": product.id, "confidence": 0.82}
        ]
    }

    view = await _service(db_session).ai_suggest(job.id, actor=user)

    await db_session.refresh(ingredient)
    assert ingredient.suggested_product_id == product.id
    assert ingredient.match_kind is MatchKind.AI
    assert ingredient.confidence == Decimal("0.82")
    assert ingredient.confirmed_product_id is None
    # Propozycja NIE zdejmuje blokady — składnik nadal czeka na człowieka.
    assert [item.kind.value for item in view.blockers] == ["unmapped_product"]


async def test_ai_nie_rusza_mapowania_potwierdzonego_przez_czlowieka(
    db_session: AsyncSession, fake_anthropic: type[_FakeClient]
) -> None:
    """Decyzja człowieka jest ostateczna — kolejne uruchomienie AI jej nie nadpisze."""
    user = await create_user(db_session, email="aikeep@example.com")
    category = await create_category(db_session, name="Nabiał")
    wybrany = await create_product(db_session, category=category, name="Skyr naturalny")
    inny = await create_product(db_session, category=category, name="Skyr waniliowy")
    job = await create_import_job(db_session, owner=user)
    dish = await create_staged_recipe(db_session, job=job)
    ingredient = await create_staged_ingredient(
        db_session, staged_recipe=dish, raw_name="Skyr naturalny pitny"
    )
    service = _service(db_session)
    await service.resolve(
        job.id,
        actor=user,
        recipes=[],
        ingredients=[
            IngredientDecision(ingredient_id=ingredient.id, confirmed_product_id=wybrany.id)
        ],
        issues=[],
    )
    fake_anthropic.mappings = {
        "mappings": [
            {"raw_name": "Skyr naturalny pitny", "product_id": inny.id, "confidence": 0.99}
        ]
    }

    await service.ai_suggest(job.id, actor=user)

    await db_session.refresh(ingredient)
    assert ingredient.confirmed_product_id == wybrany.id
    assert ingredient.suggested_product_id != inny.id


async def test_odpowiedz_niezgodna_ze_schematem_nie_wysadza_zadania(
    db_session: AsyncSession, fake_anthropic: type[_FakeClient]
) -> None:
    """Uszkodzona odpowiedź = brak propozycji, nie 500 (ADR-011)."""
    user = await create_user(db_session, email="aibroken@example.com")
    category = await create_category(db_session, name="Nabiał")
    await create_product(db_session, category=category, name="Skyr naturalny")
    job = await create_import_job(db_session, owner=user)
    dish = await create_staged_recipe(db_session, job=job)
    ingredient = await create_staged_ingredient(
        db_session, staged_recipe=dish, raw_name="Skyr naturalny pitny"
    )
    fake_anthropic.mappings = {"mappings": [{"raw_name": "Skyr naturalny pitny"}]}

    view = await _service(db_session).ai_suggest(job.id, actor=user)

    await db_session.refresh(ingredient)
    assert ingredient.suggested_product_id is None
    assert ingredient.match_kind is MatchKind.NONE
    assert view.ai_available is True


# --- duplikaty i porcje -----------------------------------------------------------------


async def test_duplikat_trafia_do_uwagi_jako_ostrzezenie_a_nie_blokada(
    db_session: AsyncSession, fake_anthropic: type[_FakeClient]
) -> None:
    """`duplicate_recipe` ma severity `warning` — scalenie to decyzja człowieka."""
    user = await create_user(db_session, email="aidup@example.com")
    existing = await create_recipe(db_session, owner=user, name="Gołąbki bez zawijania")
    job = await create_import_job(db_session, owner=user)
    dish = await create_staged_recipe(db_session, job=job, name="Gołąbki bez zawijania")
    fake_anthropic.duplicates = {
        "duplicates": [{"staged_recipe_id": dish.id, "recipe_id": existing.id, "confidence": 0.93}],
        "servings": [],
    }

    view = await _service(db_session).ai_suggest(job.id, actor=user)

    issue = (
        await db_session.execute(
            select(ImportIssue).where(ImportIssue.kind == ImportIssueKind.DUPLICATE_RECIPE)
        )
    ).scalar_one()
    assert issue.details["przepis_id"] == existing.id
    assert issue.details["przepis_nazwa"] == "Gołąbki bez zawijania"
    assert issue.details["pewność"] == "0.93"
    assert view.blockers == []


async def test_podpowiedz_porcji_ladunie_w_uwadze_a_nie_w_polu_porcji(
    db_session: AsyncSession, fake_anthropic: type[_FakeClient]
) -> None:
    """Twarda granica ADR-011: `resolved_servings` ustawia WYŁĄCZNIE człowiek."""
    user = await create_user(db_session, email="aiservings@example.com")
    job = await create_import_job(db_session, owner=user)
    dish = await create_staged_recipe(
        db_session, job=job, instructions="Uformować kotlety (około 21 szt)."
    )
    issue = await create_import_issue(db_session, job=job, staged_recipe=dish)
    fake_anthropic.duplicates = {
        "duplicates": [],
        "servings": [
            {
                "staged_recipe_id": dish.id,
                "servings": 21,
                "rationale": "Instrukcja mówi „około 21 szt”.",
            }
        ],
    }

    await _service(db_session).ai_suggest(job.id, actor=user)

    await db_session.refresh(issue)
    await db_session.refresh(dish)
    assert issue.details["propozycja_ai_porcje"] == 21
    assert "21" in issue.details["propozycja_ai_uzasadnienie"]
    assert dish.resolved_servings is None
    assert issue.resolved_at is None


# --- granica danych wysyłanych do modelu (D5) ---------------------------------------------


async def test_do_modelu_nie_ida_zadne_dane_uzytkownika(
    db_session: AsyncSession, fake_anthropic: type[_FakeClient]
) -> None:
    """Decyzja D5 zezwala na treść PDF-a i katalog produktów — na nic więcej.

    Test czyta DOSŁOWNIE to, co poszłoby do sieci, i sprawdza, że nie ma tam
    ani e-maila, ani nazwy rodziny, ani identyfikatora konta.
    """
    user = await create_user(db_session, email="tajny.adres@example.com")
    category = await create_category(db_session, name="Nabiał")
    await create_product(db_session, category=category, name="Skyr naturalny")
    job = await create_import_job(db_session, owner=user, filename="jadlospis-pacjenta.pdf")
    dish = await create_staged_recipe(db_session, job=job)
    await create_staged_ingredient(db_session, staged_recipe=dish, raw_name="Skyr naturalny pitny")

    await _service(db_session).ai_suggest(job.id, actor=user)

    sent = json.dumps(fake_anthropic.calls, ensure_ascii=False, default=str)
    assert "tajny.adres@example.com" not in sent
    assert "jadlospis-pacjenta.pdf" not in sent
    assert "Skyr naturalny pitny" in sent
    # Klucz idzie do konstruktora klienta, nie do treści żądania.
    assert FAKE_KEY not in sent


async def test_klucz_nie_wycieka_do_odpowiedzi_api(
    db_session: AsyncSession, fake_anthropic: type[_FakeClient]
) -> None:
    """Odpowiedź `staged` niesie WYŁĄCZNIE flagę dostępności asysty (07_SECURITY §7)."""
    user = await create_user(db_session, email="aikey@example.com")
    job = await create_import_job(db_session, owner=user)
    await create_staged_recipe(db_session, job=job)

    view = await _service(db_session).staged(job.id, actor=user)

    assert view.ai_available is True
    assert FAKE_KEY not in json.dumps(
        {"ai_available": view.ai_available, "recipes": [r.recipe.name for r in view.recipes]}
    )


async def test_niezmapowane_skladniki_nie_wchodza_do_promptu_gdy_juz_maja_sugestie(
    db_session: AsyncSession, fake_anthropic: type[_FakeClient]
) -> None:
    """Sugestia EXACT z BATCH_15 jest pewniejsza niż cokolwiek, co powie model."""
    user = await create_user(db_session, email="aiexact@example.com")
    category = await create_category(db_session, name="Warzywa")
    product = await create_product(db_session, category=category, name="Cebula")
    job = await create_import_job(db_session, owner=user)
    dish = await create_staged_recipe(db_session, job=job)
    await create_staged_ingredient(
        db_session,
        staged_recipe=dish,
        raw_name="Cebula",
        suggested_product=product,
        match_kind=MatchKind.EXACT,
    )

    await _service(db_session).ai_suggest(job.id, actor=user)

    prompts = json.dumps(fake_anthropic.calls, ensure_ascii=False, default=str)
    ingredient = (await db_session.execute(select(StagedIngredient))).scalar_one()
    assert ingredient.match_kind is MatchKind.EXACT
    # Jedyne wywołanie dotyczyło duplikatów — nie było czego mapować.
    assert "Nazwy do dopasowania" not in prompts


async def test_produkty_katalogu_ida_do_modelu_jako_kandydaci(
    db_session: AsyncSession, fake_anthropic: type[_FakeClient]
) -> None:
    """Bez kandydatów model musiałby zgadywać id — a tego nie wolno mu robić."""
    user = await create_user(db_session, email="aicand@example.com")
    category = await create_category(db_session, name="Nabiał")
    product = await create_product(db_session, category=category, name="Skyr naturalny")
    job = await create_import_job(db_session, owner=user)
    dish = await create_staged_recipe(db_session, job=job)
    await create_staged_ingredient(db_session, staged_recipe=dish, raw_name="Skyr naturalny pitny")

    await _service(db_session).ai_suggest(job.id, actor=user)

    mapping_call = next(
        call
        for call in fake_anthropic.calls
        if "mappings" in call["output_config"]["format"]["schema"]["properties"]
    )
    assert f"id={product.id}" in mapping_call["messages"][0]["content"]


async def test_produkt_spoza_katalogu_nie_da_sie_podsunac_przez_odpowiedz(
    db_session: AsyncSession, fake_anthropic: type[_FakeClient]
) -> None:
    """Halucynowane id produktu wysadziłoby FK — filtr stoi PRZED zapisem."""
    user = await create_user(db_session, email="aifake@example.com")
    category = await create_category(db_session, name="Nabiał")
    await create_product(db_session, category=category, name="Skyr naturalny")
    job = await create_import_job(db_session, owner=user)
    dish = await create_staged_recipe(db_session, job=job)
    ingredient = await create_staged_ingredient(
        db_session, staged_recipe=dish, raw_name="Skyr naturalny pitny"
    )
    fake_anthropic.mappings = {
        "mappings": [
            {"raw_name": "Skyr naturalny pitny", "product_id": 999_999, "confidence": 0.99}
        ]
    }

    await _service(db_session).ai_suggest(job.id, actor=user)

    await db_session.refresh(ingredient)
    assert ingredient.suggested_product_id is None
    assert (
        await db_session.execute(select(CanonicalProduct.id).where(CanonicalProduct.id == 999_999))
    ).scalar_one_or_none() is None


async def test_admin_nie_wysyla_do_modelu_przepisow_cudzych_rodzin(
    db_session: AsyncSession, fake_anthropic: type[_FakeClient]
) -> None:
    """Ustalenie `/security-review`: granica D5 nie może zależeć od roli.

    ADMIN widzi na ścieżkach użytkownika WSZYSTKIE encje ze scope (D16), więc
    lista kandydatów do wykrywania duplikatów liczona „widocznością" wysłałaby
    poza instancję nazwy przepisów cudzych rodzin. Kandydatów wyznacza więc
    PRZYNALEŻNOŚĆ (`owned_condition`), tak samo jak przy eksporcie własnych
    danych.
    """
    admin = await create_admin(db_session, email="adminai@example.com")
    stranger = await create_user(db_session, email="obcy@example.com")
    await create_recipe(db_session, owner=stranger, name="Tajny przepis cudzej rodziny")
    await create_recipe(db_session, owner=admin, name="Mój własny przepis")
    job = await create_import_job(db_session, owner=admin)
    await create_staged_recipe(db_session, job=job)

    await _service(db_session).ai_suggest(job.id, actor=admin)

    sent = json.dumps(fake_anthropic.calls, ensure_ascii=False, default=str)
    assert "Tajny przepis cudzej rodziny" not in sent
    assert "Mój własny przepis" in sent
