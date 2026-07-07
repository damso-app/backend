from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.core.security import create_access_token
from app.db.session import Base, get_db
from app.main import app
from app.models.user import User
from app.models.user_agreement import AgreementType, UserAgreement


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret_key="unit-test-jwt-secret-with-at-least-32-bytes",
        jwt_algorithm="HS256",
        access_token_expire_minutes=15,
        login_code_expire_minutes=5,
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


def create_user(session_factory: sessionmaker[Session], *, public_id: str = "user_public_id"):
    with session_factory() as db:
        user = User(public_id=public_id, display_name="Test User")
        db.add(user)
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


def test_get_agreements_returns_required_items_as_false_when_empty(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    _, public_id = create_user(session_factory)

    response = client.get(
        "/api/v1/users/me/agreements",
        headers=auth_headers(public_id, auth_settings),
    )

    assert response.status_code == 200
    assert response.json() == {
        "requiredAgreementsCompleted": False,
        "agreements": [
            {
                "type": "service_terms",
                "displayName": "서비스 이용약관 동의",
                "description": "질문, 영상 답변, 다이어리 저장 기능 이용",
                "agreed": False,
                "agreedAt": None,
            },
            {
                "type": "privacy_policy",
                "displayName": "개인정보 처리 동의",
                "description": "이름, 가족 정보, 질문, 영상 정보 처리",
                "agreed": False,
                "agreedAt": None,
            },
            {
                "type": "camera_microphone",
                "displayName": "카메라·마이크 권한 안내",
                "description": "카메라 및 마이크 권한 허용이 필수",
                "agreed": False,
                "agreedAt": None,
            },
            {
                "type": "data_usage",
                "displayName": "데이터 활용 동의",
                "description": "가족의 대화를 활용해 인공지능 처리",
                "agreed": False,
                "agreedAt": None,
            },
        ],
    }


def test_post_all_required_agreements_completes_onboarding(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    user_id, public_id = create_user(session_factory)

    response = client.post(
        "/api/v1/users/me/agreements",
        headers=auth_headers(public_id, auth_settings),
        json={
            "agreements": [
                {"type": "service_terms", "agreed": True},
                {"type": "privacy_policy", "agreed": True},
                {"type": "camera_microphone", "agreed": True},
                {"type": "data_usage", "agreed": True},
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {"requiredAgreementsCompleted": True}
    with session_factory() as db:
        agreements = db.scalars(
            select(UserAgreement).where(UserAgreement.user_id == user_id)
        ).all()
        assert len(agreements) == 4
        assert all(agreement.agreed for agreement in agreements)
        assert all(agreement.agreed_at is not None for agreement in agreements)


def test_post_partial_required_agreements_remains_incomplete(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    _, public_id = create_user(session_factory)

    response = client.post(
        "/api/v1/users/me/agreements",
        headers=auth_headers(public_id, auth_settings),
        json={"agreements": [{"type": "service_terms", "agreed": True}]},
    )

    assert response.status_code == 200
    assert response.json() == {"requiredAgreementsCompleted": False}
    status_response = client.get(
        "/api/v1/users/me/agreements",
        headers=auth_headers(public_id, auth_settings),
    )
    body = status_response.json()
    assert body["requiredAgreementsCompleted"] is False
    assert [item["agreed"] for item in body["agreements"]] == [True, False, False, False]


def test_post_three_required_agreements_without_data_usage_remains_incomplete(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    _, public_id = create_user(session_factory)

    response = client.post(
        "/api/v1/users/me/agreements",
        headers=auth_headers(public_id, auth_settings),
        json={
            "agreements": [
                {"type": "service_terms", "agreed": True},
                {"type": "privacy_policy", "agreed": True},
                {"type": "camera_microphone", "agreed": True},
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {"requiredAgreementsCompleted": False}


def test_post_same_agreement_updates_without_duplicate_rows(
    client: TestClient,
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    user_id, public_id = create_user(session_factory)
    payload = {"agreements": [{"type": "service_terms", "agreed": True}]}

    first_response = client.post(
        "/api/v1/users/me/agreements",
        headers=auth_headers(public_id, auth_settings),
        json=payload,
    )
    second_response = client.post(
        "/api/v1/users/me/agreements",
        headers=auth_headers(public_id, auth_settings),
        json=payload,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    with session_factory() as db:
        row_count = db.scalar(
            select(func.count(UserAgreement.id)).where(
                UserAgreement.user_id == user_id,
                UserAgreement.agreement_type == AgreementType.SERVICE_TERMS,
            )
        )
        assert row_count == 1


def test_agreements_endpoints_require_authentication(client: TestClient) -> None:
    get_response = client.get("/api/v1/users/me/agreements")
    post_response = client.post(
        "/api/v1/users/me/agreements",
        json={"agreements": [{"type": "service_terms", "agreed": True}]},
    )

    assert get_response.status_code == 401
    assert post_response.status_code == 401
