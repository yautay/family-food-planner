"""Blokada usuwania encji będących w użyciu — jeden kontrakt dla całego systemu.

ADR-012: encji użytej gdziekolwiek NIE usuwamy fizycznie. Serwis liczy
referencje PRZED usunięciem i przy wyniku > 0 zwraca 409 z listą miejsc użycia,
którą UI pokazuje jako „Używane w: …" (06_UIUX §3.3). Kształt ustalony
w BATCH_03 i obowiązujący każdą encję od BATCH_04:

    {"error": {"code": "conflict", "message": "…", "details":
        {"used_in": [{"type": "recipe", "id": 7, "name": "Gołąbki"}]}}}

Helper mieszka w `core`, a nie w module katalogu, bo z tego kontraktu korzystają
wszystkie moduły domenowe (przepisy, plany, spiżarnia, listy) — gdyby siedział
w `catalog/service.py`, każdy z nich importowałby cudzy moduł domenowy tylko po
to, żeby zgłosić konflikt.

DRUGA LINIA OBRONY jest obowiązkowa: FK domenowe mają `ON DELETE RESTRICT`,
więc gdyby jakiś konsument nie zarejestrował swojego licznika referencji, commit
poleci `IntegrityError`. Bez `conflict_from_integrity_error` użytkownik dostałby
wtedy 500 zamiast czytelnego 409.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.core.errors import ConflictError

#: Maksymalna długość listy „Używane w:" w odpowiedzi 409 — jedna wartość dla
#: całego kontraktu (katalog, przepisy, kolejni konsumenci); pełna lista przy
#: popularnej encji byłaby nieczytelna, a UI i tak pokazuje pierwsze pozycje.
USED_IN_LIMIT = 20


@dataclass(frozen=True)
class UsedInRef:
    """Jedno miejsce użycia encji — `type` jest nazwą encji, nie etykietą UI."""

    type: str
    id: int
    name: str

    def as_dict(self) -> dict[str, Any]:
        """Postać wchodząca do `details.used_in` (kolejność pól jak w kontrakcie)."""
        return {"type": self.type, "id": self.id, "name": self.name}


def used_in_details(used_in: Sequence[UsedInRef]) -> dict[str, Any]:
    """`details` odpowiedzi 409 — także dla pustej listy (kontrakt ma stały kształt)."""
    return {"used_in": [reference.as_dict() for reference in used_in]}


def assert_deletable(message: str, used_in: Sequence[UsedInRef]) -> None:
    """Przerwij usuwanie z 409, jeśli encja jest gdziekolwiek użyta."""
    if used_in:
        raise ConflictError(message, details=used_in_details(used_in))


def conflict_from_integrity_error(message: str) -> ConflictError:
    """409 dla `IntegrityError` z commita — bez listy użyć, bo baza jej nie zna.

    Zawsze po `session.rollback()`: transakcja jest już nieużywalna.
    """
    return ConflictError(message, details=used_in_details([]))
