from secrets import token_urlsafe
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AnyUrl, SecretStr
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.auth import AccessTokenResponse, LoginCodeExchangeRequest
from app.services.kakao_auth_service import KakaoAuthError
from app.services.kakao_login_service import (
    KakaoLoginConfigError,
    KakaoLoginError,
    KakaoLoginService,
)
from app.services.login_code_service import (
    ExpiredLoginCodeError,
    InvalidLoginCodeError,
    LoginCodeService,
    UsedLoginCodeError,
)

KAKAO_AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"

router = APIRouter(prefix="/auth", tags=["auth"])


def get_kakao_login_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> KakaoLoginService:
    return KakaoLoginService(settings)


def _required_secret_value(value: SecretStr | None, field_name: str) -> str:
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{field_name} is not configured",
        )
    return value.get_secret_value()


def _required_url(value: AnyUrl | None, field_name: str) -> str:
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{field_name} is not configured",
        )
    return str(value)


@router.get("/kakao/login-url")
def create_kakao_login_url(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
    state = token_urlsafe(32)
    client_id = _required_secret_value(settings.kakao_rest_api_key, "KAKAO_REST_API_KEY")
    redirect_uri = _required_url(settings.kakao_redirect_uri, "KAKAO_REDIRECT_URI")

    # TODO: Persist state server-side and verify it in the callback before token exchange.
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
        }
    )

    return {
        "loginUrl": f"{KAKAO_AUTHORIZE_URL}?{query}",
        "state": state,
    }


@router.get("/kakao/callback")
async def kakao_callback(
    db: Annotated[Session, Depends(get_db)],
    kakao_login_service: Annotated[KakaoLoginService, Depends(get_kakao_login_service)],
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kakao authorization code is required",
        )

    # TODO: Verify state after server-side state storage is implemented.
    _ = state

    try:
        result = await kakao_login_service.login_with_authorization_code(db, code=code)
    except KakaoAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Kakao authentication failed",
        ) from exc
    except KakaoLoginConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OAuth callback URL is not configured",
        ) from exc
    except KakaoLoginError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kakao login failed",
        ) from exc

    return RedirectResponse(result.redirect_url, status_code=status.HTTP_302_FOUND)


@router.post("/login-code/exchange", response_model=AccessTokenResponse)
def exchange_login_code(
    payload: LoginCodeExchangeRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[Session, Depends(get_db)],
) -> AccessTokenResponse:
    try:
        result = LoginCodeService(settings).exchange_login_code(
            db,
            login_code=payload.login_code,
        )
    except ExpiredLoginCodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="login_code has expired",
        ) from exc
    except UsedLoginCodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="login_code has already been used",
        ) from exc
    except InvalidLoginCodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid login_code",
        ) from exc

    return AccessTokenResponse(accessToken=result.access_token, tokenType=result.token_type)
