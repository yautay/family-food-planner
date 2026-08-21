"""Kontrakt HTTP `/products`: macierz uprawnień, walidacje, archiwizacja, audit.

Macierz z 08_TESTING §4 wiersz „nutrition produktu (edycja)" jest tu dowodzona
kodami HTTP: anonim 401, USER 403, ADMIN 200. Katalog jest globalny, więc nie ma
tu 404-owania cudzych zasobów — jest jedna widoczność i różne prawa zapisu.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deletion import UsedInRef
from app.modules.catalog.models import MeasureKind, VerificationStatus
from app.modules.catalog.service import (
    register_product_reference_finder,
    unregister_product_reference_finder,
)
from tests.factories import (
    create_admin,
    create_category,
    create_product,
    create_unit_weight,
    create_user,
)
from tests.helpers import API, csrf_headers, login

pytestmark = pytest.mark.api

PRODUCTS = f"{API}/products"

FULL_NUTRITION: dict[str, Any] = {
    "kcal_100": "40.00",
    "protein_100": "1.10",
    "fat_100": "0.10",
    "carbs_100": "9.30",
    "fiber_100": "1.70",
    "sugars_100": "4.20",
    "glycemic_index": "15.0",
    "nutrition_source": "usda:11282",
}


async def _audit_entries(client: AsyncClient, action: str) -> list[dict[str, Any]]:
    """Wpisy dziennika danej akcji — wymaga zalogowanego ADMIN-a."""
    response = await client.get(f"{API}/audit", params={"action": action})
    assert response.status_code == 200
    items: list[dict[str, Any]] = response.json()["items"]
    return items


# --- macierz uprawnień ------------------------------------------------------------


async def test_anonim_nie_widzi_katalogu(db_client: AsyncClient) -> None:
    assert (await db_client.get(PRODUCTS)).status_code == 401


async def test_anonim_nie_edytuje_wartosci_odzywczych(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)

    response = await db_client.put(f"{PRODUCTS}/{product.id}/nutrition", json=FULL_NUTRITION)

    # Anonimowa MUTACJA nigdy nie dochodzi do warstwy sesji: middleware CSRF
    # działa przed routingiem, a bez cookie nie ma z czym porównać nagłówka
    # (07_SECURITY §3). 401 dla anonima dowodzi więc odczyt — patrz
    # `test_anonim_nie_widzi_katalogu`; tutaj kontraktem jest 403.
    assert response.status_code == 403
    with_token = await db_client.put(
        f"{PRODUCTS}/{product.id}/nutrition",
        json=FULL_NUTRITION,
        headers={"X-CSRF-Token": "token-bez-cookie"},
    )
    assert with_token.status_code == 403


async def test_uzytkownik_nie_edytuje_wartosci_odzywczych(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """08_TESTING §4: nutrition produktu edytuje wyłącznie ADMIN."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await login(db_client, user.email)

    response = await db_client.put(
        f"{PRODUCTS}/{product.id}/nutrition",
        json=FULL_NUTRITION,
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_uzytkownik_nie_weryfikuje_produktu(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await login(db_client, user.email)

    response = await db_client.post(
        f"{PRODUCTS}/{product.id}/verify", headers=csrf_headers(db_client)
    )

    assert response.status_code == 403


async def test_uzytkownik_nie_usuwa_produktu_ale_dostaje_podpowiedz(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """D13: usuwa wyłącznie ADMIN; USER dowiaduje się o archiwizacji."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await login(db_client, user.email)

    response = await db_client.delete(f"{PRODUCTS}/{product.id}", headers=csrf_headers(db_client))

    assert response.status_code == 403
    assert "zarchiwizować" in response.json()["error"]["message"]


async def test_d15_uzytkownik_nie_zmienia_sposobu_liczenia(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """D15: `measure_kind` zmienia WYŁĄCZNIE ADMIN — także twórcy produktu.

    Produkt zakłada tu sam USER (inline create), bo właśnie ten przypadek
    właściciel rozstrzygnął świadomie: autor świeżego wpisu też nie poprawi
    sobie miary, zostaje mu prośba do administratora albo nowy produkt.
    """
    user = await create_user(db_session)
    category = await create_category(db_session)
    await login(db_client, user.email)
    headers = csrf_headers(db_client)
    created = await db_client.post(
        PRODUCTS,
        json={"name": "Mleko 2%", "category_id": category.id, "measure_kind": "volume"},
        headers=headers,
    )
    assert created.status_code == 201
    product_id = created.json()["id"]

    response = await db_client.patch(
        f"{PRODUCTS}/{product_id}", json={"measure_kind": "mass"}, headers=headers
    )

    assert response.status_code == 403
    message = response.json()["error"]["message"]
    assert "administrator" in message
    # Komunikat ma pokazywać wyjście, nie tylko odmawiać (wzorzec D13).
    assert "nowy produkt" in message
    # Nic się nie zapisało: miara została ta sama.
    detail = await db_client.get(f"{PRODUCTS}/{product_id}")
    assert detail.json()["measure_kind"] == "volume"


async def test_d15_uzytkownik_nie_zmienia_wagi_sztuki(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """D15: waga sztuki jedzie z tą samą bramką, bo jest sprzężona z miarą.

    Bez tego USER przestawiłby `piece_weight_g` i zmienił wynik wszystkich
    przeliczeń szt. → g, nie ruszając samego pola miary.
    """
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(
        db_session,
        category=category,
        name="Jajko",
        measure_kind=MeasureKind.PIECE,
        piece_weight_g=Decimal("60.00"),
    )
    await login(db_client, user.email)

    response = await db_client.patch(
        f"{PRODUCTS}/{product.id}",
        json={"piece_weight_g": "70.00"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 403


async def test_d15_uzytkownik_edytuje_pozostale_pola_opisowe(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Bramka D15 nie ma prawa zablokować całego endpointu (wymóg karty B09).

    Formularz produktu wysyła `measure_kind` i `piece_weight_g` przy KAŻDYM
    zapisie, więc żądanie z niezmienioną miarą musi przechodzić — inaczej USER
    nie zmieniłby nawet nazwy.
    """
    user = await create_user(db_session)
    category = await create_category(db_session)
    inna = await create_category(db_session, name="Nabiał", position=2)
    product = await create_product(db_session, category=category, name="Cebula")
    await login(db_client, user.email)

    response = await db_client.patch(
        f"{PRODUCTS}/{product.id}",
        json={
            "name": "Cebula czerwona",
            "category_id": inna.id,
            "perishability_override": "durable",
            # Pola pod bramką jadą z żądaniem, ale BEZ zmiany wartości.
            "measure_kind": "mass",
            "piece_weight_g": None,
        },
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["name"], body["category_id"]) == ("Cebula czerwona", inna.id)
    assert body["perishability_override"] == "durable"


async def test_d15_admin_zmienia_sposob_liczenia(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Druga strona macierzy: ADMIN przestawia miarę i zbija weryfikację."""
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    product = await create_product(
        db_session,
        category=category,
        name="Mleko 2%",
        measure_kind=MeasureKind.VOLUME,
        kcal_100=Decimal("50.00"),
        nutrition_source="producent:etykieta",
        verification_status=VerificationStatus.VERIFIED,
    )
    await login(db_client, admin.email)

    response = await db_client.patch(
        f"{PRODUCTS}/{product.id}",
        json={"measure_kind": "mass"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["measure_kind"] == "mass"
    # Część pierwsza D15 (z B05) obowiązuje dalej: zmiana osi unieważnia weryfikację.
    assert body["verification_status"] == "unverified"
    assert body["verified_at"] is None


async def test_mutacja_bez_csrf_daje_403(db_client: AsyncClient, db_session: AsyncSession) -> None:
    user = await create_user(db_session)
    category = await create_category(db_session)
    await login(db_client, user.email)

    response = await db_client.post(PRODUCTS, json={"name": "Cebula", "category_id": category.id})

    assert response.status_code == 403


# --- tworzenie produktu -------------------------------------------------------------


async def test_uzytkownik_tworzy_produkt_jako_niezweryfikowany(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 2: inline create USERA kończy się produktem `UNVERIFIED` (02_DOMAIN §4.9)."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    await login(db_client, user.email)

    response = await db_client.post(
        PRODUCTS,
        json={"name": "  Cebula czerwona ", "category_id": category.id},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Cebula czerwona"
    assert body["normalized_name"] == "cebula czerwona"
    assert body["verification_status"] == VerificationStatus.UNVERIFIED.value
    assert body["completeness"]["complete"] is False
    assert body["nutrition"]["kcal_100"] is None


async def test_utworzenie_produktu_trafia_do_dziennika(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Kto dodał UNVERIFIED, ma znaczenie przy weryfikacji (02_DOMAIN §12)."""
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    await login(db_client, admin.email)
    await db_client.post(
        PRODUCTS,
        json={"name": "Cebula", "category_id": category.id},
        headers=csrf_headers(db_client),
    )

    entries = await _audit_entries(db_client, "product.create")

    assert len(entries) == 1
    assert entries[0]["payload"]["name"] == "Cebula"
    assert entries[0]["user_id"] == admin.id


async def test_duplikat_nazwy_daje_409_z_podpowiedzia_istniejacego(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Picker ma z czego zbudować „ten produkt już jest" (06_UIUX §3.1)."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    existing = await create_product(db_session, category=category, name="Cebula")
    await login(db_client, user.email)

    response = await db_client.post(
        PRODUCTS,
        json={"name": "CEBULA", "category_id": category.id},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 409
    details = response.json()["error"]["details"]
    assert details["existing"] == {
        "id": existing.id,
        "name": "Cebula",
        "is_archived": False,
    }


async def test_nieistniejaca_kategoria_daje_404(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    await login(db_client, user.email)

    response = await db_client.post(
        PRODUCTS,
        json={"name": "Cebula", "category_id": 999999},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 404


# --- walidacje wejścia ----------------------------------------------------------------


async def test_produkt_w_sztukach_bez_wagi_sztuki_jest_odrzucany(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    category = await create_category(db_session)
    await login(db_client, user.email)

    response = await db_client.post(
        PRODUCTS,
        json={"name": "Jajko", "category_id": category.id, "measure_kind": "piece"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_indeks_glikemiczny_powyzej_110_jest_odrzucany(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """CHECK 0..110 z 03_DATABASE §3 ma odpowiednik w walidacji wejścia."""
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await login(db_client, admin.email)

    response = await db_client.put(
        f"{PRODUCTS}/{product.id}/nutrition",
        json={**FULL_NUTRITION, "glycemic_index": "111"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422


async def test_wartosc_ujemna_jest_odrzucana(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await login(db_client, admin.email)

    response = await db_client.put(
        f"{PRODUCTS}/{product.id}/nutrition",
        json={**FULL_NUTRITION, "protein_100": "-1.00"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422


async def test_liczba_zmiennoprzecinkowa_spoza_precyzji_kolumny_jest_odrzucana(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Granica API odrzuca float, którego NUMERIC nie zapisze bez utraty danych (ADR-008)."""
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await login(db_client, admin.email)

    response = await db_client.put(
        f"{PRODUCTS}/{product.id}/nutrition",
        json={**FULL_NUTRITION, "kcal_100": 40.123456789},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422


async def test_pusta_nazwa_z_samych_spacji_jest_odrzucana(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    category = await create_category(db_session)
    await login(db_client, user.email)

    response = await db_client.post(
        PRODUCTS,
        json={"name": "   ", "category_id": category.id},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422


# --- wartości odżywcze i weryfikacja ---------------------------------------------------


async def test_admin_zapisuje_wartosci_odzywcze_jako_stringi_dziesietne(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await login(db_client, admin.email)

    response = await db_client.put(
        f"{PRODUCTS}/{product.id}/nutrition",
        json=FULL_NUTRITION,
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 200
    nutrition = response.json()["nutrition"]
    # Stringi, nie liczby — inaczej JSON zamieniłby NUMERIC na float (04_API §1).
    assert nutrition["kcal_100"] == "40.00"
    assert nutrition["glycemic_index"] == "15.0"
    assert response.json()["completeness"]["complete"] is True


async def test_zmiana_wartosci_zapisuje_w_dzienniku_stan_przed_i_po(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 3: rozliczalność danych, na których liczy silnik (02_DOMAIN §12)."""
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    product = await create_product(
        db_session, category=category, kcal_100=Decimal("40.00"), nutrition_source="manual"
    )
    await login(db_client, admin.email)

    await db_client.put(
        f"{PRODUCTS}/{product.id}/nutrition",
        json=FULL_NUTRITION,
        headers=csrf_headers(db_client),
    )
    entries = await _audit_entries(db_client, "product.nutrition_update")

    assert len(entries) == 1
    payload = entries[0]["payload"]
    assert payload["before"]["kcal_100"] == "40.00"
    assert payload["before"]["protein_100"] is None
    assert payload["before"]["nutrition_source"] == "manual"
    assert payload["after"]["protein_100"] == "1.10"
    assert payload["after"]["nutrition_source"] == "usda:11282"
    assert entries[0]["entity_type"] == "product"
    assert entries[0]["entity_id"] == product.id


async def test_put_wartosci_czysci_pola_pominiete(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """PUT to pełna podmiana: brak pola = „nie znamy tej wartości", nie „zostaw"."""
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    product = await create_product(
        db_session,
        category=category,
        kcal_100=Decimal("40.00"),
        glycemic_index=Decimal("15.0"),
    )
    await login(db_client, admin.email)

    response = await db_client.put(
        f"{PRODUCTS}/{product.id}/nutrition",
        json={"kcal_100": "45.00", "nutrition_source": "manual"},
        headers=csrf_headers(db_client),
    )

    assert response.json()["nutrition"]["glycemic_index"] is None


async def test_weryfikacja_bez_kompletu_wartosci_daje_422(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await login(db_client, admin.email)

    response = await db_client.post(
        f"{PRODUCTS}/{product.id}/verify", headers=csrf_headers(db_client)
    )

    assert response.status_code == 422
    assert "kcal_100" in response.json()["error"]["details"]["missing"]


async def test_admin_weryfikuje_produkt_z_kompletem_wartosci(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 3 i 9: po uzupełnieniu wartości produkt znika z kolejki weryfikacji."""
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await login(db_client, admin.email)
    await db_client.put(
        f"{PRODUCTS}/{product.id}/nutrition",
        json=FULL_NUTRITION,
        headers=csrf_headers(db_client),
    )

    response = await db_client.post(
        f"{PRODUCTS}/{product.id}/verify", headers=csrf_headers(db_client)
    )

    assert response.status_code == 200
    assert response.json()["verification_status"] == VerificationStatus.VERIFIED.value
    assert response.json()["verified_at"] is not None

    queue = await db_client.get(PRODUCTS, params={"verification_status": "unverified"})
    assert queue.json()["total"] == 0
    assert len(await _audit_entries(db_client, "product.verify")) == 1


# --- archiwizacja i usuwanie --------------------------------------------------------


async def test_archiwizacja_ukrywa_produkt_z_list_i_da_sie_cofnac(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 6: archiwizacja jest odwracalna i wypycha produkt z pickerów (ADR-012)."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await login(db_client, user.email)

    archived = await db_client.post(
        f"{PRODUCTS}/{product.id}/archive", headers=csrf_headers(db_client)
    )
    assert archived.status_code == 200
    assert archived.json()["is_archived"] is True

    assert (await db_client.get(PRODUCTS)).json()["total"] == 0
    assert (await db_client.get(PRODUCTS, params={"include_archived": True})).json()["total"] == 1

    restored = await db_client.delete(
        f"{PRODUCTS}/{product.id}/archive", headers=csrf_headers(db_client)
    )
    assert restored.json()["is_archived"] is False
    assert (await db_client.get(PRODUCTS)).json()["total"] == 1


async def test_admin_usuwa_nieuzywany_produkt(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await login(db_client, admin.email)

    response = await db_client.delete(f"{PRODUCTS}/{product.id}", headers=csrf_headers(db_client))

    assert response.status_code == 204
    assert (await db_client.get(f"{PRODUCTS}/{product.id}")).status_code == 404


async def test_usuniecie_uzywanego_produktu_zwraca_kontrakt_used_in(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Kontrakt 409 dla UI („Używane w:") — konsument symulowany, mechanizm prawdziwy."""
    admin = await create_admin(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await login(db_client, admin.email)

    async def finder(_session: AsyncSession, _product_id: int) -> Sequence[UsedInRef]:
        return [UsedInRef(type="recipe", id=7, name="Gołąbki")]

    register_product_reference_finder(finder)
    try:
        response = await db_client.delete(
            f"{PRODUCTS}/{product.id}", headers=csrf_headers(db_client)
        )
    finally:
        unregister_product_reference_finder(finder)

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "conflict"
    assert error["details"]["used_in"] == [{"type": "recipe", "id": 7, "name": "Gołąbki"}]


# --- przeliczniki jednostek domowych --------------------------------------------------


async def test_uzytkownik_zarzadza_przelicznikami(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 7: CRUD przeliczników jest dostępny dla zwykłego użytkownika."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await login(db_client, user.email)

    created = await db_client.post(
        f"{PRODUCTS}/{product.id}/unit-weights",
        json={"unit_label": " Łyżka ", "grams_per_unit": "12.00", "source": "pomiar"},
        headers=csrf_headers(db_client),
    )
    assert created.status_code == 201
    # Etykieta zapisana kanonicznie, żeby UNIQUE łapał „Łyżka" i „łyżka ".
    assert created.json()["unit_label"] == "łyżka"
    assert created.json()["grams_per_unit"] == "12.00"

    weight_id = created.json()["id"]
    updated = await db_client.patch(
        f"{PRODUCTS}/{product.id}/unit-weights/{weight_id}",
        json={"grams_per_unit": "15.00"},
        headers=csrf_headers(db_client),
    )
    assert updated.json()["grams_per_unit"] == "15.00"

    removed = await db_client.delete(
        f"{PRODUCTS}/{product.id}/unit-weights/{weight_id}",
        headers=csrf_headers(db_client),
    )
    assert removed.status_code == 204
    assert (await db_client.get(f"{PRODUCTS}/{product.id}/unit-weights")).json()["total"] == 0


async def test_duplikat_jednostki_daje_409(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await create_unit_weight(db_session, product=product, unit_label="łyżka")
    await login(db_client, user.email)

    response = await db_client.post(
        f"{PRODUCTS}/{product.id}/unit-weights",
        json={"unit_label": "ŁYŻKA", "grams_per_unit": "12.00"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 409


async def test_przelicznik_o_zerowej_gramaturze_jest_odrzucany(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Przelicznik = 0 g uczyniłby ilość nieprzeliczalną w drugą stronę (ADR-005)."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(db_session, category=category)
    await login(db_client, user.email)

    response = await db_client.post(
        f"{PRODUCTS}/{product.id}/unit-weights",
        json={"unit_label": "garść", "grams_per_unit": "0"},
        headers=csrf_headers(db_client),
    )

    assert response.status_code == 422


# --- wyszukiwanie i szczegóły -----------------------------------------------------------


async def test_szukajka_zwraca_produkt_mimo_literowki(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """AC 5 — trigram na poziomie kontraktu HTTP."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    await create_product(db_session, category=category, name="Cebula")
    await login(db_client, user.email)

    response = await db_client.get(PRODUCTS, params={"q": "cebual"})

    assert response.json()["total"] == 1


async def test_szczegoly_produktu_niosa_przeliczniki_i_kategorie(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await create_user(db_session)
    category = await create_category(db_session, name="Warzywa")
    product = await create_product(
        db_session,
        category=category,
        name="Jajko",
        measure_kind=MeasureKind.PIECE,
        piece_weight_g=Decimal("60.00"),
    )
    await create_unit_weight(db_session, product=product, unit_label="garść")
    await login(db_client, user.email)

    body = (await db_client.get(f"{PRODUCTS}/{product.id}")).json()

    assert body["category_name"] == "Warzywa"
    assert body["piece_weight_g"] == "60.00"
    assert body["measure_kind"] == "piece"
    assert [weight["unit_label"] for weight in body["unit_weights"]] == ["garść"]
    assert body["perishability"] == "fresh"


async def test_niepelne_dane_wymieniaja_czego_brakuje(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Plakietka „niepełne dane" w UI ma z czego zbudować tooltip (06_UIUX §3.5)."""
    user = await create_user(db_session)
    category = await create_category(db_session)
    product = await create_product(
        db_session,
        category=category,
        name="Cebula",
        kcal_100=Decimal("40.00"),
        protein_100=Decimal("1.10"),
        fat_100=Decimal("0.10"),
        carbs_100=Decimal("9.30"),
    )
    await login(db_client, user.email)

    completeness = (await db_client.get(f"{PRODUCTS}/{product.id}")).json()["completeness"]

    assert completeness["has_core_macros"] is True
    assert completeness["complete"] is False
    assert completeness["missing"] == ["Cebula: brak indeksu glikemicznego"]
