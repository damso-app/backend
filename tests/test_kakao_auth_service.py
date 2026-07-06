from urllib.parse import parse_qs

import httpx
import pytest

from app.core.config import Settings
from app.schemas.auth import KakaoUserInfo
from app.services.kakao_auth_service import (
    KAKAO_TOKEN_URL,
    KAKAO_USERINFO_URL,
    KakaoAuthError,
    KakaoAuthService,
)

MOCK_PROVIDER_BEARER = "mock-provider-bearer"


def make_settings(*, client_secret: str | None = "test-kakao-client-secret") -> Settings:
    return Settings(
        _env_file=None,
        kakao_rest_api_key="test-kakao-rest-api-key",
        kakao_client_secret=client_secret,
        kakao_redirect_uri="http://testserver/api/v1/auth/kakao/callback",
    )


@pytest.mark.anyio
async def test_exchange_code_for_token_success() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert str(request.url) == KAKAO_TOKEN_URL
        assert request.method == "POST"
        assert request.headers["content-type"] == "application/x-www-form-urlencoded"

        form = parse_qs(request.content.decode())
        assert form["grant_type"] == ["authorization_code"]
        assert form["client_id"] == ["test-kakao-rest-api-key"]
        assert form["redirect_uri"] == ["http://testserver/api/v1/auth/kakao/callback"]
        assert form["code"] == ["test-authorization-code"]
        assert form["client_secret"] == ["test-kakao-client-secret"]

        return httpx.Response(
            200,
            json={
                "access_token": MOCK_PROVIDER_BEARER,
                "token_type": "bearer",
                "refresh_token": "test-kakao-refresh-token",
                "expires_in": 21599,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = KakaoAuthService(make_settings(), client=client)

        token = await service.exchange_code_for_token("test-authorization-code")

    assert len(requests) == 1
    assert token.access_token == MOCK_PROVIDER_BEARER
    assert token.token_type == "bearer"
    assert token.refresh_token == "test-kakao-refresh-token"


@pytest.mark.anyio
async def test_exchange_code_for_token_omits_missing_client_secret() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        form = parse_qs(request.content.decode())
        assert "client_secret" not in form
        return httpx.Response(
            200,
            json={
                "access_token": MOCK_PROVIDER_BEARER,
                "token_type": "bearer",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = KakaoAuthService(make_settings(client_secret=None), client=client)

        token = await service.exchange_code_for_token("test-authorization-code")

    assert token.access_token == MOCK_PROVIDER_BEARER


@pytest.mark.anyio
async def test_exchange_code_for_token_failure() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(401, json={"error": "invalid"})
        )
    ) as client:
        service = KakaoAuthService(make_settings(), client=client)

        with pytest.raises(KakaoAuthError) as exc_info:
            await service.exchange_code_for_token("invalid-code")

    assert str(exc_info.value) == "Kakao token exchange failed"
    assert exc_info.value.status_code == 401


@pytest.mark.anyio
async def test_exchange_code_for_token_missing_access_token_fails() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"token_type": "bearer"})
        )
    ) as client:
        service = KakaoAuthService(make_settings(), client=client)

        with pytest.raises(KakaoAuthError) as exc_info:
            await service.exchange_code_for_token("test-authorization-code")

    assert str(exc_info.value) == "Kakao token response is invalid"


@pytest.mark.anyio
async def test_exchange_code_for_token_invalid_json_fails() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"{"))
    ) as client:
        service = KakaoAuthService(make_settings(), client=client)

        with pytest.raises(KakaoAuthError) as exc_info:
            await service.exchange_code_for_token("test-authorization-code")

    assert str(exc_info.value) == "Kakao response is invalid JSON"


@pytest.mark.anyio
async def test_get_user_info_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == KAKAO_USERINFO_URL
        assert request.method == "GET"
        assert request.headers["authorization"] == f"Bearer {MOCK_PROVIDER_BEARER}"
        return httpx.Response(
            200,
            json={
                "id": 123456789,
                "kakao_account": {
                    "email": "user@example.com",
                    "profile": {
                        "nickname": "Damso User",
                        "profile_image_url": "https://example.com/profile.jpg",
                    },
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = KakaoAuthService(make_settings(), client=client)

        user_info = await service.get_user_info(MOCK_PROVIDER_BEARER)

    assert user_info.kakao_id == "123456789"
    assert user_info.nickname == "Damso User"
    assert user_info.email == "user@example.com"
    assert str(user_info.profile_image_url) == "https://example.com/profile.jpg"


@pytest.mark.anyio
async def test_get_user_info_uses_thumbnail_image_url_as_fallback() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "id": 123456789,
                    "kakao_account": {
                        "profile": {
                            "nickname": "Damso User",
                            "thumbnail_image_url": "https://example.com/thumb.jpg",
                        },
                    },
                },
            )
        )
    ) as client:
        service = KakaoAuthService(make_settings(), client=client)

        user_info = await service.get_user_info(MOCK_PROVIDER_BEARER)

    assert str(user_info.profile_image_url) == "https://example.com/thumb.jpg"


@pytest.mark.anyio
async def test_get_user_info_prefers_profile_image_url_over_thumbnail() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "id": 123456789,
                    "kakao_account": {
                        "profile": {
                            "profile_image_url": "https://example.com/profile.jpg",
                            "thumbnail_image_url": "https://example.com/thumb.jpg",
                        },
                    },
                },
            )
        )
    ) as client:
        service = KakaoAuthService(make_settings(), client=client)

        user_info = await service.get_user_info(MOCK_PROVIDER_BEARER)

    assert str(user_info.profile_image_url) == "https://example.com/profile.jpg"


@pytest.mark.anyio
async def test_get_user_info_allows_nullable_profile_fields() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"id": 123456789}))
    ) as client:
        service = KakaoAuthService(make_settings(), client=client)

        user_info = await service.get_user_info(MOCK_PROVIDER_BEARER)

    assert user_info.kakao_id == "123456789"
    assert user_info.nickname is None
    assert user_info.email is None
    assert user_info.profile_image_url is None


@pytest.mark.anyio
async def test_get_user_info_failure() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500, json={"msg": "failed"}))
    ) as client:
        service = KakaoAuthService(make_settings(), client=client)

        with pytest.raises(KakaoAuthError) as exc_info:
            await service.get_user_info(MOCK_PROVIDER_BEARER)

    assert str(exc_info.value) == "Kakao userinfo request failed"
    assert exc_info.value.status_code == 500


@pytest.mark.anyio
async def test_get_user_info_missing_id_fails() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"kakao_account": {}})
        )
    ) as client:
        service = KakaoAuthService(make_settings(), client=client)

        with pytest.raises(KakaoAuthError) as exc_info:
            await service.get_user_info(MOCK_PROVIDER_BEARER)

    assert str(exc_info.value) == "Kakao userinfo response is invalid"


@pytest.mark.anyio
async def test_get_user_info_null_id_fails() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"id": None}))
    ) as client:
        service = KakaoAuthService(make_settings(), client=client)

        with pytest.raises(KakaoAuthError) as exc_info:
            await service.get_user_info(MOCK_PROVIDER_BEARER)

    assert str(exc_info.value) == "Kakao userinfo response is invalid"


@pytest.mark.anyio
async def test_get_user_info_invalid_json_fails() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"{"))
    ) as client:
        service = KakaoAuthService(make_settings(), client=client)

        with pytest.raises(KakaoAuthError) as exc_info:
            await service.get_user_info(MOCK_PROVIDER_BEARER)

    assert str(exc_info.value) == "Kakao response is invalid JSON"


def test_kakao_user_info_schema_does_not_include_kakao_access_token() -> None:
    assert "access_token" not in KakaoUserInfo.model_fields
