"""add perfil_empresa and decision tables (RP-06)

Revision ID: 7c1e2f9a4d83
Revises: 9f2c31d8a4b7
Create Date: 2026-11-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7c1e2f9a4d83"
down_revision: str | None = "9f2c31d8a4b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "perfil_empresa",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("datos", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "decision",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("licitacion_id", sa.Integer(), nullable=False),
        sa.Column(
            "resultado",
            sa.Enum("GO", "NO-GO", "REVISAR", name="resultado_decision"),
            nullable=False,
        ),
        sa.Column("razones", postgresql.JSONB(), nullable=False),
        sa.Column("resumen", sa.Text(), nullable=True),
        sa.Column(
            "creada_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["licitacion_id"], ["licitacion.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("decision")
    op.drop_table("perfil_empresa")
