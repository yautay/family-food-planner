"""households_audit — rodziny, profile członków i dziennik operacji (BATCH_03)

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-16

Zakres wg 03_DATABASE §2 i §10: `households`, `member_profiles`, kolumna
`users.household_id` (ALTER — tabela `users` istnieje od `0002`) oraz
`audit_entries`.

Świadomie NIE powstaje tu typ enumowy `entity_scope` ani żadna tabela
z kolumnami wzorca scope (03_DATABASE §4): pierwszą produkcyjną encją ze
scope jest `recipes` w BATCH_05 i to jego migracja tworzy typ. Encja testowa
`scoped_notes` (macierz uprawnień) powstaje wyłącznie w bazie testowej przez
`create_all` w conftest — migracja produkcyjna nie może jej tworzyć.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Tworzy `households`, `member_profiles`, `audit_entries` i `users.household_id`."""
    op.create_table(
        "households",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_households")),
    )

    op.create_table(
        "member_profiles",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("household_id", sa.BigInteger(), nullable=True),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        # Mnożnik porcji i cel kcal to NUMERIC (ADR-008) — nigdy float.
        sa.Column(
            "default_multiplier",
            sa.Numeric(precision=4, scale=2),
            nullable=False,
            server_default=sa.text("1.0"),
        ),
        sa.Column("kcal_goal", sa.Numeric(precision=6, scale=0), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_member_profiles_household_id_households"),
            ondelete="CASCADE",
        ),
        # Usunięcie konta nie kasuje profilu — osoba nadal je w tej rodzinie
        # (02_DOMAIN §3: profil może istnieć bez konta).
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_member_profiles_owner_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_member_profiles")),
    )
    op.create_index(
        "ix_member_profiles_household_id", "member_profiles", ["household_id"], unique=False
    )
    op.create_index(
        "ix_member_profiles_owner_user_id", "member_profiles", ["owner_user_id"], unique=False
    )

    op.create_table(
        "audit_entries",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # Historia operacji przeżywa usunięcie konta, które je wykonało.
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_audit_entries_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_entries")),
    )
    op.create_index("ix_audit_entries_user_id", "audit_entries", ["user_id"], unique=False)
    op.create_index(
        "ix_audit_entries_entity_type_entity_id",
        "audit_entries",
        ["entity_type", "entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_entries_created_at",
        "audit_entries",
        [sa.text("created_at DESC")],
        unique=False,
    )

    # ALTER na istniejącej tabeli `users` — FK dopiero teraz ma dokąd wskazywać.
    op.add_column("users", sa.Column("household_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        op.f("fk_users_household_id_households"),
        "users",
        "households",
        ["household_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_users_household_id", "users", ["household_id"], unique=False)


def downgrade() -> None:
    """Cofa kolumnę `users.household_id` i wszystkie tabele tego batcha."""
    op.drop_index("ix_users_household_id", table_name="users")
    op.drop_constraint(op.f("fk_users_household_id_households"), "users", type_="foreignkey")
    op.drop_column("users", "household_id")

    op.drop_index("ix_audit_entries_created_at", table_name="audit_entries")
    op.drop_index("ix_audit_entries_entity_type_entity_id", table_name="audit_entries")
    op.drop_index("ix_audit_entries_user_id", table_name="audit_entries")
    op.drop_table("audit_entries")

    op.drop_index("ix_member_profiles_owner_user_id", table_name="member_profiles")
    op.drop_index("ix_member_profiles_household_id", table_name="member_profiles")
    op.drop_table("member_profiles")

    op.drop_table("households")
