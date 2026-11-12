"""add ficha table (RP-04)

Revision ID: 9f2c31d8a4b7
Revises: 42a5a427f7c1
Create Date: 2026-11-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9f2c31d8a4b7"
down_revision: str | None = "42a5a427f7c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ficha",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("licitacion_id", sa.Integer(), nullable=False),
        sa.Column("datos", postgresql.JSONB(), nullable=False),
        sa.Column("modelo", sa.String(length=255), nullable=False),
        sa.Column(
            "creada_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("avisos", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["licitacion_id"], ["licitacion.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("licitacion_id"),
    )


def downgrade() -> None:
    op.drop_table("ficha")
