"""add ai_job_id to answers

Revision ID: 20260706_0010
Revises: 20260706_0009
Create Date: 2026-07-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260706_0010"
down_revision: str | Sequence[str] | None = "20260706_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "answers",
        sa.Column("ai_job_id", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("answers", "ai_job_id")
