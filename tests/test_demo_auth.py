from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.session import Base, get_db
from app.main import app
from app.models.user import User, UserRole, UserStatus


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def create_user(
    session_factory: sessionmaker[Session],
    *,
    user_id: int = 43,
    status: UserStatus = UserStatus.ACTIVE,
) -> User:
    with session_factory() as db:
        user = User(
            id=user_id,
            public_id=f"demo_public_id_{user_id}",
            display_name="Demo Child",
            role=UserRole.CHILD,
            status=status,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@contextmanager
def make_client(
    session_factory: sessionmaker[Session],
    *,
    enable_demo_mode: bool,
    demo_user_id: int | None,
) -> Iterator[TestClient]:
    def override_settings() -> Settings:
        return Settings(
            _env_file=None,
            enable_demo_mode=enable_demo_mode,
            demo_user_id=demo_user_id,
        )

    def override_db() -> Iterator[Session]:
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_db] = override_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_demo_mode_header_returns_configured_user_without_authorization(
    session_factory: sessionmaker[Session],
) -> None:
    user = create_user(session_factory)

    with make_client(session_factory, enable_demo_mode=True, demo_user_id=user.id) as client:
        response = client.get(
            "/api/v1/users/me/onboarding",
            headers={"X-Demo-Mode": " true "},
        )

    assert response.status_code == 200
    assert response.json()["role"] == "child"


def test_demo_mode_header_is_rejected_when_disabled(
    session_factory: sessionmaker[Session],
) -> None:
    user = create_user(session_factory)

    with make_client(session_factory, enable_demo_mode=False, demo_user_id=user.id) as client:
        response = client.get("/api/v1/users/me/onboarding", headers={"X-Demo-Mode": "true"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_demo_mode_returns_error_when_demo_user_id_is_missing(
    session_factory: sessionmaker[Session],
) -> None:
    with make_client(session_factory, enable_demo_mode=True, demo_user_id=None) as client:
        response = client.get("/api/v1/users/me/onboarding", headers={"X-Demo-Mode": "true"})

    assert response.status_code == 503
    assert response.json() == {"detail": "Demo user is not configured"}


def test_demo_mode_returns_error_when_user_is_missing(
    session_factory: sessionmaker[Session],
) -> None:
    with make_client(session_factory, enable_demo_mode=True, demo_user_id=43) as client:
        response = client.get("/api/v1/users/me/onboarding", headers={"X-Demo-Mode": "true"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Demo user is unavailable"}


def test_demo_mode_returns_error_when_user_is_disabled(
    session_factory: sessionmaker[Session],
) -> None:
    user = create_user(session_factory, status=UserStatus.DISABLED)

    with make_client(session_factory, enable_demo_mode=True, demo_user_id=user.id) as client:
        response = client.get("/api/v1/users/me/onboarding", headers={"X-Demo-Mode": "true"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Demo user is unavailable"}
