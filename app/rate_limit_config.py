"""Rate limiting configuration using slowapi."""

import logging
from typing import Callable, TypeVar

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from config.settings import get_settings

logger = logging.getLogger(__name__)

try:
    from slowapi import Limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address
    SLOWAPI_AVAILABLE = True
except ModuleNotFoundError:
    SLOWAPI_AVAILABLE = False

    class RateLimitExceeded(Exception):
        """Fallback exception when slowapi is unavailable."""

        def __init__(self, detail: str = "Rate limiting backend not available"):
            self.detail = detail
            super().__init__(detail)

    class Limiter:  # type: ignore[no-redef]
        """Fallback no-op limiter used when slowapi is unavailable."""

        def __init__(self, *args, **kwargs):
            pass

        def limit(self, _limit: str):
            def _decorator(func):
                return func

            return _decorator

    def get_remote_address(request) -> str:  # type: ignore[no-redef]
        return "unknown"

settings = get_settings()

limiter = Limiter(key_func=get_remote_address)

F = TypeVar("F", bound=Callable)


def maybe_limit(limit: str) -> Callable[[F], F]:
    """Apply a rate limit decorator only when rate limiting is enabled."""
    if not settings.RATE_LIMIT_ENABLED or not SLOWAPI_AVAILABLE:
        def _passthrough(func: F) -> F:
            return func

        return _passthrough

    return limiter.limit(limit)


def _rate_limit_exceeded_handler(request, exc):
    """Return a structured 429 response when a limit is exceeded."""
    detail = getattr(exc, "detail", str(exc))
    return JSONResponse(
        status_code=429,
        content={
            "status": "error",
            "message": "Rate limit exceeded",
            "detail": str(detail),
        },
    )


def setup_rate_limiting(app: FastAPI) -> None:
    """Setup rate limiting on FastAPI app."""
    if not settings.RATE_LIMIT_ENABLED:
        return
    if not SLOWAPI_AVAILABLE:
        logger.warning("RATE_LIMIT_ENABLED=true but slowapi is not installed; rate limiting disabled.")
        return

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
