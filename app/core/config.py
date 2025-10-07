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

    # LLM knobs (safe defaults; can be overridden via .env)
    LLM_PROVIDER: str = "stub"  # stub | ollama | openai
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str | None = "gpt-4o-mini"
    OLLAMA_MODEL: str | None = "llama3.1"


settings = Settings()
