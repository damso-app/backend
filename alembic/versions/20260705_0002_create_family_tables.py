"""create family tables

Revision ID: 20260705_0002
Revises: 20260705_0001
Create Date: 2026-07-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260705_0002"
down_revision: str | Sequence[str] | None = "20260705_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


family_status = postgresql.ENUM(
    "active",
    "archived",
    name="family_status",
    create_type=False,
)
family_member_role = postgresql.ENUM(
    "child",
    "parent",
    "member",
    name="family_member_role",
    create_type=False,
)
family_member_status = postgresql.ENUM(
    "active",
    "invited",
    "left",
    "removed",
    name="family_member_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    family_status.create(bind, checkfirst=True)
    family_member_role.create(bind, checkfirst=True)
    family_member_status.create(bind, checkfirst=True)

    op.create_table(
        "families",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", family_status, server_default="active", nullable=False),
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
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_families_created_by_user_id", "families", ["created_by_user_id"])
    op.create_index("ix_families_status", "families", ["status"])
    op.create_index("ux_families_public_id", "families", ["public_id"], unique=True)

    op.create_table(
        "family_members",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("family_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("member_role", family_member_role, nullable=False),
        sa.Column("status", family_member_status, server_default="active", nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_family_members_family_status",
        "family_members",
        ["family_id", "status"],
    )
    op.create_index(
        "ix_family_members_user_status",
        "family_members",
        ["user_id", "status"],
    )
    op.create_index(
        "ux_family_members_family_user",
        "family_members",
        ["family_id", "user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_family_members_family_user", table_name="family_members")
    op.drop_index("ix_family_members_user_status", table_name="family_members")
    op.drop_index("ix_family_members_family_status", table_name="family_members")
    op.drop_table("family_members")

    op.drop_index("ux_families_public_id", table_name="families")
    op.drop_index("ix_families_status", table_name="families")
    op.drop_index("ix_families_created_by_user_id", table_name="families")
    op.drop_table("families")

    bind = op.get_bind()
    family_member_status.drop(bind, checkfirst=True)
    family_member_role.drop(bind, checkfirst=True)
    family_status.drop(bind, checkfirst=True)
