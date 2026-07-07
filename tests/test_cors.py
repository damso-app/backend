from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_cors_preflight_allows_configured_local_origin() -> None:
    settings = Settings(
        _env_file=None,
        cors_origins=["http://localhost:3000", "http://localhost:3001"],
    )
    client = TestClient(create_app(settings))

    response = client.options(
        "/api/v1/auth/kakao/login-url",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["access-control-allow-credentials"] == "true"
