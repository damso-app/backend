import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import AccessTokenError, verify_access_token
from app.db.session import get_db
from app.models.user import User, UserStatus

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[Session, Depends(get_db)],
    x_demo_mode: Annotated[str | None, Header(alias="X-Demo-Mode")] = None,
) -> User:
    if (
        x_demo_mode is not None
        and x_demo_mode.strip().lower() == "true"
        and settings.enable_demo_mode
    ):
        if settings.demo_user_id is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Demo user is not configured",
            )

        demo_user = db.get(User, settings.demo_user_id)
        if (
            demo_user is None
            or demo_user.status != UserStatus.ACTIVE
            or demo_user.deleted_at is not None
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Demo user is unavailable",
            )

        return demo_user

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = verify_access_token(credentials.credentials, settings=settings)
    except AccessTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = db.scalar(select(User).where(User.public_id == payload["sub"]).limit(1))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def require_internal_trigger(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Gate internal, scheduler-triggered endpoints behind a static shared
    secret. Stand-in for OIDC verification of the Cloud Scheduler service
    account once deployed to Cloud Run."""
    if settings.internal_trigger_token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="INTERNAL_TRIGGER_TOKEN is not configured",
        )
    if credentials is None or not secrets.compare_digest(
        credentials.credentials, settings.internal_trigger_token.get_secret_value()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid trigger token",
            headers={"WWW-Authenticate": "Bearer"},
        )
