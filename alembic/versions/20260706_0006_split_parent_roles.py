"""split parent roles into mother and father

Revision ID: 20260706_0006
Revises: 20260706_0005
Create Date: 2026-07-06 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260706_0006"
down_revision: str | Sequence[str] | None = "20260706_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        op.execute("UPDATE users SET role = 'mother' WHERE role = 'parent'")
        op.execute("UPDATE family_members SET member_role = 'mother' WHERE member_role = 'parent'")
        op.execute("UPDATE family_members SET member_role = 'child' WHERE member_role = 'member'")
        return

    op.execute("ALTER TYPE user_role RENAME TO user_role_old")
    op.execute("CREATE TYPE user_role AS ENUM ('child', 'mother', 'father')")
    op.execute(
        "ALTER TABLE users ALTER COLUMN role TYPE user_role "
        "USING CASE role::text "
        "WHEN 'parent' THEN 'mother' "
        "ELSE role::text END::user_role"
    )
    op.execute("DROP TYPE user_role_old")

    op.execute("ALTER TYPE family_member_role RENAME TO family_member_role_old")
    op.execute("CREATE TYPE family_member_role AS ENUM ('child', 'mother', 'father')")
    op.execute(
        "ALTER TABLE family_members "
        "ALTER COLUMN member_role TYPE family_member_role "
        "USING CASE member_role::text "
        "WHEN 'parent' THEN 'mother' "
        "WHEN 'member' THEN 'child' "
        "ELSE member_role::text END::family_member_role"
    )
    op.execute("DROP TYPE family_member_role_old")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        op.execute("UPDATE users SET role = 'parent' WHERE role IN ('mother', 'father')")
        op.execute(
            "UPDATE family_members SET member_role = 'parent' "
            "WHERE member_role IN ('mother', 'father')"
        )
        return

    op.execute("ALTER TYPE user_role RENAME TO user_role_new")
    op.execute("CREATE TYPE user_role AS ENUM ('child', 'parent')")
    op.execute(
        "ALTER TABLE users ALTER COLUMN role TYPE user_role "
        "USING CASE role::text "
        "WHEN 'mother' THEN 'parent' "
        "WHEN 'father' THEN 'parent' "
        "ELSE role::text END::user_role"
    )
    op.execute("DROP TYPE user_role_new")

    op.execute("ALTER TYPE family_member_role RENAME TO family_member_role_new")
    op.execute("CREATE TYPE family_member_role AS ENUM ('child', 'parent', 'member')")
    op.execute(
        "ALTER TABLE family_members "
        "ALTER COLUMN member_role TYPE family_member_role "
        "USING CASE member_role::text "
        "WHEN 'mother' THEN 'parent' "
        "WHEN 'father' THEN 'parent' "
        "ELSE member_role::text END::family_member_role"
    )
    op.execute("DROP TYPE family_member_role_new")
