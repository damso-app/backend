from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, AnyUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "Damso API"
    environment: Literal["local", "development", "staging", "production"] = "local"
    api_v1_prefix: str = "/api/v1"

    database_url: str | None = None
    supabase_url: AnyUrl | None = None
    supabase_service_role_key: SecretStr | None = None
    jwt_secret: SecretStr | None = None
    jwt_secret_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("JWT_SECRET_KEY", "JWT_SECRET"),
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    login_code_expire_minutes: int = 5
    openai_api_key: SecretStr | None = None
    kakao_rest_api_key: SecretStr | None = None
    kakao_client_secret: SecretStr | None = None
    kakao_redirect_uri: AnyUrl | None = None
    frontend_oauth_callback_url: AnyUrl | None = None
    gcs_bucket_name: str | None = None
    gcs_signed_url_expire_minutes: int = 15
    gcs_signer_service_account: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
