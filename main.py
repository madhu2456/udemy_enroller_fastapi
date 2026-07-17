"""Main FastAPI application entry point - v2 Asynchronous with security & monitoring."""

import asyncio
import os
import sys

# Windows-specific event loop policy for reliable subprocess support
# MUST be set before any other imports that might initialize a loop
if sys.platform == "win32":
    try:
        from asyncio import WindowsProactorEventLoopPolicy

        asyncio.set_event_loop_policy(WindowsProactorEventLoopPolicy())

        # Monkeypatch to silence ConnectionResetError [WinError 10054]
        # This is a known issue on Windows with ProactorEventLoop
        from asyncio import proactor_events

        _original_call_connection_lost = (
            proactor_events._ProactorBasePipeTransport._call_connection_lost
        )

        def _patched_call_connection_lost(self, exc=None):
            try:
                _original_call_connection_lost(self, exc)
            except (ConnectionResetError, ConnectionAbortedError):
                pass

        proactor_events._ProactorBasePipeTransport._call_connection_lost = (
            _patched_call_connection_lost
        )
    except ImportError:
        pass  # Fallback for older python versions if any

import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger

from app.logging_config import setup_logging
from app.models.database import create_tables, engine
from app.routers import auth, dashboard, enrollment, public_deals, seo, settings
from app.security import (
    _client_key,
    analytics_rate_limiter,
    csp_report_rate_limiter,
)
from config.settings import get_settings

# Configure logging with JSON support
setup_logging()

# Ensure the Windows console can handle non-ASCII characters
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    from app.core.constants import shutdown_event

    shutdown_event.clear()

    # Startup
    os.makedirs("logs", exist_ok=True)
    os.makedirs("Courses", exist_ok=True)
    os.makedirs("data", exist_ok=True)

    if sys.platform == "win32":
        try:
            loop = asyncio.get_running_loop()
            logger.info(f"Active event loop: {type(loop).__name__}")
        except Exception as e:
            logger.error(f"Error checking event loop: {e}")

    logger.info("Starting Udemy Course Enroller API v2 (Async)")
    logger.info(f"Log format: {get_settings().LOG_FORMAT}")

    if get_settings().AUTO_CREATE_TABLES:
        logger.warning("AUTO_CREATE_TABLES is enabled; using metadata.create_all().")
        create_tables()
    else:
        logger.info("AUTO_CREATE_TABLES is disabled; expecting Alembic-managed schema.")

    # Clean up stale runs — gracefully handle fresh database (table may not exist yet)
    try:
        from sqlalchemy import inspect, update

        from app.models.database import EnrollmentRun, SessionLocal

        with SessionLocal() as db:
            inspector = inspect(db.bind)
            if not inspector.has_table(EnrollmentRun.__tablename__):
                logger.info("No enrollment_runs table found — skipping stale run cleanup (fresh database).")
            else:
                db.execute(
                    update(EnrollmentRun)
                    .where(EnrollmentRun.status.in_(["pending", "scraping", "enrolling"]))
                    .values(status="failed", error_message="Server restarted")
                )
                db.commit()
                logger.info("Cleaned up stale enrollment runs.")
    except Exception as exc:
        logger.warning(f"Skipped stale run cleanup ({type(exc).__name__})")

    # Initialize app state
    from app.core.cache import SessionCache

    app.state.session_cache = SessionCache(max_size=100, default_ttl_seconds=3600)
    app.state.session_cache.start_cleanup_task()

    # Legacy alias for backward compatibility with auth.py
    app.state.udemy_clients = app.state.session_cache

    # Expose settings to templates via request.app.state
    _settings = get_settings()
    app.state.google_site_verification = _settings.GOOGLE_SITE_VERIFICATION
    app.state.bing_site_verification = _settings.BING_SITE_VERIFICATION
    app.state.gtm_container_id = _settings.GTM_CONTAINER_ID
    app.state.ga4_measurement_id = _settings.GA4_MEASUREMENT_ID
    app.state.deployment_env = _settings.DEPLOYMENT_ENV

    yield

    # Shutdown
    shutdown_event.set()

    logger.info("Server shutting down, cancelling active tasks...")
    try:
        from app.services.enrollment_manager import EnrollmentManager

        tasks = list(EnrollmentManager.active_tasks.values())
        if tasks:
            logger.info(f"Found {len(tasks)} active enrollment tasks to cancel.")
            for task in tasks:
                task.cancel()

            try:
                # Wait for tasks to handle cancellation (includes DB updates)
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), timeout=5.0
                )
                logger.info("All enrollment tasks cancelled successfully.")
            except asyncio.TimeoutError:
                logger.warning("Timed out waiting for enrollment tasks to cancel.")
            except Exception as exc:
                logger.error(
                    "Enrollment-task cancellation failed "
                    f"({type(exc).__name__})"
                )

    except Exception as exc:
        logger.error(f"Unexpected error during shutdown ({type(exc).__name__})")
    finally:
        try:
            # Close all udemy clients
            session_cache = getattr(app.state, "session_cache", None)
            if session_cache is not None:
                try:
                    clients = list(session_cache.items())
                    if clients:
                        logger.info(f"Closing {len(clients)} Udemy client sessions...")
                        for _token, client in clients:
                            try:
                                await client.close()
                            except Exception as exc:
                                logger.error(
                                    "Failed to close Udemy client session "
                                    f"({type(exc).__name__})"
                                )
                        logger.info("Finished Udemy client session shutdown.")
                finally:
                    try:
                        await session_cache.stop_cleanup_task()
                    except Exception as exc:
                        logger.error(
                            "Failed to stop session-cache cleanup task "
                            f"({type(exc).__name__})"
                        )
        except Exception as exc:
            logger.error(f"Unexpected error during shutdown ({type(exc).__name__})")

    logger.info("Shutting down Udemy Course Enroller API")


app_settings = get_settings()

# Disable auto-generated OpenAPI docs in production (server mode) for security
_docs_enabled = app_settings.DEPLOYMENT_ENV != "server"

app = FastAPI(
    title=app_settings.APP_NAME,
    version=app_settings.APP_VERSION,
    description="Automatically enroll in free/discounted Udemy courses (Async v2)",
    lifespan=lifespan,
    openapi_url="/openapi.json" if _docs_enabled else None,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
)

# CORS middleware - Restricted to specific origins with enhanced security
app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    expose_headers=["Content-Disposition"],  # For file downloads
    max_age=3600,  # Cache preflight for 1 hour
)

# Middleware to rewrite redirect Location headers to HTTPS in production
@app.middleware("http")
async def https_redirect_fix(request: Request, call_next):
    """Ensure redirect responses use HTTPS scheme in server mode."""
    response = await call_next(request)
    if (
        app_settings.DEPLOYMENT_ENV == "server"
        and response.status_code in (301, 302, 307, 308)
    ):
        location = response.headers.get("location", "")
        if location.startswith("http://"):
            response.headers["location"] = location.replace("http://", "https://", 1)
    return response

# GZip middleware to compress responses and lower TTFB / bandwidth
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def head_to_get(request: Request, call_next):
    """Convert HEAD requests to GET so public pages return 200 instead of 405."""
    if request.method == "HEAD":
        request.scope["method"] = "GET"
    response = await call_next(request)
    return response


@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    """Add central cache control headers to satisfy proxy policies and optimize page speed."""
    response = await call_next(request)
    path = request.url.path

    # Lightweight privacy-friendly page view logging (HTML pages only, no PII)
    if (
        not path.startswith("/static/")
        and not path.startswith("/api/")
        and request.method == "GET"
        and response.status_code == 200
        and "text/html" in response.headers.get("content-type", "")
    ):
        logger.info(f"[pageview] {path}")

    if path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path in {
        # Fully public, non-personalized content — short CDN/browser cache
        "/faq",
        "/about",
        "/guides",
        "/privacy",
        "/robots.txt",
        "/sitemap.xml",
        "/humans.txt",
        "/llms.txt",
        "/ai-profile.json",
        "/.well-known/security.txt",
        "/security.txt",
    }:
        # max-age=120: up to 2 minutes stale after deploy; SWR keeps serving while revalidating
        response.headers["Cache-Control"] = (
            "public, max-age=120, stale-while-revalidate=600"
        )
    elif path in {
        # Personalized or frequently changing — do not store
        "/",
        "/udemycoupons",
        "/dashboard",
        "/settings",
        "/history",
    } or path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        if path == "/":
            # Homepage may vary by session cookie (redirect vs marketing)
            response.headers["Vary"] = "Cookie"

    return response


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses with per-request CSP nonce."""
    nonce = secrets.token_urlsafe(16)
    request.state.nonce = nonce

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

    settings = get_settings()
    if settings.DEPLOYMENT_ENV == "server":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )
    # CSP with per-request nonce + strict-dynamic (modern XSS protection)
    # - 'strict-dynamic' propagates trust to scripts loaded by nonced scripts
    # - Domain allowlists are fallbacks for CSP level 2 browsers
    # - JSON-LD (application/ld+json) scripts are data, not governed by script-src
    # - script-src-attr 'unsafe-inline' allows onclick/onload handlers without
    #   compromising script-src nonce enforcement on <script> elements
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}' 'strict-dynamic' "
        "https://unpkg.com https://cdnjs.cloudflare.com https://www.googletagmanager.com; "
        "script-src-attr 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "img-src 'self' data: https:; "
        "font-src 'self' https://cdnjs.cloudflare.com; "
        "connect-src 'self' https://www.google-analytics.com; "
        "frame-src https://www.googletagmanager.com; "
        "base-uri 'self'; "
        "form-action 'self'; "
        f"report-uri /api/csp-violation"
    )
    return response


# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Template renderer for error pages
templates = Jinja2Templates(directory="app/templates")

# Include routers
app.include_router(seo.router)
app.include_router(dashboard.router)
app.include_router(auth.router)
app.include_router(settings.router)
app.include_router(enrollment.router)
app.include_router(public_deals.router)


@app.get(
    "/api/health",
    responses={503: {"description": "Database dependency unavailable"}},
)
async def health_check(request: Request, response: Response):
    """Health check endpoint with dependency checks."""
    db_status = "healthy"
    try:
        from sqlalchemy import text

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        # Do not expose exception details publicly
        logger.warning(f"Health check database probe failed ({type(exc).__name__})")
        db_status = "unhealthy"

    response.status_code = 200 if db_status == "healthy" else 503
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "database": db_status,
        "version": app_settings.APP_VERSION,
    }


_ALLOWED_ANALYTICS_EVENT_TYPES = frozenset(
    {
        "coupon_click",
        "cta_click",
        "enrollment_start",
        "enrollment_stop",
        "file_download",
        "login",
        "outbound_click",
        "scroll_depth",
    }
)


def _safe_analytics_event_type(value):
    """Return an approved analytics category without logging arbitrary input."""
    if not isinstance(value, str) or value not in _ALLOWED_ANALYTICS_EVENT_TYPES:
        return "unknown"
    return value


@app.post("/api/analytics/event")
async def track_analytics_event(request: Request):
    """Accept analytics events without retaining submitted target details.

    Only allowlisted event categories may be written at INFO level.
    """
    analytics_rate_limiter.raise_if_limited(_client_key(request))
    try:
        body = await request.json()
        if not isinstance(body, dict):
            return {"status": "ok"}

        event_type = _safe_analytics_event_type(body.get("type"))
        target = body.get("target")
        target_supplied = "true" if isinstance(target, str) and bool(target.strip()) else "false"
        logger.info(f"[analytics] event received (type={event_type}, target_supplied={target_supplied})")
    except Exception:
        pass
    return {"status": "ok"}


def _safe_csp_directive(value):
    """Return a bounded CSP directive token, or None for unsafe input."""
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        return None
    if not value.isascii() or not value[0].isalpha():
        return None
    if not all(character.isalnum() or character == "-" for character in value):
        return None
    return value.lower()


def _csp_report_log_summary(report):
    """Extract non-sensitive, validated fields from a legacy CSP report."""
    report_body = report.get("csp-report") if isinstance(report, dict) else None
    if not isinstance(report_body, dict):
        return "unknown", "unknown", "unknown"

    directive = _safe_csp_directive(report_body.get("effective-directive"))
    if directive is None:
        directive = _safe_csp_directive(report_body.get("violated-directive"))
    if directive is None:
        directive = "unknown"

    disposition = report_body.get("disposition")
    if not isinstance(disposition, str) or disposition not in {"enforce", "report"}:
        disposition = "unknown"

    status_code = report_body.get("status-code")
    if type(status_code) is not int or not 0 <= status_code <= 599:
        status_code = "unknown"

    return directive, disposition, status_code


@app.post("/api/csp-violation")
async def csp_violation(request: Request):
    """Receive and log CSP violation reports (rate-limited)."""
    csp_report_rate_limiter.raise_if_limited(_client_key(request))
    try:
        report = await request.json()
        directive, disposition, status_code = _csp_report_log_summary(report)
        logger.warning(
            f"CSP violation report received (directive={directive}, disposition={disposition}, status={status_code})"
        )
    except Exception as exc:
        logger.warning(f"CSP violation report rejected ({type(exc).__name__})")
    return Response(status_code=204)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Return an HTML 404 page instead of FastAPI's default JSON response."""
    return templates.TemplateResponse(request, "pages/404.html", status_code=404)
