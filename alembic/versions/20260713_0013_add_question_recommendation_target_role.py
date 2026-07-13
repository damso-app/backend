"""add question recommendation target role

Revision ID: 20260713_0013
Revises: 20260708_0012
Create Date: 2026-07-13 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260713_0013"
down_revision: str | Sequence[str] | None = "20260708_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

user_role = postgresql.ENUM(
    "child",
    "mother",
    "father",
    name="user_role",
    create_type=False,
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("question_recommendations")}
    if "target_role" not in columns:
        op.add_column(
            "question_recommendations",
            sa.Column("target_role", user_role, nullable=True),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("question_recommendations")}
    if "target_role" in columns:
        op.drop_column("question_recommendations", "target_role")
