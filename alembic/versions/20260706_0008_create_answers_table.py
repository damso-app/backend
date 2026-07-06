"""create answers table

Revision ID: 20260706_0008
Revises: 20260706_0007
Create Date: 2026-07-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260706_0008"
down_revision: str | Sequence[str] | None = "20260706_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


answer_status = postgresql.ENUM(
    "submitted",
    "processing",
    "completed",
    "failed",
    name="answer_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    answer_status.create(bind, checkfirst=True)

    op.create_table(
        "answers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("question_send_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("video_origin_url", sa.Text(), nullable=True),
        sa.Column("video_mime_type", sa.String(length=100), nullable=True),
        sa.Column("video_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("video_size_bytes", sa.Integer(), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("status", answer_status, server_default="submitted", nullable=False),
        sa.Column("ai_retryable", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("ai_fallback_used", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("ai_input_context", postgresql.JSONB(), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["question_send_id"], ["question_sends.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_answers_question_send_id",
        "answers",
        ["question_send_id"],
        unique=True,
    )
    op.create_index(
        "ix_answers_user_submitted_at",
        "answers",
        ["user_id", "submitted_at"],
    )
    op.create_index(
        "ix_answers_family_created_at",
        "answers",
        ["family_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_answers_family_created_at", table_name="answers")
    op.drop_index("ix_answers_user_submitted_at", table_name="answers")
    op.drop_index("ux_answers_question_send_id", table_name="answers")
    op.drop_table("answers")

    bind = op.get_bind()
    answer_status.drop(bind, checkfirst=True)
