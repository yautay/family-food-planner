"""retail i sklepy — warianty sklepowe oraz profile kolejności kategorii (BATCH_09)

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-21

Zakres wg 03_DATABASE §3: `stores`, `store_category_order`, `retail_products`.
Żadna z tych tabel nie ma kolumn wzorca scope — to słownik GLOBALNY instancji
(02_DOMAIN §3.1 pkt 3 i 4), więc nie ma tu ani `entity_scope`, ani CHECK-a
`scope_requires_household`.

Trzy decyzje warte zapisania:

1. **`package_unit` reużywa typu `amount_unit`** z migracji `0006` (recipes) —
   `postgresql.ENUM(..., create_type=False)`. Dziedzina wartości jest ta sama
   (`g|ml|piece`), a osobny typ „package_unit" byłby jej duplikatem, którego
   nikt by nie trzymał w zgodzie. Dlatego `downgrade()` też go NIE kasuje:
   typ należy do `0006`.
2. **`store_category_order` kasuje się kaskadą z obu stron.** Profil jest
   atrybutem sklepu (kompozycja rodzic→dziecko, ADR-012), a kategoria usunięta
   ze słownika nie ma prawa blokować sklepu — samą kategorię chroni 409 od
   strony produktów (`delete_category`).
3. **`retail_products.store_id` ma SET NULL, a nie RESTRICT** (03_DATABASE §3):
   wariant bez sklepu jest dozwolonym stanem, a wielkość opakowania zostaje
   prawdziwa nawet po likwidacji sieci. Fizyczne usunięcie używanego sklepu
   i tak blokuje serwis 409-ką z listą użyć.

CHECK-ów `package_amount > 0` ani `pieces_per_package >= 1` tu NIE MA: schemat
z 03_DATABASE §3 ich nie definiuje, a dokument jest wiążący (ta sama zasada co
w `0010` dla `amount >= 0`). Pilnują ich schematy Pydantic i serwis.

REKONCYLIACJA Z BATCH_08: migracja `0010` utworzyła `pantry_items` z kolumną
`retail_product_id BIGINT NULL` BEZ constraintu FK, bo `retail_products` jeszcze
nie istniało (karta B08, Implementation Notes pkt 1; karta B09 §Context). B08
zmergował się pierwszy, więc constraint dopina TA migracja — od tej chwili
pozycja spiżarni blokuje usunięcie wariantu sklepowego (RESTRICT, ADR-012),
a licznik referencji dla czytelnej 409-ki rejestruje `pantry/service.py`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Typ z migracji `0006` — TYLKO referencja, nigdy tworzenie ani kasowanie.
AMOUNT_UNIT = postgresql.ENUM("g", "ml", "piece", name="amount_unit", create_type=False)

#: Nazwa odroczonego constraintu z B08 — jedna literówka i downgrade nie zadziała.
#: Zapisana wprost (bez `op.f`, które na poziomie modułu nie ma jeszcze proxy);
#: wywołania owijają ją w `op.f`, żeby alembic nie przepuścił jej przez
#: `naming_convention` po raz drugi.
PANTRY_RETAIL_FK = "fk_pantry_items_retail_product_id_retail_products"


def upgrade() -> None:
    """Tworzy sklepy, profile kolejności kategorii i warianty sklepowe."""
    op.create_table(
        "stores",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("color", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stores")),
        sa.UniqueConstraint("name", name=op.f("uq_stores_name")),
    )

    op.create_table(
        "store_category_order",
        sa.Column("store_id", sa.BigInteger(), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
            name=op.f("fk_store_category_order_store_id_stores"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["product_categories.id"],
            name=op.f("fk_store_category_order_category_id_product_categories"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("store_id", "category_id", name=op.f("pk_store_category_order")),
    )

    op.create_table(
        "retail_products",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("canonical_product_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("store_id", sa.BigInteger(), nullable=True),
        sa.Column("package_amount", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("package_unit", AMOUNT_UNIT, nullable=False),
        sa.Column("pieces_per_package", sa.Integer(), nullable=True),
        sa.Column("photo_path", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # RESTRICT: produkt kanoniczny użyty w wariancie sklepowym nie znika
        # (ADR-012, 02_DOMAIN §13.4) — licznik referencji jest w `retail_service`.
        sa.ForeignKeyConstraint(
            ["canonical_product_id"],
            ["canonical_products.id"],
            name=op.f("fk_retail_products_canonical_product_id_canonical_products"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
            name=op.f("fk_retail_products_store_id_stores"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retail_products")),
    )
    # 03_DATABASE §3 wymienia ten indeks wprost: najczęstsze zapytanie to
    # „warianty retail TEGO produktu kanonicznego" (karta produktu, silnik B10).
    op.create_index(
        "ix_retail_products_canonical_product_id", "retail_products", ["canonical_product_id"]
    )
    # Filtr `?store_id=` i FK SET NULL bez indeksu skanowałyby całą tabelę.
    op.create_index("ix_retail_products_store_id", "retail_products", ["store_id"])

    # Rekoncyliacja z B08 (patrz docstring): kolumna istnieje od `0010`, dopinamy
    # jej brakujący constraint dopiero teraz, gdy jest do czego się odwołać.
    op.create_foreign_key(
        op.f(PANTRY_RETAIL_FK),
        "pantry_items",
        "retail_products",
        ["retail_product_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Kasuje warianty, profile i sklepy; typ `amount_unit` zostaje (należy do `0006`)."""
    # Najpierw odroczony FK — inaczej `retail_products` nie da się usunąć.
    op.drop_constraint(op.f(PANTRY_RETAIL_FK), "pantry_items", type_="foreignkey")

    op.drop_index("ix_retail_products_store_id", table_name="retail_products")
    op.drop_index("ix_retail_products_canonical_product_id", table_name="retail_products")
    op.drop_table("retail_products")
    op.drop_table("store_category_order")
    op.drop_table("stores")
