"""Wspólne prymitywy schematów Pydantic (04_API §1).

Jedyny mieszkaniec na razie: `DecimalString`. Ilości i wartości odżywcze są
w bazie NUMERIC, a w JSON **stringami dziesiętnymi** (`"12.5"`) — inaczej
`json` zamieniłby je na float i po drodze zgubił precyzję (ADR-008).
Moduły domenowe (B04+) używają tego aliasu zamiast własnych serializatorów.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer


def decimal_to_string(value: Decimal) -> str:
    """`Decimal` → tekst bez notacji wykładniczej (`1.00`, nie `1E+0`)."""
    return format(value, "f")


#: Pole Decimal serializowane do JSON jako string; w OpenAPI ma typ `string`,
#: więc `task fe-types` generuje po stronie frontendu `string`, a nie `number`.
DecimalString = Annotated[
    Decimal,
    PlainSerializer(decimal_to_string, return_type=str, when_used="json"),
]
