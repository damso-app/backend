"""add user profile image url

Revision ID: 20260705_0003
Revises: 20260705_0002
Create Date: 2026-07-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260705_0003"
down_revision: str | Sequence[str] | None = "20260705_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("profile_image_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "profile_image_url")
