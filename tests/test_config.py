from app.core.config import Settings


def test_kakao_oauth_settings_load_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "replace-with-jwt-secret-key")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    monkeypatch.setenv("LOGIN_CODE_EXPIRE_MINUTES", "5")
    monkeypatch.setenv("KAKAO_REST_API_KEY", "replace-with-kakao-rest-api-key")
    monkeypatch.setenv("KAKAO_CLIENT_SECRET", "replace-with-kakao-client-secret")
    monkeypatch.setenv(
        "KAKAO_REDIRECT_URI",
        "http://localhost:8000/api/v1/auth/kakao/callback",
    )
    monkeypatch.setenv(
        "FRONTEND_OAUTH_CALLBACK_URL",
        "http://localhost:3000/oauth/kakao/callback",
    )

    settings = Settings(_env_file=None)

    assert settings.jwt_secret_key is not None
    assert settings.jwt_secret_key.get_secret_value() == "replace-with-jwt-secret-key"
    assert settings.jwt_algorithm == "HS256"
    assert settings.access_token_expire_minutes == 60
    assert settings.login_code_expire_minutes == 5
    assert settings.kakao_rest_api_key is not None
    assert settings.kakao_rest_api_key.get_secret_value() == "replace-with-kakao-rest-api-key"
    assert settings.kakao_client_secret is not None
    assert settings.kakao_client_secret.get_secret_value() == "replace-with-kakao-client-secret"
    assert str(settings.kakao_redirect_uri) == "http://localhost:8000/api/v1/auth/kakao/callback"
    assert (
        str(settings.frontend_oauth_callback_url)
        == "http://localhost:3000/oauth/kakao/callback"
    )


def test_cors_origins_load_from_comma_separated_environment(monkeypatch) -> None:
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:3000, http://localhost:3001,,",
    )

    settings = Settings(_env_file=None)

    assert settings.cors_origins == [
        "http://localhost:3000",
        "http://localhost:3001",
    ]


def test_cors_origins_default_to_empty_list(monkeypatch) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    settings = Settings(_env_file=None)

    assert settings.cors_origins == []


def test_demo_mode_settings_load_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_DEMO_MODE", "true")
    monkeypatch.setenv("DEMO_USER_ID", "43")

    settings = Settings(_env_file=None)

    assert settings.enable_demo_mode is True
    assert settings.demo_user_id == 43
