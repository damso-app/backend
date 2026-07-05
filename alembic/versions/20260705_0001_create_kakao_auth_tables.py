"""create kakao auth tables

Revision ID: 20260705_0001
Revises:
Create Date: 2026-07-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260705_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


user_role = postgresql.ENUM("child", "parent", name="user_role", create_type=False)
user_status = postgresql.ENUM("active", "disabled", name="user_status", create_type=False)
oauth_provider = postgresql.ENUM("kakao", name="oauth_provider", create_type=False)
login_code_status = postgresql.ENUM(
    "active",
    "used",
    "expired",
    name="login_code_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    user_role.create(bind, checkfirst=True)
    user_status.create(bind, checkfirst=True)
    oauth_provider.create(bind, checkfirst=True)
    login_code_status.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=True),
        sa.Column("role", user_role, nullable=True),
        sa.Column("status", user_status, server_default="active", nullable=False),
        sa.Column("role_selected_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_role_status", "users", ["role", "status"], unique=False)
    op.create_index("ux_users_public_id", "users", ["public_id"], unique=True)

    op.create_table(
        "social_accounts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", oauth_provider, nullable=False),
        sa.Column("provider_user_id", sa.String(length=191), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("profile_image_url", sa.Text(), nullable=True),
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
    op.create_index("ix_social_accounts_user_id", "social_accounts", ["user_id"], unique=False)
    op.create_index(
        "ux_social_accounts_provider_user",
        "social_accounts",
        ["provider", "provider_user_id"],
        unique=True,
    )

    op.create_table(
        "oauth_login_codes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("code_hash", sa.String(length=255), nullable=False),
        sa.Column("status", login_code_status, server_default="active", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_oauth_login_codes_expires_at",
        "oauth_login_codes",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_oauth_login_codes_user_status",
        "oauth_login_codes",
        ["user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ux_oauth_login_codes_code_hash",
        "oauth_login_codes",
        ["code_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_oauth_login_codes_code_hash", table_name="oauth_login_codes")
    op.drop_index("ix_oauth_login_codes_user_status", table_name="oauth_login_codes")
    op.drop_index("ix_oauth_login_codes_expires_at", table_name="oauth_login_codes")
    op.drop_table("oauth_login_codes")

    op.drop_index("ux_social_accounts_provider_user", table_name="social_accounts")
    op.drop_index("ix_social_accounts_user_id", table_name="social_accounts")
    op.drop_table("social_accounts")

    op.drop_index("ux_users_public_id", table_name="users")
    op.drop_index("ix_users_role_status", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    login_code_status.drop(bind, checkfirst=True)
    oauth_provider.drop(bind, checkfirst=True)
    user_status.drop(bind, checkfirst=True)
    user_role.drop(bind, checkfirst=True)
