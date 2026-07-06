"""create video_clips and video_clip_ai_results tables

Revision ID: 20260706_0009
Revises: 20260706_0008
Create Date: 2026-07-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260706_0009"
down_revision: str | Sequence[str] | None = "20260706_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "video_clips",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("answer_id", sa.BigInteger(), nullable=False),
        sa.Column("video_url", sa.Text(), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("transcript_segments", postgresql.JSONB(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("one_line_summary", sa.Text(), nullable=True),
        sa.Column("emotion_tags", postgresql.JSONB(), nullable=True),
        sa.Column("fourcut_title", sa.String(length=200), nullable=True),
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
        sa.ForeignKeyConstraint(["answer_id"], ["answers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_video_clips_answer_id",
        "video_clips",
        ["answer_id"],
        unique=True,
    )

    op.create_table(
        "video_clip_ai_results",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("video_clip_id", sa.BigInteger(), nullable=False),
        sa.Column("ai_raw_response", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["video_clip_id"], ["video_clips.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_video_clip_ai_results_video_clip_id",
        "video_clip_ai_results",
        ["video_clip_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_video_clip_ai_results_video_clip_id",
        table_name="video_clip_ai_results",
    )
    op.drop_table("video_clip_ai_results")

    op.drop_index("ux_video_clips_answer_id", table_name="video_clips")
    op.drop_table("video_clips")
