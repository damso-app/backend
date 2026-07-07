from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt import InvalidTokenError

from app.core.config import Settings, get_settings


class AccessTokenError(Exception):
    pass


class AiCallbackTokenError(Exception):
    pass


_AI_CALLBACK_TOKEN_AUD = "ai-callback"


def create_access_token(
    *,
    subject: str,
    provider: str,
    role: str | None = None,
    settings: Settings | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    resolved_settings = settings or get_settings()
    secret_key = _required_jwt_secret(resolved_settings)
    now = datetime.now(UTC)
    expire_minutes = resolved_settings.access_token_expire_minutes
    expires_at = now + (expires_delta or timedelta(minutes=expire_minutes))

    payload: dict[str, Any] = {
        "sub": subject,
        "provider": provider,
        "iat": int(now.timestamp()),
        "exp": expires_at,
    }
    if role is not None:
        payload["role"] = role

    return jwt.encode(
        payload,
        secret_key,
        algorithm=resolved_settings.jwt_algorithm,
    )


def verify_access_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    resolved_settings = settings or get_settings()
    secret_key = _required_jwt_secret(resolved_settings)

    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[resolved_settings.jwt_algorithm],
        )
    except InvalidTokenError as exc:
        raise AccessTokenError("Invalid access token") from exc

    if not isinstance(payload.get("sub"), str) or not payload["sub"]:
        raise AccessTokenError("Invalid access token")
    if not isinstance(payload.get("provider"), str) or not payload["provider"]:
        raise AccessTokenError("Invalid access token")

    role = payload.get("role")
    if role is not None and not isinstance(role, str):
        raise AccessTokenError("Invalid access token")

    return payload


def create_ai_callback_token(
    *,
    answer_id: int,
    settings: Settings | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    resolved_settings = settings or get_settings()
    secret_key = _required_jwt_secret(resolved_settings)
    now = datetime.now(UTC)
    expire_minutes = resolved_settings.ai_callback_token_expire_minutes
    expires_at = now + (expires_delta or timedelta(minutes=expire_minutes))

    payload: dict[str, Any] = {
        "aud": _AI_CALLBACK_TOKEN_AUD,
        "answer_id": answer_id,
        "iat": int(now.timestamp()),
        "exp": expires_at,
    }
    return jwt.encode(payload, secret_key, algorithm=resolved_settings.jwt_algorithm)


def verify_ai_callback_token(
    token: str,
    *,
    answer_id: int,
    settings: Settings | None = None,
) -> None:
    resolved_settings = settings or get_settings()
    secret_key = _required_jwt_secret(resolved_settings)

    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[resolved_settings.jwt_algorithm],
            audience=_AI_CALLBACK_TOKEN_AUD,
        )
    except InvalidTokenError as exc:
        raise AiCallbackTokenError("Invalid callback token") from exc

    if payload.get("answer_id") != answer_id:
        raise AiCallbackTokenError("Callback token does not match this answer")


def _required_jwt_secret(settings: Settings) -> str:
    secret = settings.jwt_secret_key or settings.jwt_secret
    if secret is None:
        raise AccessTokenError("JWT_SECRET_KEY is not configured")

    value = secret.get_secret_value()
    if not value:
        raise AccessTokenError("JWT_SECRET_KEY is not configured")

    return value
