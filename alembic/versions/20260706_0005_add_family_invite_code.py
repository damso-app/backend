"""add family invite code

Revision ID: 20260706_0005
Revises: 20260706_0004
Create Date: 2026-07-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260706_0005"
down_revision: str | Sequence[str] | None = "20260706_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("families", sa.Column("invite_code", sa.String(length=7), nullable=True))
    op.create_index("ux_families_invite_code", "families", ["invite_code"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_families_invite_code", table_name="families")
    op.drop_column("families", "invite_code")
