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
    # Supported providers: stub | ollama | openai | lmstudio | anthropic
    LLM_PROVIDER: str = "stub"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_BASE_URL: str | None = None
    OLLAMA_MODEL: str = "llama3.1"
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"

    # Auth
    AUTH_REQUIRED: bool = False

    # Dangerous operations
    ALLOW_RESET: bool = False

    # Notifications (Telegram)
    TELEGRAM_BOT_TOKEN: str | None = None
    TELEGRAM_CHAT_ID: str | None = None


settings = Settings()
