"""Rejestr modeli — jedyne miejsce, które importuje WSZYSTKIE moduły z tabelami.

`Base.metadata` jest kompletna dopiero po zaimportowaniu modeli. Alembic
(`migrations/env.py`) importuje ten moduł, żeby autogenerate i `compare_type`
widziały cały schemat. Nowy moduł domenowy z tabelami = jedna linia tutaj.
"""

from __future__ import annotations

from app.core.db import Base
from app.modules.accounts import models as accounts_models

__all__ = ["Base", "accounts_models"]
