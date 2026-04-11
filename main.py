"""Main FastAPI application entry point - v2 Asynchronous with security & monitoring."""

import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from config.settings import get_settings
from app.logging_config import setup_logging
from app.sentry_config import setup_sentry
from app.models.database import create_tables
from app.rate_limit_config import setup_rate_limiting, maybe_limit
from app.routers import auth, settings, enrollment, dashboard
from app.services.scheduler import EnrollmentScheduler

# Configure logging with JSON support
setup_logging()

# Configure Sentry for error tracking
setup_sentry()

# Ensure the Windows console can handle non-ASCII characters
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

scheduler = EnrollmentScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # Startup
    os.makedirs("logs", exist_ok=True)
    os.makedirs("Courses", exist_ok=True)
    logger.info("Starting Udemy Course Enroller API v2 (Async)")
    logger.info(f"Environment: {get_settings().SENTRY_ENVIRONMENT}")
    logger.info(f"Log format: {get_settings().LOG_FORMAT}")
    logger.info(f"Rate limiting: {'enabled' if get_settings().RATE_LIMIT_ENABLED else 'disabled'}")

    if get_settings().AUTO_CREATE_TABLES:
        logger.warning("AUTO_CREATE_TABLES is enabled; using metadata.create_all().")
        create_tables()
    else:
        logger.info("AUTO_CREATE_TABLES is disabled; expecting Alembic-managed schema.")

    # Clean up stale runs
    from app.models.database import SessionLocal, EnrollmentRun
    from sqlalchemy import update
    try:
        with SessionLocal() as db:
            db.execute(
                update(EnrollmentRun)
                .where(EnrollmentRun.status.in_(["scraping", "enrolling"]))
                .values(status="failed", error_message="Server restarted")
            )
            db.commit()
            logger.info("Cleaned up stale enrollment runs.")
    except Exception as e:
        logger.error(f"Failed to clean up stale runs: {e}")

    # Initialize app state
    app.state.udemy_clients = {}

    # Start background scheduler
    scheduler.start()

    yield

    # Shutdown
    scheduler.stop()
    logger.info("Shutting down Udemy Course Enroller API")


app_settings = get_settings()

app = FastAPI(
    title=app_settings.APP_NAME,
    version=app_settings.APP_VERSION,
    description="Automatically enroll in free/discounted Udemy courses (Async v2)",
    lifespan=lifespan,
)

# Rate Limiting
setup_rate_limiting(app)

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

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include routers
app.include_router(dashboard.router)
app.include_router(auth.router)
app.include_router(settings.router)
app.include_router(enrollment.router)


@app.get("/api/health")
@maybe_limit("60/minute")
async def health_check(request: Request):
    """Health check endpoint with dependency checks."""
    return {
        "status": "healthy",
        "version": app_settings.APP_VERSION,
        "scheduler": "running" if scheduler.scheduler.running else "stopped",
        "environment": app_settings.SENTRY_ENVIRONMENT,
        "rate_limiting": app_settings.RATE_LIMIT_ENABLED,
    }
