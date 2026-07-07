"""normalize family invite codes

Revision ID: 20260708_0012
Revises: 20260708_0011
Create Date: 2026-07-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260708_0012"
down_revision: str | Sequence[str] | None = "20260708_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE families "
        "SET invite_code = replace(replace(upper(invite_code), '-', ''), ' ', '') "
        "WHERE invite_code IS NOT NULL"
    )
    op.alter_column(
        "families",
        "invite_code",
        existing_type=sa.String(length=7),
        type_=sa.String(length=6),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "families",
        "invite_code",
        existing_type=sa.String(length=6),
        type_=sa.String(length=7),
        existing_nullable=True,
    )
    op.execute(
        "UPDATE families "
        "SET invite_code = substring(invite_code from 1 for 3) || '-' "
        "|| substring(invite_code from 4 for 3) "
        "WHERE invite_code IS NOT NULL AND length(invite_code) = 6"
    )
