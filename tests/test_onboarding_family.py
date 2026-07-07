import re
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.core.security import create_access_token
from app.db.session import Base, get_db
from app.main import app
from app.models.family import Family, FamilyStatus
from app.models.family_member import FamilyMember, FamilyMemberRole, FamilyMemberStatus
from app.models.user import User, UserRole
from app.models.user_agreement import AgreementType, UserAgreement


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret_key="unit-test-jwt-secret-with-at-least-32-bytes",
        jwt_algorithm="HS256",
        access_token_expire_minutes=15,
        login_code_expire_minutes=5,
        frontend_oauth_callback_url="http://localhost:3000/oauth/kakao/callback",
    )


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    try:
        yield SessionLocal
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> Iterator[TestClient]:
    def override_settings() -> Settings:
        return auth_settings

    def override_db() -> Iterator[Session]:
        with session_factory() as request_db:
            yield request_db

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_db] = override_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def create_user(
    session_factory: sessionmaker[Session],
    *,
    public_id: str,
    display_name: str = "승주",
    role: UserRole | None = None,
    agreements_completed: bool = True,
) -> tuple[int, str]:
    with session_factory() as db:
        user = User(public_id=public_id, display_name=display_name, role=role)
        db.add(user)
        db.flush()
        if agreements_completed:
            for agreement_type in AgreementType:
                db.add(
                    UserAgreement(
                        user_id=user.id,
                        agreement_type=agreement_type,
                        agreed=True,
                    )
                )
        db.commit()
        db.refresh(user)
        return user.id, user.public_id


def auth_headers(public_id: str, settings: Settings) -> dict[str, str]:
    token = create_access_token(
        subject=public_id,
        provider="damso",
        settings=settings,
    )
    return {"Authorization": f"Bearer {token}"}


def create_family_via_api(
    client: TestClient,
    *,
    public_id: str,
    settings: Settings,
    family_name: str = "승주의 가족",
) -> dict:
    response = client.post(
        "/api/v1/families",
        headers=auth_headers(public_id, settings),
        json={"familyName": family_name},
    )
    assert response.status_code == 200
    return response.json()


def test_get_onboarding_status_before_role_and_family(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    _, public_id = create_user(
        session_factory,
        public_id="onboarding_user",
        role=None,
        agreements_completed=True,
    )

    response = client.get(
        "/api/v1/users/me/onboarding",
        headers=auth_headers(public_id, auth_settings),
    )

    assert response.status_code == 200
    assert response.json() == {
        "userId": 1,
        "role": None,
        "requiredAgreementsCompleted": True,
        "familyId": None,
        "familyMemberRole": None,
        "familyConnected": False,
        "onboardingCompleted": False,
    }


def test_update_role_success(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    user_id, public_id = create_user(
        session_factory,
        public_id="role_user",
        agreements_completed=True,
    )

    response = client.patch(
        "/api/v1/users/me/role",
        headers=auth_headers(public_id, auth_settings),
        json={"role": "child"},
    )

    assert response.status_code == 200
    assert response.json() == {"userId": user_id, "role": "child"}
    with session_factory() as db:
        user = db.scalar(select(User).where(User.id == user_id))
        assert user is not None
        assert user.role == UserRole.CHILD
        assert user.role_selected_at is not None


def test_update_role_accepts_mother_and_father(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    _, mother_public_id = create_user(
        session_factory,
        public_id="mother_role_user",
        agreements_completed=True,
    )
    _, father_public_id = create_user(
        session_factory,
        public_id="father_role_user",
        agreements_completed=True,
    )

    mother_response = client.patch(
        "/api/v1/users/me/role",
        headers=auth_headers(mother_public_id, auth_settings),
        json={"role": "mother"},
    )
    father_response = client.patch(
        "/api/v1/users/me/role",
        headers=auth_headers(father_public_id, auth_settings),
        json={"role": "father"},
    )

    assert mother_response.status_code == 200
    assert mother_response.json()["role"] == "mother"
    assert father_response.status_code == 200
    assert father_response.json()["role"] == "father"


def test_update_role_rejects_unknown_role(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    _, public_id = create_user(
        session_factory,
        public_id="invalid_role_user",
        agreements_completed=True,
    )

    response = client.patch(
        "/api/v1/users/me/role",
        headers=auth_headers(public_id, auth_settings),
        json={"role": "guardian"},
    )

    assert response.status_code == 422


def test_required_agreements_incomplete_blocks_role_and_family_apis(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    _, public_id = create_user(
        session_factory,
        public_id="incomplete_user",
        agreements_completed=False,
    )
    headers = auth_headers(public_id, auth_settings)

    role_response = client.patch(
        "/api/v1/users/me/role",
        headers=headers,
        json={"role": "child"},
    )
    family_response = client.post(
        "/api/v1/families",
        headers=headers,
        json={"familyName": "승주의 가족"},
    )

    assert role_response.status_code == 400
    assert role_response.json() == {"detail": "Required agreements are incomplete"}
    assert family_response.status_code == 400
    assert family_response.json() == {"detail": "Required agreements are incomplete"}


def test_create_family_generates_invite_code_and_member(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    user_id, public_id = create_user(
        session_factory,
        public_id="child_user",
        role=UserRole.CHILD,
        agreements_completed=True,
    )

    body = create_family_via_api(client, public_id=public_id, settings=auth_settings)

    assert body["familyId"]
    assert body["familyName"] == "승주의 가족"
    assert re.fullmatch(r"[A-Z0-9]{3}-[A-Z0-9]{3}", body["inviteCode"])
    assert body["inviteUrl"] == f"http://localhost:3000/invite?code={body['inviteCode']}"
    assert body["memberRole"] == "child"

    with session_factory() as db:
        family = db.scalar(select(Family).where(Family.id == body["familyId"]))
        member = db.scalar(
            select(FamilyMember).where(
                FamilyMember.family_id == body["familyId"],
                FamilyMember.user_id == user_id,
            )
        )
        assert family is not None
        assert family.invite_code == body["inviteCode"].replace("-", "")
        assert member is not None
        assert member.member_role == FamilyMemberRole.CHILD
        assert member.status == FamilyMemberStatus.ACTIVE
        assert member.joined_at is not None


def test_create_family_without_role_fails(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    _, public_id = create_user(
        session_factory,
        public_id="no_role_user",
        role=None,
        agreements_completed=True,
    )

    response = client.post(
        "/api/v1/families",
        headers=auth_headers(public_id, auth_settings),
        json={"familyName": "승주의 가족"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "User role is required"}


def test_create_family_fails_when_user_already_has_family(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    _, public_id = create_user(
        session_factory,
        public_id="existing_family_user",
        role=UserRole.CHILD,
        agreements_completed=True,
    )
    create_family_via_api(client, public_id=public_id, settings=auth_settings)

    response = client.post(
        "/api/v1/families",
        headers=auth_headers(public_id, auth_settings),
        json={"familyName": "다른 가족"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "User already belongs to a family"}


def test_get_my_family_invitation_success(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    _, public_id = create_user(
        session_factory,
        public_id="invitation_owner",
        role=UserRole.CHILD,
        agreements_completed=True,
    )
    created = create_family_via_api(client, public_id=public_id, settings=auth_settings)

    response = client.get(
        "/api/v1/families/me/invitation",
        headers=auth_headers(public_id, auth_settings),
    )

    assert response.status_code == 200
    assert response.json() == {
        "familyId": created["familyId"],
        "familyName": created["familyName"],
        "inviteCode": created["inviteCode"],
        "inviteUrl": created["inviteUrl"],
    }


def test_validate_missing_invite_code_returns_404(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    _, public_id = create_user(
        session_factory,
        public_id="validator_user",
        role=UserRole.MOTHER,
        agreements_completed=True,
    )

    response = client.get(
        "/api/v1/families/invitations/NO1-COD",
        headers=auth_headers(public_id, auth_settings),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Invite code was not found"}


def test_validate_invite_code_success(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    _, child_public_id = create_user(
        session_factory,
        public_id="invite_child",
        role=UserRole.CHILD,
        agreements_completed=True,
    )
    _, mother_public_id = create_user(
        session_factory,
        public_id="invite_mother",
        role=UserRole.MOTHER,
        agreements_completed=True,
    )
    created = create_family_via_api(client, public_id=child_public_id, settings=auth_settings)

    response = client.get(
        f"/api/v1/families/invitations/{created['inviteCode']}",
        headers=auth_headers(mother_public_id, auth_settings),
    )

    assert response.status_code == 200
    assert response.json() == {
        "inviteCode": created["inviteCode"],
        "familyId": created["familyId"],
        "familyName": created["familyName"],
        "available": True,
    }


def test_mother_joins_family_with_invite_code(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    _, child_public_id = create_user(
        session_factory,
        public_id="join_child",
        role=UserRole.CHILD,
        agreements_completed=True,
    )
    mother_user_id, mother_public_id = create_user(
        session_factory,
        public_id="join_mother",
        role=UserRole.MOTHER,
        agreements_completed=True,
    )
    created = create_family_via_api(client, public_id=child_public_id, settings=auth_settings)

    response = client.post(
        "/api/v1/families/join",
        headers=auth_headers(mother_public_id, auth_settings),
        json={"inviteCode": created["inviteCode"]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "familyId": created["familyId"],
        "familyName": created["familyName"],
        "memberRole": "mother",
        "familyConnected": True,
    }
    with session_factory() as db:
        member = db.scalar(
            select(FamilyMember).where(
                FamilyMember.family_id == created["familyId"],
                FamilyMember.user_id == mother_user_id,
            )
        )
        assert member is not None
        assert member.member_role == FamilyMemberRole.MOTHER
        assert member.joined_at is not None


@pytest.mark.parametrize(
    "code_variant",
    [
        lambda code: code.replace("-", ""),
        lambda code: code.lower(),
        lambda code: code.replace("-", " "),
    ],
)
def test_join_normalizes_invite_code_variants(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
    code_variant,
) -> None:
    _, child_public_id = create_user(
        session_factory,
        public_id=f"normalize_child_{code_variant.__name__}",
        role=UserRole.CHILD,
        agreements_completed=True,
    )
    mother_user_id, mother_public_id = create_user(
        session_factory,
        public_id=f"normalize_mother_{code_variant.__name__}",
        role=UserRole.MOTHER,
        agreements_completed=True,
    )
    created = create_family_via_api(client, public_id=child_public_id, settings=auth_settings)

    response = client.post(
        "/api/v1/families/join",
        headers=auth_headers(mother_public_id, auth_settings),
        json={"inviteCode": code_variant(created["inviteCode"])},
    )

    assert response.status_code == 200
    assert response.json()["familyConnected"] is True
    with session_factory() as db:
        member_count = db.scalar(
            select(func.count(FamilyMember.id)).where(
                FamilyMember.family_id == created["familyId"],
                FamilyMember.user_id == mother_user_id,
            )
        )
        assert member_count == 1


def test_join_fails_when_user_already_has_family(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    _, first_child_public_id = create_user(
        session_factory,
        public_id="first_child",
        role=UserRole.CHILD,
        agreements_completed=True,
    )
    _, second_child_public_id = create_user(
        session_factory,
        public_id="second_child",
        role=UserRole.CHILD,
        agreements_completed=True,
    )
    _, father_public_id = create_user(
        session_factory,
        public_id="already_joined_father",
        role=UserRole.FATHER,
        agreements_completed=True,
    )
    first_family = create_family_via_api(
        client,
        public_id=first_child_public_id,
        settings=auth_settings,
        family_name="첫 가족",
    )
    second_family = create_family_via_api(
        client,
        public_id=second_child_public_id,
        settings=auth_settings,
        family_name="둘째 가족",
    )
    first_join = client.post(
        "/api/v1/families/join",
        headers=auth_headers(father_public_id, auth_settings),
        json={"inviteCode": first_family["inviteCode"]},
    )
    assert first_join.status_code == 200
    assert first_join.json()["memberRole"] == "father"

    response = client.post(
        "/api/v1/families/join",
        headers=auth_headers(father_public_id, auth_settings),
        json={"inviteCode": second_family["inviteCode"]},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "User already belongs to a family"}


def test_join_with_own_family_invite_code_returns_409(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    _, child_public_id = create_user(
        session_factory,
        public_id="own_invite_child",
        role=UserRole.CHILD,
        agreements_completed=True,
    )
    created = create_family_via_api(client, public_id=child_public_id, settings=auth_settings)

    response = client.post(
        "/api/v1/families/join",
        headers=auth_headers(child_public_id, auth_settings),
        json={"inviteCode": created["inviteCode"]},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Cannot join own family invitation"}


def test_join_without_required_agreements_returns_400(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    _, child_public_id = create_user(
        session_factory,
        public_id="agreement_child",
        role=UserRole.CHILD,
        agreements_completed=True,
    )
    _, mother_public_id = create_user(
        session_factory,
        public_id="agreement_incomplete_mother",
        role=UserRole.MOTHER,
        agreements_completed=False,
    )
    created = create_family_via_api(client, public_id=child_public_id, settings=auth_settings)

    response = client.post(
        "/api/v1/families/join",
        headers=auth_headers(mother_public_id, auth_settings),
        json={"inviteCode": created["inviteCode"]},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Required agreements are incomplete"}


def test_join_without_role_returns_400(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    _, child_public_id = create_user(
        session_factory,
        public_id="role_required_child",
        role=UserRole.CHILD,
        agreements_completed=True,
    )
    _, no_role_public_id = create_user(
        session_factory,
        public_id="role_required_joiner",
        role=None,
        agreements_completed=True,
    )
    created = create_family_via_api(client, public_id=child_public_id, settings=auth_settings)

    response = client.post(
        "/api/v1/families/join",
        headers=auth_headers(no_role_public_id, auth_settings),
        json={"inviteCode": created["inviteCode"]},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "User role is required"}


@pytest.mark.parametrize("deleted", [False, True])
def test_inactive_or_deleted_family_invite_code_returns_404(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
    deleted: bool,
) -> None:
    _, child_public_id = create_user(
        session_factory,
        public_id=f"hidden_child_{deleted}",
        role=UserRole.CHILD,
        agreements_completed=True,
    )
    _, mother_public_id = create_user(
        session_factory,
        public_id=f"hidden_mother_{deleted}",
        role=UserRole.MOTHER,
        agreements_completed=True,
    )
    created = create_family_via_api(client, public_id=child_public_id, settings=auth_settings)
    with session_factory() as db:
        family = db.scalar(select(Family).where(Family.id == created["familyId"]))
        assert family is not None
        if deleted:
            family.deleted_at = datetime.now(UTC)
        else:
            family.status = FamilyStatus.ARCHIVED
        db.commit()

    validation_response = client.get(
        f"/api/v1/families/invitations/{created['inviteCode']}",
        headers=auth_headers(mother_public_id, auth_settings),
    )
    join_response = client.post(
        "/api/v1/families/join",
        headers=auth_headers(mother_public_id, auth_settings),
        json={"inviteCode": created["inviteCode"]},
    )

    assert validation_response.status_code == 404
    assert validation_response.json() == {"detail": "Invite code was not found"}
    assert join_response.status_code == 404
    assert join_response.json() == {"detail": "Invite code was not found"}


def test_duplicate_join_is_blocked_by_unique_family_member_constraint(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    _, child_public_id = create_user(
        session_factory,
        public_id="duplicate_child",
        role=UserRole.CHILD,
        agreements_completed=True,
    )
    mother_user_id, mother_public_id = create_user(
        session_factory,
        public_id="duplicate_mother",
        role=UserRole.MOTHER,
        agreements_completed=True,
    )
    created = create_family_via_api(client, public_id=child_public_id, settings=auth_settings)
    with session_factory() as db:
        db.add(
            FamilyMember(
                family_id=created["familyId"],
                user_id=mother_user_id,
                member_role=FamilyMemberRole.MOTHER,
                status=FamilyMemberStatus.LEFT,
            )
        )
        db.commit()

    response = client.post(
        "/api/v1/families/join",
        headers=auth_headers(mother_public_id, auth_settings),
        json={"inviteCode": created["inviteCode"]},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "User already belongs to a family"}
    with session_factory() as db:
        member_count = db.scalar(
            select(func.count(FamilyMember.id)).where(
                FamilyMember.family_id == created["familyId"],
                FamilyMember.user_id == mother_user_id,
            )
        )
        assert member_count == 1
