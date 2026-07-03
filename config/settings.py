"""Application configuration using Pydantic Settings."""

import secrets
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
    # Cookie encryption key — must be 32 bytes base64-encoded for Fernet.
    # Falls back to SECRET_KEY if not set (not recommended for production).
    COOKIE_ENCRYPTION_KEY: str = ""
    # Google Search Console verification code — set in .env after creating a GSC property
    GOOGLE_SITE_VERIFICATION: str = ""
    # Google Tag Manager container ID — set in .env (e.g. GTM-XXXXXXX)
    GTM_CONTAINER_ID: str = ""
    # Google Analytics 4 Measurement ID — set in .env (e.g. G-XXXXXXXXXX)
    # Used for direct GA4 gtag.js tracking (works independently of GTM)
    GA4_MEASUREMENT_ID: str = "G-GT1FDTC7Y6"
    # CORS origins - in production, set specific domains
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Database
    DATABASE_URL: str = "sqlite:///./udemy_enroller.db"
    AUTO_CREATE_TABLES: bool = False  # Use Alembic migrations by default

    # Udemy
    UDEMY_EMAIL: str = ""
    UDEMY_PASSWORD: str = ""

    # Scraper defaults
    MAX_SCRAPER_WORKERS: int = 5
    SCRAPER_SITE_TIMEOUT_SECONDS: int = 1800
    SCRAPER_RUN_TIMEOUT_SECONDS: int = 2700
    SCRAPER_TIMEOUT: int = 30  # Deprecated
    PROXIES: str = ""  # Comma-separated list of proxy URLs

    # Deployment environment: "local" or "server"
    # "server" applies stricter rate limits and adaptive backoff to avoid Udemy blocks
    DEPLOYMENT_ENV: str = "local"

    # Logging
    LOG_LEVEL: str = "WARNING"
    LOG_FILE: str = "logs/app.log"
    LOG_FORMAT: str = "json"  # "json" or "text"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    from pydantic import model_validator

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        # Generate a random SECRET_KEY if the default is detected
        _insecure_keys = (
            "change-me-in-production-use-a-strong-secret-key",
            "change-me-in-production",
            "change-me",
            "",
        )
        if self.SECRET_KEY in _insecure_keys:
            self.SECRET_KEY = secrets.token_hex(32)

        if self.DEPLOYMENT_ENV == "server":
            self.COOKIE_SECURE = True
        return self


@lru_cache()
def get_settings() -> Settings:
    return Settings()
