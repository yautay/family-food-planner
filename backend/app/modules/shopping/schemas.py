"""Schematy request/response modułu shopping (04_API §1-2).

Trzy zasady, z których wynika kształt tych schematów:

1. **Ilości w JSON to stringi dziesiętne** (`DecimalString`, ADR-008) — frontend
   nie liczy na floatach, a OpenAPI dostaje typ `string`, więc `task fe-types`
   generuje po stronie TS `string`.
2. **`use_pantry` nigdy nie jest domyślnie włączone.** Brak pola znaczy „nie
   odejmuj" (02_DOMAIN §8): odejmowanie stanu domowego wymaga jawnej decyzji,
   a nie zapomnienia o parametrze.
3. **Preview NIE ma własnego zapisu w bazie** — jest wynikiem silnika liczonym
   z `params`. Dlatego tu są wyłącznie schematy ODCZYTU preview; nie ma
   żadnego „PreviewUpdateRequest".
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.core.schemas import DecimalString
from app.core.scope import Scope
from app.modules.catalog.models import Perishability
from app.modules.catalog.units import AmountUnit
from app.modules.shopping.engine import IssueKind, IssueSeverity, RoundMode
from app.modules.shopping.models import GenerationStatus

__all__ = [
    "AcceptToPantryResponse",
    "FinalizeResponse",
    "GenerateRequest",
    "GenerationRead",
    "ListItemUpdateRequest",
    "ListSectionRead",
    "ListUpdateRequest",
    "PreviewIssueRead",
    "PreviewLineRead",
    "PreviewRoundRead",
    "PublicListItemRead",
    "PublicListItemUpdateRequest",
    "PublicListRead",
    "ResolveRequest",
    "RetailChoiceInput",
    "RetailOptionRead",
    "RoundConfigCreateRequest",
    "RoundConfigListResponse",
    "RoundConfigRead",
    "RoundConfigUpdateRequest",
    "ShareCreateRequest",
    "ShareRead",
    "ShoppingListDetailRead",
    "ShoppingListItemRead",
    "ShoppingListRead",
    "ShoppingListStatus",
    "ShoppingListSummaryRead",
    "ShoppingListsResponse",
]

RoundName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
#: 0 = poniedziałek, 6 = niedziela — konwencja `date.weekday()` (karta B10).
Weekday = Annotated[int, Field(ge=0, le=6)]
#: Okno tury w dniach; rok to sufit oczywistej pomyłki, nie reguła domenowa.
DaysWindow = Annotated[int, Field(ge=1, le=366)]


class RoundConfigRead(BaseModel):
    """Tura zakupowa w odczycie."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    #: `0` = poniedziałek, `6` = niedziela (jak `date.weekday()` w Pythonie).
    shopping_weekday: int | None
    covers_days: int
    #: Na ile dni kupujemy świeże — tylko w trybie `durable_plus_fresh_window`.
    fresh_days: int | None
    mode: RoundMode
    position: int
    scope: Scope
    owner_user_id: int
    household_id: int | None
    created_at: datetime
    updated_at: datetime


class RoundConfigListResponse(BaseModel):
    """Lista tur. Bez paginacji — tur jest kilka, nie tysiące."""

    items: list[RoundConfigRead]
    total: int


class RoundConfigCreateRequest(BaseModel):
    """Nowa tura. `fresh_days` ma znaczenie wyłącznie w trybie z oknem świeżych."""

    name: RoundName
    mode: RoundMode
    covers_days: DaysWindow
    fresh_days: DaysWindow | None = None
    shopping_weekday: Weekday | None = None
    position: int | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def _fresh_window_needs_mode(self) -> Self:
        """Okno świeżych bez trybu, który go używa, byłoby martwym ustawieniem."""
        if self.fresh_days is not None and self.mode is not RoundMode.DURABLE_PLUS_FRESH_WINDOW:
            raise ValueError("Okno świeżych ustawia się tylko w trybie „trwałe + okno świeżych”.")
        if self.fresh_days is not None and self.fresh_days > self.covers_days:
            raise ValueError("Okno świeżych nie może być dłuższe niż zakres tury.")
        return self


class RoundConfigUpdateRequest(BaseModel):
    """Częściowa edycja tury; pole pominięte zostaje bez zmian."""

    name: RoundName | None = None
    mode: RoundMode | None = None
    covers_days: DaysWindow | None = None
    fresh_days: DaysWindow | None = None
    shopping_weekday: Weekday | None = None
    position: int | None = Field(default=None, ge=0, le=100)
    #: `true` czyści dzień zakupów (kolumna jest NULLABLE, więc `null` w PATCH-u
    #: byłby nieodróżnialny od „nie zmieniaj").
    clear_shopping_weekday: bool = False
    clear_fresh_days: bool = False


class GenerateRequest(BaseModel):
    """Wejście generacji: zakres dat, decyzja o spiżarni, opcjonalny wybór tur."""

    date_from: date
    date_to: date
    #: JAWNA zgoda na odjęcie stanu domowego. Brak pola = brak odejmowania.
    use_pantry: bool = False
    #: `null` = wszystkie tury z konfiguracji; pusta lista = jedna tura zastępcza.
    round_config_ids: list[int] | None = None

    @model_validator(mode="after")
    def _range_ordered(self) -> Self:
        if self.date_from > self.date_to:
            raise ValueError("Data „od” nie może być późniejsza niż data „do”.")
        return self


class RetailChoiceInput(BaseModel):
    """Wybór wariantu sklepowego dla produktu (także po inline create)."""

    product_id: int = Field(ge=1)
    retail_product_id: int = Field(ge=1)


class ResolveRequest(BaseModel):
    """Decyzje użytkownika w preview.

    Pole POMINIĘTE zostaje bez zmian, pole PODANE zastępuje cały zbiór —
    frontend wysyła pełny stan zaznaczeń, bo różnica nie umiałaby wyrazić
    odznaczenia.
    """

    already_have: list[int] | None = None
    retail_choices: list[RetailChoiceInput] | None = None
    dismissed_issues: list[str] | None = None


class RetailOptionRead(BaseModel):
    """Wariant sklepowy do wyboru w pozycji preview."""

    retail_product_id: int
    label: str
    package_amount: DecimalString
    package_unit: AmountUnit
    store_id: int | None
    store_name: str | None


class PreviewLineRead(BaseModel):
    """Pozycja preview: produkt w konkretnej turze, z opakowaniami i resztką."""

    round_key: str
    product_id: int
    label: str
    amount_unit: AmountUnit
    #: Potrzeba PO odjęciu spiżarni.
    needed_amount: DecimalString
    #: Potrzeba przed odjęciem — UI pokazuje oba, żeby odjęcie było widoczne.
    raw_amount: DecimalString
    category_id: int | None
    category_name: str | None
    perishability: Perishability | None
    days: list[date]
    from_pantry_amount: DecimalString | None
    already_have: bool
    retail_product_id: int | None
    retail_label: str | None
    package_amount: DecimalString | None
    packages_count: int | None
    #: „Zostanie: 150 g" — resztka jest zawsze eksponowana (02_DOMAIN §9.3).
    leftover_amount: DecimalString | None
    retail_options: list[RetailOptionRead]


class PreviewRoundRead(BaseModel):
    """Tura w preview razem z oknem, które pokryła, i sugerowanym dniem zakupów."""

    key: str
    name: str
    mode: RoundMode
    shopping_weekday: int | None
    shopping_date: date | None
    date_from: date | None
    date_to: date | None
    items: list[PreviewLineRead]


class PreviewIssueRead(BaseModel):
    """Niejasność: `blocker` wstrzymuje finalizację, `warning` tylko informuje."""

    key: str
    kind: IssueKind
    severity: IssueSeverity
    message: str
    dismissed: bool
    product_id: int | None
    plan_item_id: int | None
    pantry_item_id: int | None


class GenerationRead(BaseModel):
    """Generacja razem z policzonym preview — odpowiedź `generate`/`GET`/`resolve`.

    Świadomie BEZ `from_attributes`: `rounds` i `issues` nie są kolumnami
    `shopping_generations` (preview liczy silnik), więc schemat składa router.
    """

    id: int
    date_from: date
    date_to: date
    use_pantry: bool
    status: GenerationStatus
    scope: Scope
    owner_user_id: int
    household_id: int | None
    rounds: list[PreviewRoundRead]
    issues: list[PreviewIssueRead]
    #: JAWNE wybory wariantów (produkt → wariant). UI musi je znać, bo `resolve`
    #: zastępuje cały zbiór: wysłanie wariantów dobranych automatem zamroziłoby
    #: je jako decyzje użytkownika.
    retail_choices: list[RetailChoiceInput]
    #: Czy coś blokuje finalizację — UI wyłącza tym przycisk „Utwórz listy".
    has_blockers: bool
    created_at: datetime
    updated_at: datetime


class ShoppingListItemRead(BaseModel):
    """Pozycja utworzonej listy zakupowej (pełny widok listy dostarcza BATCH_11)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    product_id: int | None
    retail_product_id: int | None
    label: str
    needed_amount: DecimalString
    amount_unit: AmountUnit
    packages_count: int | None
    package_size: DecimalString | None
    leftover_amount: DecimalString | None
    already_have: bool
    from_pantry_amount: DecimalString | None
    checked: bool
    #: Moment OSTATNIEJ decyzji o checkboxie (także odznaczenia) — ustawia go
    #: serwer, a LWW z ADR-009 porównuje właśnie tę wartość (B12).
    checked_at: datetime | None
    #: Moment przyjęcia pozycji do spiżarni; `None` = jeszcze nieprzyjęta (D19).
    #: W odpowiedzi PUBLICZNEJ tego pola NIE MA — osoba z linkiem nie ma nic
    #: wiedzieć o spiżarni rodziny (02_DOMAIN §13.5).
    received_at: datetime | None
    position: int


class ShoppingListRead(BaseModel):
    """Lista zakupowa utworzona przez finalizację.

    `public_token` świadomie NIE JEST tu wystawiany: kolumna istnieje od tej
    migracji, ale udostępnianie należy do BATCH_11 (karta B10 §Security).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    generation_id: int | None
    name: str
    round_name: str | None
    store_id: int | None
    expires_at: datetime
    items: list[ShoppingListItemRead]


class FinalizeResponse(BaseModel):
    """Wynik finalizacji: listy per tura, w kolejności tur."""

    items: list[ShoppingListRead]
    total: int


# --- listy zakupowe: pełny widok, edycja, udostępnianie (BATCH_11) ---------------------


class ShoppingListStatus(StrEnum):
    """Filtr listy list. `expired` NIE znaczy „usunięta" — D10: historia zostaje."""

    ACTIVE = "active"
    EXPIRED = "expired"


class ShareRead(BaseModel):
    """Publiczny link listy (ADR-010).

    `url` jest ŚCIEŻKĄ (`/l/{token}`), nie adresem absolutnym: backend nie wie,
    pod jaką domeną stoi reverse proxy, a frontend zna `window.location.origin`
    (karta B11, Implementation Notes pkt 7).
    """

    url: str
    expires_at: datetime
    revoked: bool


class ShareCreateRequest(BaseModel):
    """Udostępnienie listy: ważność w dniach (default 7 — ADR-010)."""

    expires_in_days: int = Field(default=7, ge=1, le=365)


class ShoppingListSummaryRead(BaseModel):
    """Lista na liście list — bez pozycji, z licznikiem odhaczonych."""

    id: int
    generation_id: int | None
    name: str
    round_name: str | None
    store_id: int | None
    store_name: str | None
    expires_at: datetime
    items_total: int
    items_checked: int
    share: ShareRead | None
    created_at: datetime


class ShoppingListsResponse(BaseModel):
    items: list[ShoppingListSummaryRead]
    total: int


class ListSectionRead(BaseModel):
    """Sekcja listy: kategoria i jej pozycje w kolejności przejścia po sklepie."""

    category_id: int
    category_name: str
    items: list[ShoppingListItemRead]


class ShoppingListDetailRead(BaseModel):
    """Lista z pozycjami POSORTOWANYMI w sekcje (karta B11 §Backend „Sortowanie").

    Sekcje składa serwer, a nie przeglądarka: kolejność zależy od profilu sklepu
    (`store_category_order`, B09) i od globalnych pozycji kategorii, więc gdyby
    układał ją frontend, ta sama lista wyglądałaby inaczej na papierze i na
    publicznym linku.
    """

    id: int
    generation_id: int | None
    name: str
    round_name: str | None
    store_id: int | None
    store_name: str | None
    expires_at: datetime
    share: ShareRead | None
    sections: list[ListSectionRead]
    created_at: datetime
    updated_at: datetime


class ListUpdateRequest(BaseModel):
    """Edycja listy: nazwa i sklep (profil sortowania). Pominięte = bez zmian."""

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] | (
        None
    ) = None
    store_id: int | None = Field(default=None, ge=1)
    #: `true` odpina sklep (kolumna jest NULLABLE, więc `null` byłby
    #: nieodróżnialny od „nie zmieniaj") — wzorzec z `RoundConfigUpdateRequest`.
    clear_store: bool = False


class ListItemUpdateRequest(BaseModel):
    """Odhaczenie i „mam już w domu"; `checked_at` opcjonalnie od klienta (ADR-009).

    Innych pól tu nie ma z rozmysłem: pozycja jest wynikiem generacji, a jej
    ilości zmienia się nową generacją (karta B11 §Out of Scope pkt 4).

    `checked_at` przysyła WYŁĄCZNIE kolejka offline (B12): odhaczenie zrobione
    w sklepie bez zasięgu trafia na serwer minuty później, więc bez znacznika
    z momentu decyzji LWW rozstrzygałoby konflikt na korzyść telefonu, który
    pierwszy złapał sieć, a nie tego, który odhaczył później. Pole pominięte =
    zachowanie dotychczasowe, czyli czas serwera.
    """

    checked: bool | None = None
    already_have: bool | None = None
    #: Wymagana strefa czasowa (`AwareDatetime`): porównanie z kolumną
    #: `timestamptz` musi mieć jednoznaczny punkt w czasie, a nie „lokalną
    #: godzinę czyjegoś telefonu".
    checked_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _something_to_change(self) -> Self:
        if self.checked is None and self.already_have is None:
            raise ValueError("Podaj przynajmniej jedno pole do zmiany.")
        return self


class AcceptToPantryResponse(BaseModel):
    """Ile pozycji weszło do spiżarni: nowe wiersze, dolane, pominięte i już przyjęte.

    `already_received` doszło ADDYTYWNIE w B12 (D19) — `skipped` zachowuje
    znaczenie z R3 („odhaczone, ale nie jest zakupem albo nie ma czego dolać").
    """

    created: int
    increased: int
    skipped: int
    #: Pozycje pominięte, bo mają już `received_at` — zakupy wchodzą do spiżarni raz.
    already_received: int = 0


# --- ścieżka publiczna: BIAŁA LISTA pól (ADR-010, niezmiennik 02_DOMAIN §13.5) --------


class PublicListItemRead(BaseModel):
    """Pozycja listy w widoku publicznym.

    Ten schemat jest jawną BIAŁĄ LISTĄ i nie ma `from_attributes`: gdyby
    powstawał z encji, dołożenie kolumny do `shopping_list_items` mogłoby po
    cichu wypchnąć dane rodziny na publiczną stronę. Zbiór kluczy odpowiedzi
    pilnuje test `test_public_response_has_no_pii`.
    """

    id: int
    label: str
    amount: DecimalString
    unit: AmountUnit
    category_name: str
    checked: bool
    leftover_amount: DecimalString | None
    already_have: bool
    packages_count: int | None
    package_size: DecimalString | None


class PublicListRead(BaseModel):
    """Publiczna treść listy: nazwa, ważność, pozycje. Żadnych danych rodziny."""

    name: str
    expires_at: datetime
    items: list[PublicListItemRead]


class PublicListItemUpdateRequest(BaseModel):
    """Uprawnienia tokenu: `checked` + znacznik czasu tej decyzji (ADR-009/010).

    `model_config` z `extra="forbid"` jest tu zabezpieczeniem, nie ozdobą: próba
    przemycenia `already_have` albo ilości ma skończyć się 422, a nie cichym
    zignorowaniem pola (karta B11 §Security).

    `checked_at` NIE poszerza uprawnień tokenu: nadal da się zmienić wyłącznie
    checkbox, a znacznik mówi tylko, KIEDY ta zmiana zapadła. Bez niego lista
    odhaczona offline nadpisywałaby świeższe decyzje z drugiego telefonu.
    """

    model_config = ConfigDict(extra="forbid")

    checked: bool
    checked_at: AwareDatetime | None = None
