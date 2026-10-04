"""Weryfikacja narzędzia `/pdf-extract` prawdziwym kodem aplikacji (BATCH_22, D31 pkt 4 i 8).

Każdy przypadek reguły jednostek to realny błąd, który wyszedł dopiero przy ręcznej
analizie `dieta.pdf` (karta B22, „Wnioski z ręcznej analizy”).
"""

from __future__ import annotations

import copy
from decimal import Decimal
from typing import Any

import pytest

from app.modules.catalog.units import AmountUnit, normalize_amount
from scripts.pdf_extract.catalog_index import build_index, resolve_catalog
from scripts.pdf_extract.spec import IngredientSpec, Spec, SpecError, Thresholds, parse_spec
from scripts.pdf_extract.verify import (
    IngredientError,
    check_product_values,
    mentioned_but_missing,
    product_measure,
    resolve_ingredient,
    verify_spec,
)
from tests.pdf_extract_fixtures import (
    BUTTER,
    EGG,
    FLOUR,
    MILK,
    MUSHROOMS,
    version_one,
    version_one_payload,
    version_two,
)

pytestmark = pytest.mark.unit

THRESHOLDS = Thresholds()


def _product(payload: dict[str, Any]) -> Any:
    return parse_spec(
        {
            **version_one_payload(),
            "products": [copy.deepcopy(payload)],
            "recipes": [
                {
                    "day": "pon",
                    "meal": "obiad",
                    "name": "X",
                    "ingredients": [{"product": payload["key"], "pdf_qty": "1", "pdf_unit": "g"}],
                }
            ],
            "pdf_day_totals": {},
            "pdf_shopping_list_grams": {},
        }
    ).products[0]


def _ingredient(key: str, qty: str, unit: str, grams: str | None, **extra: Any) -> IngredientSpec:
    return IngredientSpec.model_validate(
        {"product": key, "pdf_qty": qty, "pdf_unit": unit, "pdf_grams": grams, **extra}
    )


def test_sztuka_przy_produkcie_spoza_piece_zapisuje_gramy_z_notatka() -> None:
    """„5 x Sztuka” pieczarek (MASS) → gramy; surowy zapis dałby 422 przy edycji w UI."""
    product = _product(MUSHROOMS)
    resolution = resolve_ingredient(
        "R", _ingredient("pieczarki", "5", "Sztuka", "100"), product, THRESHOLDS
    )
    assert (resolution.mode, resolution.display_unit, resolution.display_qty) == (
        "grams",
        "g",
        Decimal("100"),
    )
    assert resolution.note == "5 x sztuka"
    assert "sztuka" in (resolution.reason or "")
    # Ten zapis przechodzi normalize_amount — to jest sens reguły.
    normalized = normalize_amount(
        resolution.display_qty, resolution.display_unit, product_measure(product)
    )
    assert (normalized.amount, normalized.unit) == (resolution.amount, AmountUnit.GRAM)


def test_lyzka_poza_progiem_zapisuje_gramy_a_oryginal_w_note() -> None:
    """Łyżka mąki = 10 g, PDF podaje 20 g (odchyłka 50%) → gramy + „1 x łyżka” w note."""
    resolution = resolve_ingredient(
        "R", _ingredient("maka", "1", "Łyżka", "20"), _product(FLOUR), THRESHOLDS
    )
    assert resolution.mode == "grams"
    assert (resolution.display_qty, resolution.display_unit, resolution.note) == (
        Decimal("20"),
        "g",
        "1 x łyżka",
    )
    assert resolution.home_basis == Decimal("10")
    assert resolution.deviation_pct == Decimal("-50.0")


def test_lyzka_w_progu_zostaje_jednostka_domowa() -> None:
    """Łyżka mąki 10 g vs PDF 10,5 g (≈5%) → jednostka z PDF-a, bez notatki."""
    resolution = resolve_ingredient(
        "R", _ingredient("maka", "1", "Łyżka", "10.5"), _product(FLOUR), THRESHOLDS
    )
    assert resolution.mode == "pdf_unit"
    assert (resolution.display_unit, resolution.display_qty, resolution.note) == (
        "łyżka",
        Decimal("1"),
        "",
    )
    assert (resolution.amount, resolution.amount_unit) == (Decimal("10"), AmountUnit.GRAM)


def test_sztuka_przy_produkcie_piece_zostaje_w_sztukach() -> None:
    """Jajko (PIECE 50 g): 2 sztuki = 100 g = PDF → `szt.`, ilość w sztukach."""
    resolution = resolve_ingredient(
        "R", _ingredient("jajko", "2", "Sztuka", "100"), _product(EGG), THRESHOLDS
    )
    assert (resolution.mode, resolution.display_unit) == ("pdf_unit", "szt.")
    assert (resolution.amount, resolution.amount_unit) == (Decimal("2"), AmountUnit.PIECE)
    assert resolution.basis_amount == Decimal("100")  # oś wartości: gramy


def test_sztuka_piece_z_rozna_waga_niz_pdf_zapisuje_gramy() -> None:
    """Pomidor 150 vs 170 g w PDF-ie: waga sztuki różni się od PDF-a ponad próg → gramy."""
    egg = _product(EGG)  # 50 g/szt.
    resolution = resolve_ingredient("R", _ingredient("jajko", "1", "Sztuka", "70"), egg, THRESHOLDS)
    assert resolution.mode == "grams"
    assert resolution.note == "1 x sztuka"


def test_jednostka_bez_przelicznika_zapisuje_gramy() -> None:
    """„Garść” bez przelicznika przy produkcie → gramy (inaczej `normalize_amount` rzuci)."""
    resolution = resolve_ingredient(
        "R", _ingredient("maka", "1", "Garść", "30"), _product(FLOUR), THRESHOLDS
    )
    assert resolution.mode == "grams"
    assert "przelicznika" in (resolution.reason or "")


def test_gramy_z_pdf_dla_produktu_volume_zapisane_jako_ml() -> None:
    """VOLUME: g → ml nie istnieje w modelu, więc gramy PDF-a idą jako ml (gęstość ≈ 1)."""
    milk = _product(MILK)
    resolution = resolve_ingredient("R", _ingredient("mleko", "300", "g", "300"), milk, THRESHOLDS)
    assert (resolution.mode, resolution.display_unit, resolution.amount_unit) == (
        "grams",
        "ml",
        AmountUnit.MILLILITER,
    )
    assert "gęstość" in (resolution.reason or "")


def test_brak_gramow_w_pdf_przy_wymaganym_fallbacku_to_blad() -> None:
    with pytest.raises(IngredientError, match="nie podaje"):
        resolve_ingredient(
            "R", _ingredient("pieczarki", "5", "Sztuka", None), _product(MUSHROOMS), THRESHOLDS
        )


def test_reczny_nakaz_write_as_grams() -> None:
    resolution = resolve_ingredient(
        "R",
        _ingredient("maka", "1", "Łyżka", "10", write_as="grams"),
        _product(FLOUR),
        THRESHOLDS,
    )
    assert resolution.mode == "grams"
    assert "ręczny" in (resolution.reason or "")


def test_kazdy_zapis_przechodzi_normalize_amount_na_zapisana_ilosc() -> None:
    """Niezmiennik, który wywala UI: (display_qty, display_unit) → (amount, amount_unit)."""
    spec = version_one()
    resolved = resolve_catalog(spec, build_index({}))
    report = verify_spec(spec, resolved.products)
    assert report.ok, report.errors
    for item in report.ingredients:
        product = resolved.products[item.product]
        normalized = normalize_amount(item.display_qty, item.display_unit, product_measure(product))
        assert normalized.unit == item.amount_unit
        assert abs(normalized.amount - item.amount) <= Decimal("0.001")


def test_wersja_syntetyczna_przechodzi_weryfikacje_i_sumy_zgadzaja_sie() -> None:
    """Sumy posiłków i dnia policzone silnikiem = „PDF”, lista zakupów = Σ składników."""
    spec = version_one()
    resolved = resolve_catalog(spec, build_index({}))
    report = verify_spec(spec, resolved.products)
    assert report.ok
    kcal = {meal.label.split(": ")[1]: meal.computed.kcal for meal in report.meals}
    assert kcal == {
        "Naleśniki testowe": Decimal("325"),
        "Omlet z pieczarkami testowy": Decimal("223"),
    }
    assert report.days[0].computed.kcal == Decimal("548")
    assert all(check.severity is None for check in report.shopping)
    grams = [item for item in report.ingredients if item.mode == "grams"]
    assert {(item.recipe, item.product) for item in grams} == {
        ("Omlet z pieczarkami testowy", "pieczarki"),
        ("Omlet z pieczarkami testowy", "maka"),
    }


def test_posilek_powyzej_progow_daje_ostrzezenie_a_potem_blad() -> None:
    """kcal posiłku: >10% = ostrzeżenie, >15% = błąd; dzień z błędem posiłku też odstaje."""

    def severity(pdf_kcal: str) -> str | None:
        payload = version_one_payload()
        payload["recipes"][0]["pdf_totals"] = {"kcal": pdf_kcal}
        spec = parse_spec(payload)
        report = verify_spec(spec, resolve_catalog(spec, build_index({})).products)
        return report.meals[0].severity

    assert severity("325") is None
    assert severity("290") == "warning"  # silnik 325 vs 290 ≈ +12,1%
    assert severity("270") == "error"  # ≈ +20,4%


def test_dzien_przekraczajacy_progi_kcal_jest_bledem_a_makro_ostrzezeniem() -> None:
    payload = version_one_payload()
    payload["pdf_day_totals"] = {"pon": {"kcal": "500", "protein": "30"}}
    spec = parse_spec(payload)
    report = verify_spec(spec, resolve_catalog(spec, build_index({})).products)
    codes = {(issue.level, issue.code) for issue in report.issues}
    assert ("error", "day_total") in codes  # kcal 548 vs 500 ≈ +9,6% > 5%
    assert not report.ok
    assert report.days[0].severity == "error"


def test_progi_sa_konfigurowalne_w_spec() -> None:
    payload = version_one_payload()
    payload["recipes"][0]["pdf_totals"] = {"kcal": "290"}
    payload["thresholds"] = {"meal_warning_pct": "20", "meal_error_pct": "30"}
    spec = parse_spec(payload)
    report = verify_spec(spec, resolve_catalog(spec, build_index({})).products)
    assert report.meals[0].severity is None


def test_lista_zakupow_wykrywa_brakujacy_skladnik_i_odchylke_silnika() -> None:
    """Σ składników PDF-a ≠ lista PDF-a → błąd danych; Σ silnika poza ±5% → błąd."""
    payload = version_one_payload()
    payload["pdf_shopping_list_grams"]["jajko"] = "200"
    spec = parse_spec(payload)
    report = verify_spec(spec, resolve_catalog(spec, build_index({})).products)
    codes = {issue.code for issue in report.issues if issue.level == "error"}
    assert {"shopping_pdf_sum", "shopping_engine_sum"} <= codes


def test_produkt_na_liscie_zakupow_bez_przepisu_i_odwrotnie() -> None:
    payload = version_one_payload()
    del payload["pdf_shopping_list_grams"]["mleko"]
    spec = parse_spec(payload)
    report = verify_spec(spec, resolve_catalog(spec, build_index({})).products)
    assert any(issue.code == "not_on_shopping_list" for issue in report.warnings)


def test_ta_sama_nazwa_przepisu_w_innej_wersji_jest_bledem() -> None:
    """Import reużyłby stary przepis i pominął nowe składniki (D22)."""
    spec = version_one()
    resolved = resolve_catalog(spec, build_index({}))
    report = verify_spec(
        spec, resolved.products, known_recipe_names={"naleśniki testowe": "0007-inna"}
    )
    assert any(issue.code == "recipe_name_taken" for issue in report.errors)


def test_energia_produktu_musi_zgadzac_sie_z_makroskladnikami() -> None:
    """kcal ≈ 4B+4W+9T (±20% albo ±10 kcal); wartość z sufitu nie wejdzie do paczki."""
    assert check_product_values(_product(FLOUR)) == []
    wrong = copy.deepcopy(FLOUR)
    wrong["per_100"] = {**wrong["per_100"], "kcal": "700"}
    issues = check_product_values(_product(wrong))
    assert [issue.code for issue in issues] == ["nutrition_energy"]
    assert issues[0].level == "error"


def test_cukry_ponad_weglowodany_to_ostrzezenie() -> None:
    odd = copy.deepcopy(BUTTER)
    odd["per_100"] = {**odd["per_100"], "sugars": "5"}
    issues = check_product_values(_product(odd))
    assert [issue.code for issue in issues] == ["nutrition_sugars"]


def test_instrukcja_wspomina_produkt_ktorego_nie_ma_na_liscie() -> None:
    """Heurystyka z odmianą: „mąkę” w instrukcji, a składnika „mąka” brak."""
    spec = version_two()
    resolved = resolve_catalog(spec, build_index({"0001-syntetyczny": version_one()}))
    payload = spec.model_dump(mode="json")
    payload["recipes"][0]["ingredients"] = [
        item for item in payload["recipes"][0]["ingredients"] if item["product"] != "maka"
    ]
    recipe = parse_spec({**payload, "pdf_shopping_list_grams": {}}).recipes[0]
    missing = mentioned_but_missing(recipe, resolved.products)
    assert [product.key for product in missing] == ["maka"]


def test_pusta_instrukcja_to_ostrzezenie() -> None:
    payload = version_one_payload()
    payload["recipes"][0]["instructions"] = ""
    spec = parse_spec(payload)
    report = verify_spec(spec, resolve_catalog(spec, build_index({})).products)
    assert any(issue.code == "empty_instructions" for issue in report.warnings)


def test_silnik_dostaje_wartosci_tylko_z_adaptera_produktu() -> None:
    """Weryfikacja nie liczy kcal po swojemu: moduł nie sięga po kolumny ani po `float`."""
    from pathlib import Path

    import scripts.pdf_extract.verify as verify_module

    source = Path(verify_module.__file__).read_text(encoding="utf-8")
    assert "canonical_products" not in source
    assert "kcal_100 *" not in source
    assert "ingredient_nutrition" in source and "to_basis_amount" in source


def test_wiele_wersji_produkt_reuzyty_liczy_sie_jak_w_definicji() -> None:
    """Wersja 0002: mąka z 0001 (łyżka = 10 g) → 2 łyżki = 20 g w bazie."""
    spec: Spec = version_two()
    resolved = resolve_catalog(spec, build_index({"0001-syntetyczny": version_one()}))
    report = verify_spec(spec, resolved.products)
    assert report.ok, report.errors
    flour = next(item for item in report.ingredients if item.product == "maka")
    assert (flour.mode, flour.amount, flour.amount_unit) == (
        "pdf_unit",
        Decimal("20"),
        AmountUnit.GRAM,
    )


def test_blad_skladnika_nie_generuje_falszywych_bledow_posilku_i_dnia() -> None:
    """Pominięty składnik zaniża sumy — raport ma pokazać JEDEN prawdziwy błąd, nie kaskadę."""
    payload = version_one_payload()
    # pieczarki (MASS) „Sztuka” bez gramów w PDF-ie: nie da się zapisać w żadnej jednostce
    payload["recipes"][1]["ingredients"][1]["pdf_grams"] = None
    spec = parse_spec(payload)
    report = verify_spec(spec, resolve_catalog(spec, build_index({})).products)
    assert {issue.code for issue in report.errors} >= {"ingredient"}
    assert "meal_kcal" not in {issue.code for issue in report.issues}
    assert "day_total" not in {issue.code for issue in report.issues}
    assert report.meals[1].severity is None
    assert report.days[0].severity is None


def test_odchylka_zero_nie_jest_ujemna() -> None:
    """Ujemne zero po kwantyzacji (-0.04%) wychodzi jako 0, nie „-0” w raporcie."""
    from scripts.pdf_extract.verify import _pct

    value = _pct(Decimal("-0.04"), Decimal("100"))
    assert value == 0
    assert str(value).startswith("-") is False


def test_progi_posilku_musza_byc_uporzadkowane() -> None:
    payload = version_one_payload()
    payload["thresholds"] = {"meal_warning_pct": "20", "meal_error_pct": "10"}
    with pytest.raises(SpecError, match="meal_warning_pct"):
        parse_spec(payload)
