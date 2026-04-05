"""Application configuration using Pydantic Settings."""

import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    APP_NAME: str = "Udemy Course Enroller"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production-use-a-strong-secret-key"
    ALLOWED_HOSTS: str = "*"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Database
    DATABASE_URL: str = "sqlite:///./udemy_enroller.db"

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
