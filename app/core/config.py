from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Pydantic v2 style: use model_config, not inner Config
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",  # ignore unknown env keys instead of erroring
        case_sensitive=False,
    )

    # Core app
    APP_NAME: str = "DAWN"
    ENV: str = "dev"

    # Infra
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    POSTGRES_DSN: str | None = None  # e.g. postgresql+psycopg2://user:pass@host/db?sslmode=require
    AWS_REGION: str | None = None
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    S3_BUCKET: str | None = None
    S3_ENDPOINT_URL: str | None = None

    # Dependency enforcement (dev-only showcase defaults)
    REQUIRE_REDIS: bool = True
    REQUIRE_POSTGRES: bool = True

    # Upload and remote fetch limits (bytes)
    MAX_UPLOAD_BYTES: int = 25_000_000
    MAX_REMOTE_BYTES: int = 25_000_000

    # LLM knobs (safe defaults; can be overridden via .env)
    LLM_PROVIDER: str = "stub"  # stub | ollama | openai
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str | None = "gpt-4o-mini"
    OLLAMA_MODEL: str | None = "llama3.1"

    # Auth
    AUTH_REQUIRED: bool = False


settings = Settings()
