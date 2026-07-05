from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.core.database import Base, get_db
from app.core.security import AccessTokenError, create_access_token, verify_access_token
from app.main import app
from app.models.oauth_login_code import LoginCodeStatus, OAuthLoginCode
from app.models.user import User
from app.services.login_code_service import (
    ExpiredLoginCodeError,
    LoginCodeService,
    UsedLoginCodeError,
)


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret_key="unit-test-jwt-secret-with-at-least-32-bytes",
        jwt_algorithm="HS256",
        access_token_expire_minutes=15,
        login_code_expire_minutes=5,
        kakao_rest_api_key="test-kakao-rest-api-key",
        kakao_client_secret="test-kakao-client-secret",
        kakao_redirect_uri="http://testserver/api/v1/auth/kakao/callback",
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
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        yield session


def create_test_user(db: Session, *, public_id: str = "user_public_id") -> User:
    user = User(public_id=public_id, display_name="Test User")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_create_and_verify_access_token(auth_settings: Settings) -> None:
    token = create_access_token(
        subject="user_public_id",
        provider="damso",
        role=None,
        settings=auth_settings,
    )

    payload = verify_access_token(token, settings=auth_settings)

    assert payload["sub"] == "user_public_id"
    assert payload["provider"] == "damso"
    assert "role" not in payload


def test_verify_access_token_rejects_invalid_token(auth_settings: Settings) -> None:
    with pytest.raises(AccessTokenError):
        verify_access_token("invalid-token", settings=auth_settings)


def test_create_login_code_stores_only_hash(db: Session, auth_settings: Settings) -> None:
    user = create_test_user(db)
    service = LoginCodeService(auth_settings)

    created = service.create_login_code(db, user_id=user.id)

    stored_code = db.scalar(select(OAuthLoginCode).where(OAuthLoginCode.user_id == user.id))
    assert stored_code is not None
    assert created.login_code
    assert stored_code.code_hash != created.login_code
    assert len(stored_code.code_hash) == 64
    assert stored_code.status == LoginCodeStatus.ACTIVE
    assert created.expires_at > datetime.now(UTC)


def test_exchange_login_code_success(db: Session, auth_settings: Settings) -> None:
    user = create_test_user(db)
    service = LoginCodeService(auth_settings)
    created = service.create_login_code(db, user_id=user.id)

    exchanged = service.exchange_login_code(db, login_code=created.login_code)

    payload = verify_access_token(exchanged.access_token, settings=auth_settings)
    stored_code = db.scalar(select(OAuthLoginCode).where(OAuthLoginCode.user_id == user.id))

    assert exchanged.token_type == "bearer"
    assert payload["sub"] == "user_public_id"
    assert payload["provider"] == "damso"
    assert stored_code is not None
    assert stored_code.status == LoginCodeStatus.USED
    assert stored_code.used_at is not None


def test_expired_login_code_exchange_fails(db: Session, auth_settings: Settings) -> None:
    user = create_test_user(db)
    service = LoginCodeService(auth_settings)
    created = service.create_login_code(db, user_id=user.id)
    stored_code = db.scalar(select(OAuthLoginCode).where(OAuthLoginCode.user_id == user.id))
    assert stored_code is not None
    stored_code.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    with pytest.raises(ExpiredLoginCodeError):
        service.exchange_login_code(db, login_code=created.login_code)

    db.refresh(stored_code)
    assert stored_code.status == LoginCodeStatus.EXPIRED


def test_used_login_code_reuse_fails(db: Session, auth_settings: Settings) -> None:
    user = create_test_user(db)
    service = LoginCodeService(auth_settings)
    created = service.create_login_code(db, user_id=user.id)

    service.exchange_login_code(db, login_code=created.login_code)

    with pytest.raises(UsedLoginCodeError):
        service.exchange_login_code(db, login_code=created.login_code)


def test_exchange_api_success(
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    service = LoginCodeService(auth_settings)
    with session_factory() as setup_db:
        user = create_test_user(setup_db)
        created = service.create_login_code(setup_db, user_id=user.id)

    def override_settings() -> Settings:
        return auth_settings

    def override_db() -> Iterator[Session]:
        with session_factory() as request_db:
            yield request_db

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).post(
            "/api/v1/auth/login-code/exchange",
            json={"loginCode": created.login_code},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"accessToken", "tokenType"}
    assert body["tokenType"] == "bearer"
    assert "kakao" not in body["accessToken"].lower()
    payload = verify_access_token(body["accessToken"], settings=auth_settings)
    assert payload["sub"] == "user_public_id"
    assert payload["provider"] == "damso"


def test_exchange_api_failure(
    session_factory: sessionmaker[Session],
    auth_settings: Settings,
) -> None:
    def override_settings() -> Settings:
        return auth_settings

    def override_db() -> Iterator[Session]:
        with session_factory() as request_db:
            yield request_db

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).post(
            "/api/v1/auth/login-code/exchange",
            json={"loginCode": "unknown-login-code"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid login_code"}
