"""Schematy modułu planning (04_API §1-2): plan dnia, posiłki, pozycje, kopiowanie.

Zasady kontraktu:

- każda liczba NUMERIC wychodzi jako string dziesiętny (`DecimalString`, ADR-008),
- pole `nutrition` ma jeden kształt w całym API (`NutritionRead` z modułu
  nutrition) — wartości ZAWSZE liczy silnik, nigdy baza (02_DOMAIN §13.2),
- pozycja to przepis ALBO produkt luzem: pilnuje tego walidator schematu,
  a niezależnie od niego CHECK w bazie,
- ilość produktu luzem podaje się tak, jak w przepisie: `quantity` + `unit`
  (etykieta użytkownika); normalizację na g/ml/szt. robi serwis (ADR-005).

Od BATCH_07 mieszka tu również kontrakt payloadu szablonów (`v:1`) oraz schematy
cykli i kopiowania bloku — sekcje na końcu pliku.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.schemas import DecimalString
from app.core.scope import Scope
from app.modules.catalog.units import AmountUnit
from app.modules.nutrition.schemas import GoalMetricRead, NutritionRead
from app.modules.nutrition.types import GoalStatus

__all__ = [
    "MEALS_PER_DAY_LIMIT",
    "TEMPLATE_PAYLOAD_VERSION",
    "CycleApplyRequest",
    "CycleListResponse",
    "CycleRead",
    "CycleWriteRequest",
    "DayGoalProgressRead",
    "DayRead",
    "DayTemplatePayload",
    "DayTemplateReadFull",
    "DayTemplateWriteRequest",
    "DaysResponse",
    "FitToTargetResponse",
    "InstantiateDayRequest",
    "InstantiateResponse",
    "InstantiateWeekRequest",
    "ItemCreateRequest",
    "ItemUpdateRequest",
    "MealCreateRequest",
    "MealRead",
    "MealUpdateRequest",
    "PlanCopyRequest",
    "PlanDayUpsertRequest",
    "PlanItemRead",
    "PlanServingSplitInput",
    "PlanServingSplitRead",
    "TemplateItemPayload",
    "TemplateListResponse",
    "TemplateMealPayload",
    "TemplateSplitPayload",
    "TemplateSummaryRead",
    "WeekTemplateDayPayload",
    "WeekTemplatePayload",
    "WeekTemplateReadFull",
    "WeekTemplateWriteRequest",
]

MealName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
DayTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
UnitLabel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]

#: Mnożnik porcji — skala kolumny `plan_meal_items.servings` NUMERIC(6,2).
Servings = Annotated[
    Decimal, Field(gt=Decimal("0"), le=Decimal("9999.99"), max_digits=6, decimal_places=2)
]
#: Mnożnik jednej osoby w rozkładzie rodzinnym — NUMERIC(4,2).
SplitMultiplier = Annotated[
    Decimal, Field(gt=Decimal("0"), le=Decimal("99.99"), max_digits=4, decimal_places=2)
]
#: Ilość produktu luzem w jednostce użytkownika — jak `quantity` składnika przepisu.
ItemQuantity = Annotated[
    Decimal, Field(gt=Decimal("0"), le=Decimal("99999.999"), max_digits=8, decimal_places=3)
]
#: Cel kcal posiłku — NUMERIC(6,0).
MealKcalTarget = Annotated[Decimal, Field(gt=Decimal("0"), le=Decimal("99999"), decimal_places=0)]
Position = Annotated[int, Field(ge=0, le=10_000)]

#: Sufit posiłków dnia i pozycji posiłku — plan dnia to plan, nie import danych.
MEALS_PER_DAY_LIMIT = 50
#: Ile dat naraz przyjmuje `/plan/copy` (miesiąc z zapasem).
COPY_TARGETS_LIMIT = 62
#: Ile dni źródłowych i ile powtórzeń przyjmuje `what="block"`; iloczyn i tak
#: ogranicza `COPY_TARGETS_LIMIT`, ale osobne sufity dają czytelniejsze 422.
BLOCK_SOURCE_DAYS_LIMIT = 31
BLOCK_REPEAT_LIMIT = 7


# --- rozkład rodzinny ---------------------------------------------------------------


class PlanServingSplitInput(BaseModel):
    """Jedna osoba w rozkładzie porcji. Suma multiplierów musi równać się `servings`."""

    member_profile_id: int = Field(ge=1)
    multiplier: SplitMultiplier


class PlanServingSplitRead(BaseModel):
    """Rozkład w odczycie — z imieniem profilu, żeby UI nie dociągał go osobno."""

    member_profile_id: int
    member_name: str
    multiplier: DecimalString


# --- pozycje ------------------------------------------------------------------------


class ItemCreateRequest(BaseModel):
    """Nowa pozycja posiłku: przepis z mnożnikiem ALBO produkt luzem z ilością."""

    recipe_id: int | None = Field(default=None, ge=1)
    product_id: int | None = Field(default=None, ge=1)
    #: Ilość produktu luzem w jednostce użytkownika (g/kg/ml/l/szt./jednostka domowa).
    quantity: ItemQuantity | None = None
    unit: UnitLabel | None = None
    servings: Servings = Decimal("1")
    servings_split: list[PlanServingSplitInput] = Field(default_factory=list, max_length=20)
    position: Position | None = None

    @model_validator(mode="after")
    def _recipe_xor_product(self) -> Self:
        if (self.recipe_id is None) == (self.product_id is None):
            raise ValueError("Pozycja planu wskazuje albo przepis, albo produkt — dokładnie jedno.")
        if self.product_id is not None and (self.quantity is None or self.unit is None):
            raise ValueError("Podaj ilość i jednostkę produktu.")
        if self.recipe_id is not None and (self.quantity is not None or self.unit is not None):
            raise ValueError("Pozycja z przepisem nie ma ilości — steruje nią mnożnik porcji.")
        return self


class ItemUpdateRequest(BaseModel):
    """Częściowa edycja pozycji. Pola pominięte zostają bez zmian.

    `servings_split` podane jawnie ZASTĘPUJE cały rozkład (pusta lista = brak
    rozkładu); pominięte zostawia go nietkniętym.
    """

    servings: Servings | None = None
    servings_split: list[PlanServingSplitInput] | None = Field(default=None, max_length=20)
    quantity: ItemQuantity | None = None
    unit: UnitLabel | None = None
    position: Position | None = None

    @model_validator(mode="after")
    def _amount_needs_both_parts(self) -> Self:
        if (self.quantity is None) != (self.unit is None):
            raise ValueError("Zmiana ilości wymaga podania i liczby, i jednostki.")
        return self


class PlanItemRead(BaseModel):
    """Pozycja posiłku z wartościami policzonymi przez silnik."""

    id: int
    position: int
    recipe_id: int | None
    recipe_name: str | None
    recipe_photo_thumb_url: str | None
    product_id: int | None
    product_name: str | None
    amount: DecimalString | None
    amount_unit: AmountUnit | None
    servings: DecimalString
    servings_split: list[PlanServingSplitRead]
    nutrition: NutritionRead


# --- posiłki ------------------------------------------------------------------------


class MealCreateRequest(BaseModel):
    """Nowy posiłek dnia — nazwa własna (02_DOMAIN §7), opcjonalny cel kcal."""

    name: MealName
    kcal_target: MealKcalTarget | None = None
    position: Position | None = None


class MealUpdateRequest(BaseModel):
    """Częściowa edycja posiłku. `kcal_target` można wyzerować, podając `null`."""

    name: MealName | None = None
    kcal_target: MealKcalTarget | None = None
    position: Position | None = None
    #: Jawne „usuń cel" — bez tego `null` nie odróżniłby się od „nie ruszaj".
    clear_kcal_target: bool = False


class MealRead(BaseModel):
    """Posiłek z pozycjami, sumą wartości i statusem względem własnego celu kcal."""

    id: int
    name: str
    position: int
    kcal_target: DecimalString | None
    kcal_status: GoalStatus | None
    items: list[PlanItemRead]
    nutrition: NutritionRead


# --- dzień --------------------------------------------------------------------------


class PlanDayUpsertRequest(BaseModel):
    """PUT dnia: tworzy go albo aktualizuje tytuł i widoczność (04_API §2)."""

    title: DayTitle | None = None
    scope: Scope = Scope.PRIVATE


class DayGoalProgressRead(BaseModel):
    """Cztery kafelki widoku 1: wartość/cel/delta/status dla kcal i makro."""

    kcal: GoalMetricRead
    protein_g: GoalMetricRead
    fat_g: GoalMetricRead
    carbs_g: GoalMetricRead


class DayRead(BaseModel):
    """Dzień planu razem z posiłkami, wartościami i postępem względem celu.

    `id` jest `null` dla dnia, którego jeszcze nie ma w bazie: otwarcie pustej
    daty to normalna sytuacja, nie błąd 404 (dzień powstaje przy pierwszym
    posiłku albo przez PUT).
    """

    id: int | None
    day: date
    title: str | None
    scope: Scope
    owner_user_id: int | None
    meals: list[MealRead]
    nutrition: NutritionRead
    goal_progress: DayGoalProgressRead
    #: Data obowiązywania celu użytego do statusów (`null`, gdy celu brak).
    goal_valid_from: date | None
    created_at: datetime | None
    updated_at: datetime | None


class DaysResponse(BaseModel):
    """Dni z zakresu `from`-`to`. Zwracane są WYŁĄCZNIE dni istniejące w bazie."""

    items: list[DayRead]
    total: int


# --- akcje ---------------------------------------------------------------------------


class FitToTargetResponse(BaseModel):
    """Propozycja „dopasuj porcję do celu" — sama propozycja, bez zapisu.

    Zastosowanie jest osobną, jawną akcją użytkownika (`PATCH` pozycji) —
    nic nie zmienia się samo (02_DOMAIN §6).
    """

    item_id: int
    #: Cel kcal posiłku, względem którego liczono propozycję.
    target_kcal: DecimalString
    current_servings: DecimalString
    proposed_servings: DecimalString
    #: Wartości pozycji PO zastosowaniu propozycji (zaokrąglone na wyjściu).
    resulting_nutrition: NutritionRead


class PlanCopyRequest(BaseModel):
    """Kopiowanie dnia na datę/daty albo posiłku do dnia (04_API §2).

    Kopia jest GŁĘBOKA (nowe id posiłków, pozycji i rozkładów) i DOPISUJE się
    do dnia docelowego — istniejących posiłków nie nadpisuje (karta B06).
    """

    what: Literal["day", "meal", "block"]
    #: Wymagane dla `what="day"` — data dnia źródłowego.
    source_date: date | None = None
    #: Wymagane dla `what="meal"` — identyfikator kopiowanego posiłku.
    source_meal_id: int | None = Field(default=None, ge=1)
    #: Wymagane dla `what="day"` i `what="meal"`; dla bloku daty wylicza serwis.
    target_dates: list[date] = Field(default_factory=list, max_length=COPY_TARGETS_LIMIT)
    #: --- tylko `what="block"` (model 2+2+2 z 01_PDF_AUDIT §6) ---
    #: Pierwszy dzień bloku źródłowego.
    source_from: date | None = None
    #: Ile kolejnych dni obejmuje blok.
    source_days: int | None = Field(default=None, ge=1, le=BLOCK_SOURCE_DAYS_LIMIT)
    #: Ile razy pod rząd powtarzany jest każdy dzień bloku (2+2+2 ⇒ 2).
    repeat_each: int | None = Field(default=None, ge=1, le=BLOCK_REPEAT_LIMIT)
    #: Data, od której układany jest wynik.
    target_start: date | None = None

    @model_validator(mode="after")
    def _source_matches_kind(self) -> Self:
        if self.what == "block":
            missing = [
                name
                for name, value in (
                    ("source_from", self.source_from),
                    ("source_days", self.source_days),
                    ("repeat_each", self.repeat_each),
                    ("target_start", self.target_start),
                )
                if value is None
            ]
            if missing:
                raise ValueError(
                    "Powielenie bloku wymaga pól: od kiedy, ile dni, ile powtórzeń i data docelowa."
                )
            # Sufit `target_dates` obowiązuje też blok — inaczej 30 dni x 30
            # powtórzeń zrobiłoby 900 dni planu jednym żądaniem.
            assert self.source_days is not None and self.repeat_each is not None
            if self.source_days * self.repeat_each > COPY_TARGETS_LIMIT:
                raise ValueError(
                    f"Blok dawałby więcej niż {COPY_TARGETS_LIMIT} dni docelowych — "
                    "zmniejsz liczbę dni albo powtórzeń."
                )
            return self

        if not self.target_dates:
            raise ValueError("Podaj przynajmniej jedną datę docelową.")
        if self.what == "day" and self.source_date is None:
            raise ValueError("Podaj datę dnia, który chcesz skopiować.")
        if self.what == "meal" and self.source_meal_id is None:
            raise ValueError("Podaj posiłek, który chcesz skopiować.")
        return self


# --- szablony: kontrakt payloadu `v:1` (BATCH_07, 03_DATABASE §6) --------------------
#
# Payload jest ZAMROŻONĄ KOPIĄ STRUKTURY, nie wyliczonych wartości: trzyma
# `recipe_id`/`product_id` jako referencje do słowników, a wartości odżywcze
# liczy silnik przy każdym odczycie planu (niezmiennik 02_DOMAIN §13.2).
#
# Ilość produktu luzem zapisujemy JUŻ ZNORMALIZOWANĄ (`amount` + `amount_unit`
# na osi produktu), a nie jako `quantity` + etykietę użytkownika. Powód: szablon
# odwzorowuje wiersze `plan_meal_items`, więc instancjacja jest przepisaniem
# wartości, a nie ponowną konwersją — inaczej zmiana przelicznika jednostki
# domowej po zapisaniu szablonu cicho zmieniłaby jego treść (albo wysadziła
# instancjację błędem konwersji).
#
# Pole `v` istnieje od pierwszej wersji: eksport (B14) i ewentualna migracja
# kształtu payloadu będą go potrzebowały. Zmiana kształtu = `v: 2` + konwersja
# przy odczycie, nigdy cicha zmiana znaczenia pól `v: 1`.

#: Wersja kontraktu payloadu. Odczyt szablonu z inną wersją = błąd, nie domysł.
#: Adnotacja `Literal[1]` jest konieczna: pola `v` mają ten typ, a goły `int`
#: nie zawęża się do niego automatycznie.
TEMPLATE_PAYLOAD_VERSION: Literal[1] = 1

TemplateName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]

#: Ile posiłków i pozycji przyjmuje payload — te same sufity, co plan dnia.
TEMPLATE_ITEMS_PER_MEAL_LIMIT = 50
#: Dni tygodnia w szablonie tygodnia (poniedziałek..niedziela).
DAYS_PER_WEEK = 7
#: Ile szablonów może mieć cykl — rotacja A→B→C, nie kalendarz na rok.
CYCLE_TEMPLATES_LIMIT = 26


class TemplateSplitPayload(BaseModel):
    """Rozkład rodzinny pozycji w szablonie — te same pola, co w planie."""

    model_config = ConfigDict(extra="forbid")

    member_profile_id: int = Field(ge=1)
    multiplier: DecimalString = Field(
        gt=Decimal("0"), le=Decimal("99.99"), max_digits=4, decimal_places=2
    )


class TemplateItemPayload(BaseModel):
    """Pozycja posiłku w szablonie: przepis ALBO produkt luzem ze znormalizowaną ilością."""

    model_config = ConfigDict(extra="forbid")

    recipe_id: int | None = Field(default=None, ge=1)
    product_id: int | None = Field(default=None, ge=1)
    #: Ilość na osi produktu (g/ml/szt.) — już po konwersji, jak w `plan_meal_items`.
    amount: DecimalString | None = Field(
        default=None, gt=Decimal("0"), le=Decimal("9999999.999"), max_digits=10, decimal_places=3
    )
    amount_unit: AmountUnit | None = None
    servings: DecimalString = Field(
        default=Decimal("1"), gt=Decimal("0"), le=Decimal("9999.99"), max_digits=6, decimal_places=2
    )
    position: Position = 0
    servings_split: list[TemplateSplitPayload] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _recipe_xor_product(self) -> Self:
        # Te same niezmienniki, co CHECK-i `plan_meal_items` — payload spoza
        # kontraktu musi paść na walidacji, a nie dopiero przy instancjacji.
        if (self.recipe_id is None) == (self.product_id is None):
            raise ValueError(
                "Pozycja szablonu wskazuje albo przepis, albo produkt — dokładnie jedno."
            )
        if self.product_id is not None and (self.amount is None or self.amount_unit is None):
            raise ValueError("Pozycja z produktem musi mieć ilość i jednostkę.")
        if self.recipe_id is not None and (self.amount is not None or self.amount_unit is not None):
            raise ValueError("Pozycja z przepisem nie ma ilości — steruje nią mnożnik porcji.")
        return self


class TemplateMealPayload(BaseModel):
    """Posiłek w szablonie: nazwa, opcjonalny cel kcal, kolejność i pozycje."""

    model_config = ConfigDict(extra="forbid")

    name: MealName
    kcal_target: DecimalString | None = Field(
        default=None, gt=Decimal("0"), le=Decimal("99999"), decimal_places=0
    )
    position: Position = 0
    items: list[TemplateItemPayload] = Field(
        default_factory=list, max_length=TEMPLATE_ITEMS_PER_MEAL_LIMIT
    )


class DayTemplatePayload(BaseModel):
    """Payload szablonu dnia (`v:1`): tytuł dnia + posiłki. Bez ani jednej daty."""

    model_config = ConfigDict(extra="forbid")

    v: Literal[1] = TEMPLATE_PAYLOAD_VERSION
    title: DayTitle | None = None
    meals: list[TemplateMealPayload] = Field(default_factory=list, max_length=MEALS_PER_DAY_LIMIT)


class WeekTemplateDayPayload(BaseModel):
    """Jeden dzień szablonu tygodnia: offset 0-6 od poniedziałku + payload dnia."""

    model_config = ConfigDict(extra="forbid")

    offset: int = Field(ge=0, le=DAYS_PER_WEEK - 1)
    day: DayTemplatePayload


class WeekTemplatePayload(BaseModel):
    """Payload szablonu tygodnia (`v:1`): dni po offsetach, każdy w kształcie dnia."""

    model_config = ConfigDict(extra="forbid")

    v: Literal[1] = TEMPLATE_PAYLOAD_VERSION
    days: list[WeekTemplateDayPayload] = Field(default_factory=list, max_length=DAYS_PER_WEEK)

    @model_validator(mode="after")
    def _offsets_are_unique(self) -> Self:
        offsets = [entry.offset for entry in self.days]
        if len(offsets) != len(set(offsets)):
            raise ValueError("Każdy dzień tygodnia może wystąpić w szablonie tylko raz.")
        return self


# --- szablony: żądania i odpowiedzi -------------------------------------------------


class DayTemplateWriteRequest(BaseModel):
    """POST/PUT szablonu dnia: payload wprost ALBO `from_date` (zbuduj z planu).

    PUT nadpisuje CAŁY payload (03_DATABASE §6) — edycji „per posiłek" nie ma
    i mieć nie będzie; edycją jest plan plus ponowny zapis szablonu.
    """

    name: TemplateName
    scope: Scope = Scope.PRIVATE
    payload: DayTemplatePayload | None = None
    #: „Zapisz ten dzień jako szablon" — serwis zbuduje payload z planu tej daty.
    from_date: date | None = None

    @model_validator(mode="after")
    def _payload_xor_source(self) -> Self:
        if (self.payload is None) == (self.from_date is None):
            raise ValueError("Podaj albo treść szablonu, albo datę dnia, z którego ma powstać.")
        return self


class WeekTemplateWriteRequest(BaseModel):
    """POST/PUT szablonu tygodnia: payload wprost ALBO `from_week_start` (7 dni planu)."""

    name: TemplateName
    scope: Scope = Scope.PRIVATE
    payload: WeekTemplatePayload | None = None
    #: Poniedziałek tygodnia źródłowego — inny dzień tygodnia kończy się 422.
    from_week_start: date | None = None

    @model_validator(mode="after")
    def _payload_xor_source(self) -> Self:
        if (self.payload is None) == (self.from_week_start is None):
            raise ValueError("Podaj albo treść szablonu, albo poniedziałek tygodnia źródłowego.")
        return self


class TemplateSummaryRead(BaseModel):
    """Szablon na liście — bez payloadu (lista szablonów nie jest eksportem)."""

    id: int
    name: str
    scope: Scope
    owner_user_id: int
    #: Ile posiłków (dzień) albo ile dni (tydzień) obejmuje szablon — podpowiedź w UI.
    summary: str
    created_at: datetime
    updated_at: datetime


class DayTemplateReadFull(TemplateSummaryRead):
    """Szablon dnia z payloadem — odczyt pojedynczego szablonu."""

    payload: DayTemplatePayload


class WeekTemplateReadFull(TemplateSummaryRead):
    """Szablon tygodnia z payloadem."""

    payload: WeekTemplatePayload


class TemplateListResponse(BaseModel):
    """Lista szablonów (jeden kształt dla dni i tygodni)."""

    items: list[TemplateSummaryRead]
    total: int


class InstantiateDayRequest(BaseModel):
    """Instancjacja szablonu dnia na wskazane daty (dopisuje, jak `/plan/copy`)."""

    dates: list[date] = Field(min_length=1, max_length=COPY_TARGETS_LIMIT)


class InstantiateWeekRequest(BaseModel):
    """Instancjacja szablonu tygodnia — `week_start` MUSI być poniedziałkiem."""

    week_start: date


class InstantiateResponse(BaseModel):
    """Dni utworzone przez instancjację albo apply cyklu.

    `warnings` niesie ostrzeżenia miękkie (np. zarchiwizowany przepis w payloadzie):
    instancjacja się udała, ale użytkownik powinien wiedzieć, co wpadło do planu.
    Twarde braki (nieistniejący przepis/produkt) kończą się 422, nie ostrzeżeniem.
    """

    items: list[DayRead]
    total: int
    warnings: list[str] = Field(default_factory=list)


# --- cykle tygodni -------------------------------------------------------------------


class CycleWriteRequest(BaseModel):
    """POST/PUT cyklu: nazwa + kolejność szablonów tygodnia (rotacja A→B→C)."""

    name: TemplateName
    scope: Scope = Scope.PRIVATE
    #: Kolejność JEST rotacją; ten sam szablon może wystąpić wielokrotnie
    #: („A, A, B" to legalny cykl: dwa tygodnie A, potem B).
    template_ids: list[int] = Field(min_length=1, max_length=CYCLE_TEMPLATES_LIMIT)
    #: Od którego tygodnia liczy się rotacja; `null` = od pierwszego szablonu.
    start_date: date | None = None


class CycleRead(BaseModel):
    """Cykl w odczycie — z nazwami szablonów, żeby UI nie dociągał ich osobno."""

    id: int
    name: str
    scope: Scope
    owner_user_id: int
    template_ids: list[int]
    #: Nazwy w tej samej kolejności co `template_ids` (brakujący szablon = `null`).
    template_names: list[str | None]
    start_date: date | None
    created_at: datetime
    updated_at: datetime


class CycleListResponse(BaseModel):
    items: list[CycleRead]
    total: int


class CycleApplyRequest(BaseModel):
    """Zastosowanie cyklu na zakres dat. `date_from` MUSI być poniedziałkiem."""

    date_from: date
    date_to: date

    @model_validator(mode="after")
    def _range_is_ordered(self) -> Self:
        if self.date_from > self.date_to:
            raise ValueError("Data „od” nie może być późniejsza niż data „do”.")
        return self
