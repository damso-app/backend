from functools import lru_cache
from typing import Literal

from pydantic import AnyUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Damso API"
    environment: Literal["local", "development", "staging", "production"] = "local"
    api_v1_prefix: str = "/api/v1"

    database_url: str | None = None
    supabase_url: AnyUrl | None = None
    supabase_service_role_key: SecretStr | None = None
    jwt_secret: SecretStr | None = None
    openai_api_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
