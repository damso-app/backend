"""create user agreements

Revision ID: 20260706_0004
Revises: 20260705_0003
Create Date: 2026-07-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260706_0004"
down_revision: str | Sequence[str] | None = "20260705_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


agreement_type = postgresql.ENUM(
    "terms_of_service",
    "privacy_policy",
    "camera_microphone_notice",
    name="agreement_type",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    agreement_type.create(bind, checkfirst=True)

    op.create_table(
        "user_agreements",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("agreement_type", agreement_type, nullable=False),
        sa.Column("agreed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("agreed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_agreements_user_agreed",
        "user_agreements",
        ["user_id", "agreed"],
    )
    op.create_index(
        "ux_user_agreements_user_type",
        "user_agreements",
        ["user_id", "agreement_type"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_user_agreements_user_type", table_name="user_agreements")
    op.drop_index("ix_user_agreements_user_agreed", table_name="user_agreements")
    op.drop_table("user_agreements")

    bind = op.get_bind()
    agreement_type.drop(bind, checkfirst=True)
