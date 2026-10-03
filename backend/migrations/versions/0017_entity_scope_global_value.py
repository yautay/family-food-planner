"""wartość `global` w typie enumowym `entity_scope` (BATCH_21, D32)

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-03

Przepis dostaje trzeci zakres, `global` — widoczny dla każdego zalogowanego,
zarządzany wyłącznie przez ADMIN-a (decyzja **D32**, rewizja ADR-006). Typ
`entity_scope` (utworzony w `0006`) współdzielą ośmiu konsumentów, ale kod
przyznaje nową wartość wyłącznie `recipes` (enum `RecipeScope`); CHECK-i, które
to egzekwują w bazie, dokłada KOLEJNA rewizja (`0018`).

**Dlaczego ta rewizja zawiera WYŁĄCZNIE `ADD VALUE`** i dlaczego robi to w
`autocommit_block`: `migrations/env.py` wykonuje CAŁE `upgrade head` w jednej
transakcji, a w PostgreSQL nowej wartości enuma nie wolno UŻYĆ przed commitem
transakcji, która ją dodała — ani w CHECK-u, ani w indeksie częściowym, ani w
wierszu. `autocommit_block` zatwierdza to, co migracje zrobiły dotąd, wykonuje
`ALTER TYPE` poza transakcją i otwiera nową — więc `0018` (i każda kolejna)
widzi `global` jako wartość już zatwierdzoną. Test jednoprzebiegowy z `upgrade
head` od zera TEGO nie wykryje (typ utworzony w tej samej transakcji bywa z
ograniczenia zwolniony); dlatego istnieje test dwustopniowy
`test_migracja_0017_na_istniejacej_bazie_z_wierszami`.

`IF NOT EXISTS` — rewizja jest powtarzalna: ponowny `upgrade` po
częściowym `downgrade` (który wartości nie usuwa) nie może się wywrócić.

**Migracja jest NIEODWRACALNA w sensie danych**: PostgreSQL nie ma
`ALTER TYPE … DROP VALUE`, więc `downgrade` jest świadomym no-opem. Typ z
dodatkową wartością jest nieszkodliwy dla starego kodu, dopóki żaden wiersz jej
nie niesie — a CHECK-i z `0018` (zdejmowane jej `downgrade`) to właśnie
pilnują. Po cofnięciu do `0016` wiersze `recipes` z `scope='global'` zostają
NIECZYTELNE dla starego kodu (jego enum `Scope` nie zna tej wartości): **przed
cofnięciem zmień ich zakres albo przywróć dump** zrobiony przez deploy tuż przed
migracją (ADR-017, `deploy/README.md`). Pełne `downgrade base` działa, bo
`0006` kasuje cały typ razem z jego wartościami.

Rola produkcyjna `ffp_user` (NOSUPERUSER) jest WŁAŚCICIELEM typu (utworzyła go
w `0006`), a `ALTER TYPE … ADD VALUE` wymaga właśnie własności typu — migracja
jest więc wykonalna bez operatora klastra.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Dodaj `global` do `entity_scope` poza transakcją migracji."""
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE entity_scope ADD VALUE IF NOT EXISTS 'global'")


def downgrade() -> None:
    """No-op: PostgreSQL nie potrafi usunąć wartości enuma.

    Wiersze z `scope='global'` zostają po cofnięciu nieczytelne dla starego
    kodu — przed `downgrade` zmień ich zakres albo przywróć dump (patrz
    docstring modułu). `downgrade base` i tak kasuje cały typ w `0006`.
    """
