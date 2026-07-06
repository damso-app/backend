from app.models import Base
from app.models.family import FamilyStatus
from app.models.family_member import FamilyMemberRole, FamilyMemberStatus
from app.models.oauth_login_code import LoginCodeStatus
from app.models.question_recommendation import (
    QuestionDepth,
    QuestionRecommendationStatus,
)
from app.models.question_send import QuestionSendSource, QuestionSendStatus
from app.models.social_account import OAuthProvider
from app.models.user import UserRole, UserStatus
from app.models.user_agreement import AgreementType


def test_auth_onboarding_tables_are_registered_in_metadata() -> None:
    assert {
        "users",
        "social_accounts",
        "oauth_login_codes",
        "families",
        "family_members",
        "user_agreements",
        "question_recommendations",
        "question_sends",
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
    assert families.c.invite_code.type.length == 7
    assert families.c.invite_code.nullable is True
    assert families.c.created_by_user_id.nullable is False
    assert families.c.status.nullable is False
    assert families.c.deleted_at.nullable is True

    indexes = {index.name for index in families.indexes}
    assert "ux_families_public_id" in indexes
    assert "ux_families_invite_code" in indexes
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


def test_user_agreements_model_matches_db_schema() -> None:
    user_agreements = Base.metadata.tables["user_agreements"]

    assert user_agreements.c.id.type.python_type is int
    assert user_agreements.c.user_id.nullable is False
    assert user_agreements.c.agreement_type.nullable is False
    assert user_agreements.c.agreed.nullable is False
    assert user_agreements.c.agreed_at.nullable is True
    assert user_agreements.c.created_at.nullable is False
    assert user_agreements.c.updated_at.nullable is False

    indexes = {index.name for index in user_agreements.indexes}
    assert "ux_user_agreements_user_type" in indexes
    assert "ix_user_agreements_user_agreed" in indexes


def test_question_recommendations_model_matches_db_schema() -> None:
    question_recommendations = Base.metadata.tables["question_recommendations"]

    assert question_recommendations.c.id.type.python_type is int
    assert question_recommendations.c.question_text.nullable is False
    assert question_recommendations.c.depth.nullable is False
    assert question_recommendations.c.category.type.length == 80
    assert question_recommendations.c.category.nullable is True
    assert question_recommendations.c.status.nullable is False

    indexes = {index.name for index in question_recommendations.indexes}
    assert "ix_question_recommendations_depth_status" in indexes


def test_question_sends_model_matches_db_schema() -> None:
    question_sends = Base.metadata.tables["question_sends"]

    assert question_sends.c.id.type.python_type is int
    assert question_sends.c.sender_user_id.nullable is False
    assert question_sends.c.recipient_user_id.nullable is False
    assert question_sends.c.family_id.nullable is False
    assert question_sends.c.question_text.nullable is False
    assert question_sends.c.depth.nullable is False
    assert question_sends.c.source.nullable is False
    assert question_sends.c.recommendation_id.nullable is True
    assert question_sends.c.sent_at.nullable is False
    assert question_sends.c.read_at.nullable is True
    assert question_sends.c.answered_at.nullable is True
    assert question_sends.c.status.nullable is False

    indexes = {index.name for index in question_sends.indexes}
    assert "ix_question_sends_recipient_status" in indexes
    assert "ix_question_sends_sender_status" in indexes
    assert "ix_question_sends_family_sent_at" in indexes


def test_auth_onboarding_enum_values_match_db_schema() -> None:
    assert [role.value for role in UserRole] == ["child", "mother", "father"]
    assert [status.value for status in UserStatus] == ["active", "disabled"]
    assert [provider.value for provider in OAuthProvider] == ["kakao"]
    assert [status.value for status in LoginCodeStatus] == ["active", "used", "expired"]
    assert [status.value for status in FamilyStatus] == ["active", "archived"]
    assert [role.value for role in FamilyMemberRole] == ["child", "mother", "father"]
    assert [status.value for status in FamilyMemberStatus] == [
        "active",
        "invited",
        "left",
        "removed",
    ]
    assert [agreement_type.value for agreement_type in AgreementType] == [
        "terms_of_service",
        "privacy_policy",
        "camera_microphone_notice",
    ]
    assert [depth.value for depth in QuestionDepth] == ["tiny", "medium", "deep"]
    assert [status.value for status in QuestionRecommendationStatus] == [
        "active",
        "archived",
    ]
    assert [source.value for source in QuestionSendSource] == ["recommendation", "custom"]
    assert [status.value for status in QuestionSendStatus] == [
        "sent",
        "answered",
        "cancelled",
        "expired",
    ]
