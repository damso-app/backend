import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import create_access_token
from app.models.oauth_login_code import LoginCodeStatus, OAuthLoginCode
from app.models.user import User


class LoginCodeError(Exception):
    pass


class InvalidLoginCodeError(LoginCodeError):
    pass


class ExpiredLoginCodeError(LoginCodeError):
    pass


class UsedLoginCodeError(LoginCodeError):
    pass


@dataclass(frozen=True)
class CreatedLoginCode:
    login_code: str
    expires_at: datetime


@dataclass(frozen=True)
class ExchangedLoginCode:
    access_token: str
    token_type: str = "bearer"


class LoginCodeService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def create_login_code(self, db: Session, *, user_id: int) -> CreatedLoginCode:
        login_code = token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(
            minutes=self._settings.login_code_expire_minutes
        )
        db.add(
            OAuthLoginCode(
                user_id=user_id,
                code_hash=self._hash_login_code(login_code),
                status=LoginCodeStatus.ACTIVE,
                expires_at=expires_at,
            )
        )
        db.commit()

        return CreatedLoginCode(login_code=login_code, expires_at=expires_at)

    def exchange_login_code(self, db: Session, *, login_code: str) -> ExchangedLoginCode:
        code_hash = self._hash_login_code(login_code)
        code = db.scalar(
            select(OAuthLoginCode)
            .where(OAuthLoginCode.code_hash == code_hash)
            .limit(1)
        )
        if code is None:
            raise InvalidLoginCodeError("Invalid login_code")

        now = datetime.now(UTC)
        if code.status == LoginCodeStatus.USED:
            raise UsedLoginCodeError("login_code has already been used")
        if code.status == LoginCodeStatus.EXPIRED or self._is_expired(code.expires_at, now):
            code.status = LoginCodeStatus.EXPIRED
            db.commit()
            raise ExpiredLoginCodeError("login_code has expired")

        user = db.get(User, code.user_id)
        if user is None:
            raise InvalidLoginCodeError("Invalid login_code")

        code.status = LoginCodeStatus.USED
        code.used_at = now
        access_token = create_access_token(
            subject=user.public_id,
            provider="damso",
            role=user.role.value if user.role is not None else None,
            settings=self._settings,
        )
        db.commit()

        return ExchangedLoginCode(access_token=access_token)

    def _hash_login_code(self, login_code: str) -> str:
        secret = self._hash_secret()
        return hmac.new(
            secret.encode("utf-8"),
            login_code.encode("utf-8"),
            sha256,
        ).hexdigest()

    def _hash_secret(self) -> str:
        secret = self._settings.jwt_secret_key or self._settings.jwt_secret
        if secret is None:
            raise LoginCodeError("JWT_SECRET_KEY is not configured")

        value = secret.get_secret_value()
        if not value:
            raise LoginCodeError("JWT_SECRET_KEY is not configured")

        return value

    @staticmethod
    def _is_expired(expires_at: datetime, now: datetime) -> bool:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return expires_at <= now
