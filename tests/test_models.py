from app.models import Base
from app.models.family import FamilyStatus
from app.models.family_member import FamilyMemberRole, FamilyMemberStatus
from app.models.oauth_login_code import LoginCodeStatus
from app.models.social_account import OAuthProvider
from app.models.user import UserRole, UserStatus


def test_auth_onboarding_tables_are_registered_in_metadata() -> None:
    assert {
        "users",
        "social_accounts",
        "oauth_login_codes",
        "families",
        "family_members",
    } <= set(Base.metadata.tables)


def test_users_model_matches_db_schema() -> None:
    users = Base.metadata.tables["users"]

    assert users.c.id.type.python_type is int
    assert users.c.public_id.type.length == 32
    assert users.c.display_name.type.length == 100
    assert users.c.profile_image_url.nullable is True
    assert users.c.role.nullable is True
    assert users.c.status.nullable is False
    assert users.c.deleted_at.nullable is True

    indexes = {index.name for index in users.indexes}
    assert "ux_users_public_id" in indexes
    assert "ix_users_role_status" in indexes


def test_social_accounts_model_does_not_store_kakao_tokens() -> None:
    social_accounts = Base.metadata.tables["social_accounts"]

    assert "access_token" not in social_accounts.c
    assert "refresh_token" not in social_accounts.c
    assert social_accounts.c.provider_user_id.type.length == 191
    assert social_accounts.c.email.nullable is True
    assert social_accounts.c.profile_image_url.nullable is True

    indexes = {index.name for index in social_accounts.indexes}
    assert "ux_social_accounts_provider_user" in indexes
    assert "ix_social_accounts_user_id" in indexes


def test_oauth_login_codes_model_stores_only_code_hash() -> None:
    oauth_login_codes = Base.metadata.tables["oauth_login_codes"]

    assert "login_code" not in oauth_login_codes.c
    assert "code_hash" in oauth_login_codes.c
    assert oauth_login_codes.c.code_hash.type.length == 255
    assert oauth_login_codes.c.expires_at.nullable is False
    assert oauth_login_codes.c.used_at.nullable is True

    indexes = {index.name for index in oauth_login_codes.indexes}
    assert "ux_oauth_login_codes_code_hash" in indexes
    assert "ix_oauth_login_codes_user_status" in indexes
    assert "ix_oauth_login_codes_expires_at" in indexes


def test_families_model_matches_db_schema() -> None:
    families = Base.metadata.tables["families"]

    assert families.c.id.type.python_type is int
    assert families.c.public_id.type.length == 32
    assert families.c.name.type.length == 100
    assert families.c.created_by_user_id.nullable is False
    assert families.c.status.nullable is False
    assert families.c.deleted_at.nullable is True

    indexes = {index.name for index in families.indexes}
    assert "ux_families_public_id" in indexes
    assert "ix_families_created_by_user_id" in indexes
    assert "ix_families_status" in indexes


def test_family_members_model_matches_db_schema() -> None:
    family_members = Base.metadata.tables["family_members"]

    assert family_members.c.id.type.python_type is int
    assert family_members.c.family_id.nullable is False
    assert family_members.c.user_id.nullable is False
    assert family_members.c.member_role.nullable is False
    assert family_members.c.status.nullable is False
    assert family_members.c.joined_at.nullable is True

    indexes = {index.name for index in family_members.indexes}
    assert "ux_family_members_family_user" in indexes
    assert "ix_family_members_user_status" in indexes
    assert "ix_family_members_family_status" in indexes


def test_auth_onboarding_enum_values_match_db_schema() -> None:
    assert [role.value for role in UserRole] == ["child", "parent"]
    assert [status.value for status in UserStatus] == ["active", "disabled"]
    assert [provider.value for provider in OAuthProvider] == ["kakao"]
    assert [status.value for status in LoginCodeStatus] == ["active", "used", "expired"]
    assert [status.value for status in FamilyStatus] == ["active", "archived"]
    assert [role.value for role in FamilyMemberRole] == ["child", "parent", "member"]
    assert [status.value for status in FamilyMemberStatus] == [
        "active",
        "invited",
        "left",
        "removed",
    ]
