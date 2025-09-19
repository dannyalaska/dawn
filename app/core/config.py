from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENV: str = "dev"
    APP_NAME: str = "DAWN"
    PORT: int = 8000

    POSTGRES_DSN: str | None = None

    AWS_REGION: str | None = None
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    S3_BUCKET: str | None = None
    S3_ENDPOINT_URL: str | None = None

    REDIS_URL: str = "redis://localhost:6379/1"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
