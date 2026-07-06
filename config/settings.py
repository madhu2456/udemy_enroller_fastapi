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
    # Cookie encryption key — must be 32 bytes base64-encoded for Fernet.
    # Falls back to SECRET_KEY if not set (not recommended for production).
    COOKIE_ENCRYPTION_KEY: str = ""
    # Google Search Console verification code — set in .env after creating a GSC property
    GOOGLE_SITE_VERIFICATION: str = ""
    # Bing Webmaster Tools verification code — set in .env after creating a Bing property
    BING_SITE_VERIFICATION: str = ""
    # Google Tag Manager container ID
    GTM_CONTAINER_ID: str = "GTM-5JHNVN6K"
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

    # Redis (optional, for task queue)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Scraper defaults
    MAX_SCRAPER_WORKERS: int = 5
    SCRAPER_SITE_TIMEOUT_SECONDS: int = 1800
    SCRAPER_RUN_TIMEOUT_SECONDS: int = 2700
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
        extra="ignore",
    )

    from pydantic import model_validator

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.DEPLOYMENT_ENV == "server":
            # Fail closed: require strong SECRET_KEY in production
            if len(self.SECRET_KEY) < 32:
                raise ValueError(
                    "SECRET_KEY must be at least 32 characters long in server mode. "
                    "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
                )
            # Require explicit encryption key in production (no fallback to derived key)
            if not self.COOKIE_ENCRYPTION_KEY:
                raise ValueError(
                    "COOKIE_ENCRYPTION_KEY must be set in server mode. "
                    "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
                )
            self.COOKIE_SECURE = True
        else:
            # Local development: auto-generate on insecure defaults for convenience
            _insecure_keys = (
                "change-me-in-production-use-a-strong-secret-key",
                "change-me-in-production",
                "change-me",
                "",
            )
            if self.SECRET_KEY in _insecure_keys:
                self.SECRET_KEY = secrets.token_hex(32)
        return self


@lru_cache()
def get_settings() -> Settings:
    return Settings()
