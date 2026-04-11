"""Sentry configuration for comprehensive error tracking and performance monitoring."""

try:
    import sentry_sdk
    from sentry_sdk.integrations.asyncio import AsyncioIntegration
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    SENTRY_AVAILABLE = True
except ModuleNotFoundError:
    sentry_sdk = None
    AsyncioIntegration = None
    FastApiIntegration = None
    SqlalchemyIntegration = None
    SENTRY_AVAILABLE = False

from config.settings import get_settings

settings = get_settings()


def setup_sentry():
    """Initialize Sentry for error tracking and performance monitoring."""
    if not settings.SENTRY_DSN or not SENTRY_AVAILABLE:
        return  # Sentry not configured

    assert sentry_sdk is not None
    assert FastApiIntegration is not None
    assert SqlalchemyIntegration is not None
    assert AsyncioIntegration is not None

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
            AsyncioIntegration(),
        ],
        traces_sample_rate=0.1,  # 10% of transactions for performance monitoring
        profiles_sample_rate=0.1,  # 10% for profiling
        attach_stacktrace=True,
        debug=settings.DEBUG,
        # Capture release for better grouping
        release="udemy-enroller@1.0.0",
        # Additional settings for better error capturing
        max_breadcrumbs=50,
        request_bodies="small",  # Include small request bodies
    )


def capture_exception(exc: Exception, level: str = "error") -> None:
    """Capture an exception in Sentry with context."""
    if not settings.SENTRY_DSN or not SENTRY_AVAILABLE:
        return

    assert sentry_sdk is not None
    with sentry_sdk.push_scope() as scope:
        scope.level = level
        sentry_sdk.capture_exception(exc)
