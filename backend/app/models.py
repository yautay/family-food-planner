"""Rejestr modeli — jedyne miejsce, które importuje WSZYSTKIE moduły z tabelami.

`Base.metadata` jest kompletna dopiero po zaimportowaniu modeli. Alembic
(`migrations/env.py`) importuje ten moduł, żeby autogenerate i `compare_type`
widziały cały schemat. Nowy moduł domenowy z tabelami = jedna linia tutaj.
"""

from __future__ import annotations

from app.core.db import Base
from app.modules.accounts import models as accounts_models
from app.modules.audit import models as audit_models
from app.modules.catalog import models as catalog_models
from app.modules.households import models as households_models
from app.modules.nutrition import models as nutrition_models
from app.modules.planning import models as planning_models
from app.modules.recipes import models as recipes_models

__all__ = [
    "Base",
    "accounts_models",
    "audit_models",
    "catalog_models",
    "households_models",
    "nutrition_models",
    "planning_models",
    "recipes_models",
]
