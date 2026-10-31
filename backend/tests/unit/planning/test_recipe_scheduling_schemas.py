"""Addytywny kontrakt UX03: wybór posiłku i zamiana wyłącznie przepisu."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.planning.schemas import ItemUpdateRequest, RecipeItemCreateRequest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "meal", [{}, {"meal_id": 1, "new_meal_name": "Obiad"}, {"new_meal_name": " "}]
)
def test_wymaga_dokladnie_jednego_celu_posilku(meal: dict[str, object]) -> None:
    """Brak celu, dwa cele oraz pusta nazwa nie przechodzą walidacji."""
    with pytest.raises(ValidationError):
        RecipeItemCreateRequest.model_validate({"recipe_id": 1, **meal})


def test_nowy_posilek_ma_nazwe_dowolna_i_decimal() -> None:
    """Nazwa jest przycinana, a porcje nie przechodzą przez float."""
    payload = RecipeItemCreateRequest.model_validate(
        {"new_meal_name": "  Późny obiad po spacerze  ", "recipe_id": 1, "servings": "3.30"}
    )
    assert payload.new_meal_name == "Późny obiad po spacerze"
    assert payload.servings == Decimal("3.30")
    assert payload.servings_split == []


@pytest.mark.parametrize("servings", ["0", "-1", "10000", "1.001", "NaN", "Infinity"])
def test_nieprawidlowe_porcje_sa_odrzucane(servings: str) -> None:
    """Nowy zapis dziedziczy dokładność i sufit dotychczasowego ItemCreate."""
    with pytest.raises(ValidationError):
        RecipeItemCreateRequest.model_validate({"meal_id": 1, "recipe_id": 2, "servings": servings})


@pytest.mark.parametrize("recipe_id", [None, 0, -1])
def test_patch_nie_pozwala_usunac_przepisu(recipe_id: int | None) -> None:
    """recipe_id=null nie jest konwersją ani skasowaniem powiązania."""
    with pytest.raises(ValidationError):
        ItemUpdateRequest.model_validate({"recipe_id": recipe_id})


def test_patch_sam_przepis_nie_dopisuje_porcji() -> None:
    """Pominięte servings/split pozostają pominięte i zachowują zapisany podział."""
    assert ItemUpdateRequest(recipe_id=2).model_dump(exclude_unset=True) == {"recipe_id": 2}


@pytest.mark.parametrize("multiplier", ["0", "100", "1.001"])
def test_podzial_ma_te_same_granice_co_dotychczas(multiplier: str) -> None:
    """Dodatni multiplier do 99,99 jest wspólnym kontraktem planowania."""
    with pytest.raises(ValidationError):
        RecipeItemCreateRequest.model_validate(
            {
                "meal_id": 1,
                "recipe_id": 2,
                "servings_split": [{"member_profile_id": 1, "multiplier": multiplier}],
            }
        )
