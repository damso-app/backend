from collections.abc import Iterator
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.database import Base
from app.models.oauth_login_code import OAuthLoginCode
from app.models.social_account import OAuthProvider, SocialAccount
from app.models.user import User
from app.schemas.auth import KakaoTokenResponse, KakaoUserInfo
from app.services.kakao_auth_service import KakaoAuthError
from app.services.kakao_login_service import KakaoLoginService


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret_key="unit-test-jwt-secret-with-at-least-32-bytes",
        jwt_algorithm="HS256",
        access_token_expire_minutes=15,
        login_code_expire_minutes=5,
        frontend_oauth_callback_url="http://localhost:3000/oauth/kakao/callback?source=kakao",
        kakao_rest_api_key="test-kakao-rest-api-key",
        kakao_client_secret="test-kakao-client-secret",
        kakao_redirect_uri="http://testserver/api/v1/auth/kakao/callback",
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


class FakeKakaoAuthService:
    def __init__(
        self,
        *,
        token_error: bool = False,
        userinfo_error: bool = False,
        user_info: KakaoUserInfo | None = None,
    ) -> None:
        self.token_error = token_error
        self.userinfo_error = userinfo_error
        self.user_info = user_info or KakaoUserInfo(
            kakao_id="123456789",
            nickname="Kakao User",
            email="user@example.com",
            profile_image_url="https://example.com/profile.jpg",
        )
        self.exchange_calls: list[str] = []
        self.userinfo_calls: list[str] = []

    async def exchange_code_for_token(self, code: str) -> KakaoTokenResponse:
        self.exchange_calls.append(code)
        if self.token_error:
            raise KakaoAuthError("Kakao token exchange failed")
        return KakaoTokenResponse(
            access_token="mock-provider-bearer",
            token_type="bearer",
        )

    async def get_user_info(self, kakao_access_token: str) -> KakaoUserInfo:
        self.userinfo_calls.append(kakao_access_token)
        if self.userinfo_error:
            raise KakaoAuthError("Kakao userinfo request failed")
        return self.user_info


def create_existing_social_account(
    db: Session,
    *,
    user_profile_image_url: str | None = None,
) -> User:
    user = User(
        public_id="existing_user_public_id",
        display_name="Existing User",
        profile_image_url=user_profile_image_url,
    )
    db.add(user)
    db.flush()
    db.add(
        SocialAccount(
            user_id=user.id,
            provider=OAuthProvider.KAKAO,
            provider_user_id="123456789",
            email="old@example.com",
            profile_image_url="https://example.com/old.jpg",
        )
    )
    db.commit()
    db.refresh(user)
    return user


@pytest.mark.anyio
async def test_kakao_login_uses_existing_social_account(
    db: Session,
    auth_settings: Settings,
) -> None:
    user = create_existing_social_account(db)
    kakao_auth_service = FakeKakaoAuthService()
    service = KakaoLoginService(auth_settings, kakao_auth_service=kakao_auth_service)

    result = await service.login_with_authorization_code(db, code="authorization-code")

    stored_code = db.scalar(select(OAuthLoginCode).where(OAuthLoginCode.user_id == user.id))
    parsed_url = urlparse(result.redirect_url)
    query = parse_qs(parsed_url.query)

    assert kakao_auth_service.exchange_calls == ["authorization-code"]
    assert kakao_auth_service.userinfo_calls == ["mock-provider-bearer"]
    assert stored_code is not None
    assert stored_code.code_hash != result.login_code
    assert query["source"] == ["kakao"]
    assert query["loginCode"] == [result.login_code]
    assert "accessToken" not in query
    assert "kakaoAccessToken" not in query
    assert db.scalar(select(func.count(User.id))) == 1


@pytest.mark.anyio
async def test_kakao_login_creates_user_and_social_account(
    db: Session,
    auth_settings: Settings,
) -> None:
    kakao_auth_service = FakeKakaoAuthService()
    service = KakaoLoginService(auth_settings, kakao_auth_service=kakao_auth_service)

    result = await service.login_with_authorization_code(db, code="authorization-code")

    user = db.scalar(select(User).limit(1))
    social_account = db.scalar(select(SocialAccount).limit(1))
    stored_code = db.scalar(select(OAuthLoginCode).limit(1))

    assert user is not None
    assert user.public_id
    assert len(user.public_id) <= 32
    assert user.display_name == "Kakao User"
    assert user.profile_image_url == "https://example.com/profile.jpg"
    assert social_account is not None
    assert social_account.user_id == user.id
    assert social_account.provider == OAuthProvider.KAKAO
    assert social_account.provider_user_id == "123456789"
    assert social_account.email == "user@example.com"
    assert social_account.profile_image_url == "https://example.com/profile.jpg"
    assert stored_code is not None
    assert stored_code.user_id == user.id
    assert result.login_code


@pytest.mark.anyio
async def test_kakao_login_succeeds_without_profile_image_url(
    db: Session,
    auth_settings: Settings,
) -> None:
    kakao_auth_service = FakeKakaoAuthService(
        user_info=KakaoUserInfo(
            kakao_id="123456789",
            nickname="Kakao User",
            email="user@example.com",
            profile_image_url=None,
        )
    )
    service = KakaoLoginService(auth_settings, kakao_auth_service=kakao_auth_service)

    await service.login_with_authorization_code(db, code="authorization-code")

    user = db.scalar(select(User).limit(1))
    social_account = db.scalar(select(SocialAccount).limit(1))

    assert user is not None
    assert user.profile_image_url is None
    assert social_account is not None
    assert social_account.profile_image_url is None


@pytest.mark.anyio
async def test_kakao_login_fills_missing_existing_user_profile_image_url(
    db: Session,
    auth_settings: Settings,
) -> None:
    user = create_existing_social_account(db, user_profile_image_url=None)
    kakao_auth_service = FakeKakaoAuthService(
        user_info=KakaoUserInfo(
            kakao_id="123456789",
            nickname="Kakao User",
            email="user@example.com",
            profile_image_url="https://example.com/new-profile.jpg",
        )
    )
    service = KakaoLoginService(auth_settings, kakao_auth_service=kakao_auth_service)

    await service.login_with_authorization_code(db, code="authorization-code")

    db.refresh(user)
    assert user.profile_image_url == "https://example.com/new-profile.jpg"


@pytest.mark.anyio
async def test_kakao_login_does_not_overwrite_existing_user_profile_image_url(
    db: Session,
    auth_settings: Settings,
) -> None:
    user = create_existing_social_account(
        db,
        user_profile_image_url="https://example.com/existing-profile.jpg",
    )
    kakao_auth_service = FakeKakaoAuthService(
        user_info=KakaoUserInfo(
            kakao_id="123456789",
            nickname="Kakao User",
            email="user@example.com",
            profile_image_url="https://example.com/new-profile.jpg",
        )
    )
    service = KakaoLoginService(auth_settings, kakao_auth_service=kakao_auth_service)

    await service.login_with_authorization_code(db, code="authorization-code")

    db.refresh(user)
    assert user.profile_image_url == "https://example.com/existing-profile.jpg"


@pytest.mark.anyio
async def test_kakao_login_token_exchange_failure(
    db: Session,
    auth_settings: Settings,
) -> None:
    service = KakaoLoginService(
        auth_settings,
        kakao_auth_service=FakeKakaoAuthService(token_error=True),
    )

    with pytest.raises(KakaoAuthError):
        await service.login_with_authorization_code(db, code="authorization-code")

    assert db.scalar(select(func.count(User.id))) == 0


@pytest.mark.anyio
async def test_kakao_login_userinfo_failure(
    db: Session,
    auth_settings: Settings,
) -> None:
    service = KakaoLoginService(
        auth_settings,
        kakao_auth_service=FakeKakaoAuthService(userinfo_error=True),
    )

    with pytest.raises(KakaoAuthError):
        await service.login_with_authorization_code(db, code="authorization-code")

    assert db.scalar(select(func.count(User.id))) == 0
