from collections.abc import Iterator
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.api.v1.auth import get_kakao_login_service
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.main import app
from app.services.kakao_auth_service import KakaoAuthError
from app.services.kakao_login_service import KakaoLoginResult


class FakeKakaoLoginService:
    async def login_with_authorization_code(self, db, *, code: str) -> KakaoLoginResult:
        assert code == "test-code"
        return KakaoLoginResult(
            redirect_url="http://localhost:3000/oauth/kakao/callback?loginCode=mock-login-code",
            login_code="mock-login-code",
        )


class FailingKakaoLoginService:
    async def login_with_authorization_code(self, db, *, code: str) -> KakaoLoginResult:
        raise KakaoAuthError("Kakao token exchange failed")


@pytest.fixture
def client() -> Iterator[TestClient]:
    def override_settings() -> Settings:
        return Settings(
            _env_file=None,
            kakao_rest_api_key="test-kakao-rest-api-key",
            kakao_client_secret="test-kakao-client-secret",
            kakao_redirect_uri="http://testserver/api/v1/auth/kakao/callback",
            frontend_oauth_callback_url="http://localhost:3000/oauth/kakao/callback",
        )

    def override_db():
        yield None

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_kakao_login_service] = lambda: FakeKakaoLoginService()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_create_kakao_login_url(client: TestClient) -> None:
    response = client.get("/api/v1/auth/kakao/login-url")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"loginUrl", "state"}
    assert body["state"]

    parsed_url = urlparse(body["loginUrl"])
    query = parse_qs(parsed_url.query)

    assert parsed_url.scheme == "https"
    assert parsed_url.netloc == "kauth.kakao.com"
    assert parsed_url.path == "/oauth/authorize"
    assert query["client_id"] == ["test-kakao-rest-api-key"]
    assert query["redirect_uri"] == ["http://testserver/api/v1/auth/kakao/callback"]
    assert query["response_type"] == ["code"]
    assert query["state"] == [body["state"]]
    assert "access_token" not in body["loginUrl"]
    assert "test-kakao-client-secret" not in body["loginUrl"]


def test_kakao_callback_redirects_with_login_code_only(client: TestClient) -> None:
    response = client.get(
        "/api/v1/auth/kakao/callback?code=test-code&state=test-state",
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = response.headers["location"]
    parsed_url = urlparse(location)
    query = parse_qs(parsed_url.query)

    assert parsed_url.geturl().startswith("http://localhost:3000/oauth/kakao/callback")
    assert query == {"loginCode": ["mock-login-code"]}
    assert "accessToken" not in query
    assert "kakaoAccessToken" not in query
    assert "test-code" not in location


def test_kakao_callback_requires_code(client: TestClient) -> None:
    response = client.get("/api/v1/auth/kakao/callback?state=test-state")

    assert response.status_code == 400
    assert response.json() == {"detail": "Kakao authorization code is required"}


def test_kakao_callback_provider_failure_returns_stable_error(client: TestClient) -> None:
    app.dependency_overrides[get_kakao_login_service] = lambda: FailingKakaoLoginService()

    response = client.get(
        "/api/v1/auth/kakao/callback?code=test-code&state=test-state",
        follow_redirects=False,
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Kakao authentication failed"}
