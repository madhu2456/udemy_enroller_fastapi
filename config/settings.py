"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    APP_NAME: str = "Udemy Course Enroller"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production-use-a-strong-secret-key"
    COOKIE_SECURE: bool = False
    ALLOWED_HOSTS: str = "*"
    # CORS origins - in production, set specific domains
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Database
    DATABASE_URL: str = "sqlite:///./udemy_enroller.db"
    AUTO_CREATE_TABLES: bool = False  # Use Alembic migrations by default

    # Redis (optional, for task queue)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Udemy
    UDEMY_EMAIL: str = ""
    UDEMY_PASSWORD: str = ""

    # Scraper defaults
    MAX_SCRAPER_WORKERS: int = 5
    SCRAPER_TIMEOUT: int = 30
    ENROLLMENT_BATCH_SIZE: int = 5

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"
    LOG_FORMAT: str = "json"  # "json" or "text"

    # Monitoring
    SENTRY_DSN: str = ""
    SENTRY_ENVIRONMENT: str = "development"

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_AUTH: str = "100/minute"
    RATE_LIMIT_API: str = "500/minute"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
