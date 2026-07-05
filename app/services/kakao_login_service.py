from dataclasses import dataclass
from secrets import token_urlsafe
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.social_account import OAuthProvider, SocialAccount
from app.models.user import User
from app.schemas.auth import KakaoUserInfo
from app.services.kakao_auth_service import KakaoAuthService
from app.services.login_code_service import LoginCodeService


class KakaoLoginError(Exception):
    pass


class KakaoLoginConfigError(KakaoLoginError):
    pass


@dataclass(frozen=True)
class KakaoLoginResult:
    redirect_url: str
    login_code: str


class KakaoLoginService:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        kakao_auth_service: KakaoAuthService | None = None,
        login_code_service: LoginCodeService | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._kakao_auth_service = kakao_auth_service or KakaoAuthService(self._settings)
        self._login_code_service = login_code_service or LoginCodeService(self._settings)

    async def login_with_authorization_code(self, db: Session, *, code: str) -> KakaoLoginResult:
        kakao_token = await self._kakao_auth_service.exchange_code_for_token(code)
        user_info = await self._kakao_auth_service.get_user_info(kakao_token.access_token)
        user = self._find_or_create_user(db, user_info=user_info)
        login_code = self._login_code_service.create_login_code(db, user_id=user.id)
        redirect_url = self._build_frontend_redirect_url(login_code.login_code)

        return KakaoLoginResult(
            redirect_url=redirect_url,
            login_code=login_code.login_code,
        )

    def _find_or_create_user(self, db: Session, *, user_info: KakaoUserInfo) -> User:
        social_account = db.scalar(
            select(SocialAccount)
            .where(
                SocialAccount.provider == OAuthProvider.KAKAO,
                SocialAccount.provider_user_id == user_info.kakao_id,
            )
            .limit(1)
        )
        if social_account is not None:
            return social_account.user

        user = User(
            public_id=self._generate_public_id(db),
            display_name=user_info.nickname,
        )
        db.add(user)
        db.flush()
        db.add(
            SocialAccount(
                user_id=user.id,
                provider=OAuthProvider.KAKAO,
                provider_user_id=user_info.kakao_id,
                email=user_info.email,
                profile_image_url=(
                    str(user_info.profile_image_url)
                    if user_info.profile_image_url is not None
                    else None
                ),
            )
        )
        db.commit()
        db.refresh(user)

        return user

    def _generate_public_id(self, db: Session) -> str:
        for _ in range(5):
            public_id = token_urlsafe(18)[:32]
            exists = db.scalar(select(User.id).where(User.public_id == public_id).limit(1))
            if exists is None:
                return public_id

        raise KakaoLoginError("Failed to generate user public_id")

    def _build_frontend_redirect_url(self, login_code: str) -> str:
        if self._settings.frontend_oauth_callback_url is None:
            raise KakaoLoginConfigError("FRONTEND_OAUTH_CALLBACK_URL is not configured")

        parts = urlsplit(str(self._settings.frontend_oauth_callback_url))
        query_items = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key not in {"loginCode", "accessToken", "kakaoAccessToken"}
        ]
        query_items.append(("loginCode", login_code))

        return urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                urlencode(query_items),
                parts.fragment,
            )
        )
