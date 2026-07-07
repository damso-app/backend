"""update user agreement types

Revision ID: 20260708_0011
Revises: 20260706_0010
Create Date: 2026-07-08 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260708_0011"
down_revision: str | Sequence[str] | None = "20260706_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        op.execute(
            "UPDATE user_agreements "
            "SET agreement_type = 'service_terms' "
            "WHERE agreement_type = 'terms_of_service'"
        )
        op.execute(
            "UPDATE user_agreements "
            "SET agreement_type = 'camera_microphone' "
            "WHERE agreement_type = 'camera_microphone_notice'"
        )
        return

    op.execute("ALTER TYPE agreement_type RENAME TO agreement_type_old")
    op.execute(
        "CREATE TYPE agreement_type AS ENUM "
        "('service_terms', 'privacy_policy', 'camera_microphone', 'data_usage')"
    )
    op.execute(
        "ALTER TABLE user_agreements "
        "ALTER COLUMN agreement_type TYPE agreement_type "
        "USING CASE agreement_type::text "
        "WHEN 'terms_of_service' THEN 'service_terms' "
        "WHEN 'camera_microphone_notice' THEN 'camera_microphone' "
        "ELSE agreement_type::text END::agreement_type"
    )
    op.execute("DROP TYPE agreement_type_old")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        op.execute("DELETE FROM user_agreements WHERE agreement_type = 'data_usage'")
        op.execute(
            "UPDATE user_agreements "
            "SET agreement_type = 'terms_of_service' "
            "WHERE agreement_type = 'service_terms'"
        )
        op.execute(
            "UPDATE user_agreements "
            "SET agreement_type = 'camera_microphone_notice' "
            "WHERE agreement_type = 'camera_microphone'"
        )
        return

    op.execute("DELETE FROM user_agreements WHERE agreement_type = 'data_usage'")
    op.execute("ALTER TYPE agreement_type RENAME TO agreement_type_new")
    op.execute(
        "CREATE TYPE agreement_type AS ENUM "
        "('terms_of_service', 'privacy_policy', 'camera_microphone_notice')"
    )
    op.execute(
        "ALTER TABLE user_agreements "
        "ALTER COLUMN agreement_type TYPE agreement_type "
        "USING CASE agreement_type::text "
        "WHEN 'service_terms' THEN 'terms_of_service' "
        "WHEN 'camera_microphone' THEN 'camera_microphone_notice' "
        "ELSE agreement_type::text END::agreement_type"
    )
    op.execute("DROP TYPE agreement_type_new")
