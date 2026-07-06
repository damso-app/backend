"""create question answer loop tables

Revision ID: 20260706_0007
Revises: 20260706_0006
Create Date: 2026-07-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260706_0007"
down_revision: str | Sequence[str] | None = "20260706_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


question_depth = postgresql.ENUM(
    "tiny",
    "medium",
    "deep",
    name="question_depth",
    create_type=False,
)
question_recommendation_status = postgresql.ENUM(
    "active",
    "archived",
    name="question_recommendation_status",
    create_type=False,
)
question_send_source = postgresql.ENUM(
    "recommendation",
    "custom",
    name="question_send_source",
    create_type=False,
)
question_send_status = postgresql.ENUM(
    "sent",
    "answered",
    "cancelled",
    "expired",
    name="question_send_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    question_depth.create(bind, checkfirst=True)
    question_recommendation_status.create(bind, checkfirst=True)
    question_send_source.create(bind, checkfirst=True)
    question_send_status.create(bind, checkfirst=True)

    op.create_table(
        "question_recommendations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("depth", question_depth, nullable=False),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column(
            "status",
            question_recommendation_status,
            server_default="active",
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_question_recommendations_depth_status",
        "question_recommendations",
        ["depth", "status"],
    )

    op.create_table(
        "question_sends",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("sender_user_id", sa.BigInteger(), nullable=False),
        sa.Column("recipient_user_id", sa.BigInteger(), nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("depth", question_depth, nullable=False),
        sa.Column("source", question_send_source, nullable=False),
        sa.Column("recommendation_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", question_send_status, server_default="sent", nullable=False),
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
        sa.ForeignKeyConstraint(["family_id"], ["families.id"]),
        sa.ForeignKeyConstraint(["recommendation_id"], ["question_recommendations.id"]),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_question_sends_family_sent_at",
        "question_sends",
        ["family_id", "sent_at"],
    )
    op.create_index(
        "ix_question_sends_recipient_status",
        "question_sends",
        ["recipient_user_id", "status"],
    )
    op.create_index(
        "ix_question_sends_sender_status",
        "question_sends",
        ["sender_user_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_question_sends_sender_status", table_name="question_sends")
    op.drop_index("ix_question_sends_recipient_status", table_name="question_sends")
    op.drop_index("ix_question_sends_family_sent_at", table_name="question_sends")
    op.drop_table("question_sends")

    op.drop_index(
        "ix_question_recommendations_depth_status",
        table_name="question_recommendations",
    )
    op.drop_table("question_recommendations")

    bind = op.get_bind()
    question_send_status.drop(bind, checkfirst=True)
    question_send_source.drop(bind, checkfirst=True)
    question_recommendation_status.drop(bind, checkfirst=True)
    question_depth.drop(bind, checkfirst=True)
