from typing import Any

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.auth import KakaoTokenResponse, KakaoUserInfo

KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
KAKAO_USERINFO_URL = "https://kapi.kakao.com/v2/user/me"


class KakaoAuthError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class KakaoAuthService:
    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._settings = settings
        self._client = client
        self._timeout_seconds = timeout_seconds

    async def exchange_code_for_token(self, code: str) -> KakaoTokenResponse:
        client_id = self._required_secret("KAKAO_REST_API_KEY", self._settings.kakao_rest_api_key)
        redirect_uri = self._required_url("KAKAO_REDIRECT_URI", self._settings.kakao_redirect_uri)

        data = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code": code,
        }

        if self._settings.kakao_client_secret is not None:
            client_secret = self._settings.kakao_client_secret.get_secret_value()
            if client_secret:
                data["client_secret"] = client_secret

        payload = await self._request_json(
            "POST",
            KAKAO_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=data,
            error_message="Kakao token exchange failed",
        )

        try:
            return KakaoTokenResponse.model_validate(payload)
        except ValidationError as exc:
            raise KakaoAuthError("Kakao token response is invalid") from exc

    async def get_user_info(self, kakao_access_token: str) -> KakaoUserInfo:
        payload = await self._request_json(
            "GET",
            KAKAO_USERINFO_URL,
            headers={"Authorization": f"Bearer {kakao_access_token}"},
            error_message="Kakao userinfo request failed",
        )

        try:
            kakao_id = self._required_kakao_id(payload["id"])
        except (KeyError, ValueError) as exc:
            raise KakaoAuthError("Kakao userinfo response is invalid") from exc

        kakao_account = payload.get("kakao_account")
        if not isinstance(kakao_account, dict):
            kakao_account = {}

        profile = kakao_account.get("profile")
        if not isinstance(profile, dict):
            profile = {}

        try:
            return KakaoUserInfo(
                kakao_id=kakao_id,
                nickname=self._optional_str(profile.get("nickname")),
                email=self._optional_str(kakao_account.get("email")),
                profile_image_url=self._optional_str(profile.get("profile_image_url")),
            )
        except ValidationError as exc:
            raise KakaoAuthError("Kakao userinfo response is invalid") from exc

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        error_message: str,
        data: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await self._send_request(method, url, headers=headers, data=data)
        except httpx.RequestError as exc:
            raise KakaoAuthError(error_message) from exc

        if response.status_code != httpx.codes.OK:
            raise KakaoAuthError(error_message, status_code=response.status_code)

        try:
            payload = response.json()
        except ValueError as exc:
            raise KakaoAuthError("Kakao response is invalid JSON") from exc

        if not isinstance(payload, dict):
            raise KakaoAuthError("Kakao response JSON is invalid")

        return payload

    async def _send_request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        data: dict[str, str] | None,
    ) -> httpx.Response:
        if self._client is not None:
            return await self._client.request(method, url, headers=headers, data=data)

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            return await client.request(method, url, headers=headers, data=data)

    @staticmethod
    def _required_secret(field_name: str, value: Any) -> str:
        if value is None:
            raise KakaoAuthError(f"{field_name} is not configured")

        secret = value.get_secret_value()
        if not secret:
            raise KakaoAuthError(f"{field_name} is not configured")

        return secret

    @staticmethod
    def _required_url(field_name: str, value: Any) -> str:
        if value is None:
            raise KakaoAuthError(f"{field_name} is not configured")

        return str(value)

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if isinstance(value, str) and value:
            return value
        return None

    @staticmethod
    def _required_kakao_id(value: Any) -> str:
        if isinstance(value, bool) or value is None:
            raise ValueError("Kakao id is required")

        kakao_id = str(value)
        if not kakao_id:
            raise ValueError("Kakao id is required")

        return kakao_id
