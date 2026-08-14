"""Application configuration using Pydantic Settings."""

import secrets
from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic_settings import BaseSettings, SettingsConfigDict

# Known placeholder / example secret keys that must never pass server validation.
# Used ONLY by the server-mode gate.
_INSECURE_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "change-me-in-production-use-a-strong-secret-key",
        "change-me-to-a-random-string-in-production",
        "change-me-in-production",
        "change-me",
        "",
    }
)

# Legacy local-mode blocklist: local mode auto-generates a fresh SECRET_KEY only
# for these markers. Deliberately EXCLUDES the 42-char .env.example placeholder
# ("change-me-to-a-random-string-in-production") so local development keeps a
# stable SECRET_KEY — and thus a stable derived cookie key — across restarts.
_INSECURE_LOCAL_AUTOGEN_KEYS: frozenset[str] = frozenset(
    {
        "change-me-in-production-use-a-strong-secret-key",
        "change-me-in-production",
        "change-me",
        "",
    }
)


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
    # Google Tag Manager container ID — set in production .env only (no hard-coded default)
    GTM_CONTAINER_ID: str = ""
    # Google Analytics 4 Measurement ID — set in production .env only (e.g. G-XXXXXXXXXX)
    # Used for direct GA4 gtag.js tracking (works independently of GTM)
    GA4_MEASUREMENT_ID: str = ""
    # CORS origins - in production, set specific domains
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Public base URL (e.g. https://udemyenroller.madhudadi.in). When set, the
    # login CSRF origin gate compares the browser Origin/Referer netloc against
    # this value instead of request.base_url — required behind Cloudflare
    # Flexible SSL, where nginx forwards X-Forwarded-Proto: http ($scheme)
    # while browsers send https Origins.
    PUBLIC_BASE_URL: str = ""

    # Trusted reverse-proxy / loopback peer IPs. _client_key() (app/security.py)
    # trusts X-Forwarded-For ONLY when the direct TCP peer is in this list, then
    # walks the chain right-to-left past these proxies to the real client.
    # Docker topology: compose publishes "127.0.0.1:8000:8000", so the app's TCP
    # peer is the bridge gateway (e.g. 172.18.0.1), NOT 127.0.0.1.
    # docker-entrypoint.sh resolves that gateway at startup and exports
    # TRUSTED_PROXY_IPS with it included. Never trust a proxy IP without the
    # loopback bind (an untrusted peer spoofs per-IP rate-limit buckets), and
    # never widen this list manually unless the deployment truly routes through
    # that peer. Env var:
    # TRUSTED_PROXY_IPS='["127.0.0.1","::1"]' (JSON list, pydantic-settings v2).
    TRUSTED_PROXY_IPS: list[str] = ["127.0.0.1", "::1"]

    # Database
    DATABASE_URL: str = "sqlite:///./udemy_enroller.db"
    AUTO_CREATE_TABLES: bool = False  # Use Alembic migrations by default

    # Public coupons catalog ( /udemycoupons ). Empty = project-root public_deals.json.
    # In Docker set to a path on the data volume so checker updates survive rebuilds:
    #   PUBLIC_DEALS_PATH=/app/data/public_deals.json
    PUBLIC_DEALS_PATH: str = ""

    # Background coupon checker loop interval (seconds). Used by
    # scripts/coupon_checker_loop.py / docker compose coupon-checker service.
    COUPON_CHECKER_INTERVAL_SECONDS: int = 7200  # 2 hours

    # Redis (optional, for task queue)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Upstash Redis REST (optional) — shared rate-limit buckets across app
    # instances. RateLimiter.is_allowed_redis() is active ONLY when BOTH are
    # set; otherwise it fails open to per-instance in-memory limiting. Never
    # set one without the other.
    UPSTASH_REDIS_REST_URL: str = ""
    UPSTASH_REDIS_REST_TOKEN: str = ""

    # Scraper defaults
    MAX_SCRAPER_WORKERS: int = 5
    SCRAPER_SITE_TIMEOUT_SECONDS: int = 1800
    SCRAPER_RUN_TIMEOUT_SECONDS: int = 2700
    PROXIES: str = ""  # Comma-separated list of proxy URLs

    # Deployment environment: "local" or "server"
    # "server" applies stricter rate limits and adaptive backoff to avoid Udemy blocks
    DEPLOYMENT_ENV: str = "local"

    # Max concurrent non-expired app sessions per user (login creates a new one).
    # Oldest sessions are revoked when the cap is exceeded. Set 0 to disable.
    MAX_SESSIONS_PER_USER: int = 3

    # Stuck-run detection (F-ENRL-O01): the in-process sweeper marks runs whose
    # last_heartbeat is older than STALE_RUN_TIMEOUT_MINUTES as failed, and
    # runs every STALE_RUN_SWEEP_SECONDS.
    STALE_RUN_TIMEOUT_MINUTES: int = 15
    STALE_RUN_SWEEP_SECONDS: int = 60

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

    from pydantic import field_validator, model_validator

    @field_validator("STALE_RUN_SWEEP_SECONDS")
    @classmethod
    def _clamp_sweep_interval(cls, v: int) -> int:
        """Sweeper interval must be >= 1s; a non-positive value would otherwise
        raise ValueError inside the sweeper task (asyncio.sleep(0)) and kill the
        recovery loop (F-ENRL-O01)."""
        return max(1, v)

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.DEPLOYMENT_ENV == "server":
            # Fail closed: require strong SECRET_KEY in production
            if len(self.SECRET_KEY) < 32:
                raise ValueError(
                    "SECRET_KEY must be at least 32 characters long in server mode. "
                    "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
                )
            # minimum-entropy gate, not a strength guarantee
            if (
                self.SECRET_KEY in _INSECURE_SECRET_KEYS
                or len(set(self.SECRET_KEY)) == 1
            ):
                raise ValueError(
                    "SECRET_KEY is a known placeholder or low-entropy value in server mode. "
                    'Generate a strong random key with: python -c "import secrets; print(secrets.token_hex(32))"'
                )
            # Require explicit Fernet-format encryption key in production (no fallback to derived key)
            try:
                Fernet(self.COOKIE_ENCRYPTION_KEY)
            except (ValueError, TypeError):
                raise ValueError(
                    "COOKIE_ENCRYPTION_KEY must be a valid Fernet key (44-char urlsafe base64) in server mode. "
                    'Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
                )
            self.COOKIE_SECURE = True
        else:
            # Local development: auto-generate on insecure defaults for convenience
            if self.SECRET_KEY in _INSECURE_LOCAL_AUTOGEN_KEYS:
                self.SECRET_KEY = secrets.token_hex(32)
        return self


@lru_cache()
def get_settings() -> Settings:
    return Settings()
