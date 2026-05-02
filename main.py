"""Main FastAPI application entry point - v2 Asynchronous with security & monitoring."""

import os
import sys
import asyncio

# Windows-specific event loop policy for reliable subprocess support
# MUST be set before any other imports that might initialize a loop
if sys.platform == "win32":
    try:
        from asyncio import WindowsProactorEventLoopPolicy
        asyncio.set_event_loop_policy(WindowsProactorEventLoopPolicy())
        
        # Monkeypatch to silence ConnectionResetError [WinError 10054]
        # This is a known issue on Windows with ProactorEventLoop
        from asyncio import proactor_events
        _original_call_connection_lost = proactor_events._ProactorBasePipeTransport._call_connection_lost

        def _patched_call_connection_lost(self, exc=None):
            try:
                _original_call_connection_lost(self, exc)
            except (ConnectionResetError, ConnectionAbortedError):
                pass

        proactor_events._ProactorBasePipeTransport._call_connection_lost = _patched_call_connection_lost
    except ImportError:
        pass # Fallback for older python versions if any

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from config.settings import get_settings
from app.logging_config import setup_logging
from app.models.database import create_tables, engine
from app.routers import auth, settings, enrollment, dashboard, seo

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

    # Clean up stale runs
    from app.models.database import SessionLocal, EnrollmentRun
    from sqlalchemy import update
    try:
        with SessionLocal() as db:
            db.execute(
                update(EnrollmentRun)
                .where(EnrollmentRun.status.in_(["pending", "scraping", "enrolling"]))
                .values(status="failed", error_message="Server restarted")
            )
            db.commit()
            logger.info("Cleaned up stale enrollment runs.")
    except Exception as e:
        logger.error(f"Failed to clean up stale runs: {e}")

    # Initialize app state
    from app.core.cache import SessionCache
    app.state.session_cache = SessionCache(max_size=100, default_ttl_seconds=3600)
    app.state.session_cache.start_cleanup_task()
    
    # Legacy alias for backward compatibility with auth.py
    app.state.udemy_clients = app.state.session_cache

    yield

    # Shutdown
    from app.core.constants import shutdown_event
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
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=5.0)
                logger.info("All enrollment tasks cancelled successfully.")
            except asyncio.TimeoutError:
                logger.warning("Timed out waiting for enrollment tasks to cancel.")
            except Exception as e:
                logger.error(f"Error during enrollment task cancellation: {e}")

        # Close all udemy clients
        session_cache = getattr(app.state, "session_cache", None)
        if session_cache:
            clients = list(session_cache.items())
            if clients:
                logger.info(f"Closing {len(clients)} Udemy client sessions...")
                for token, client in clients:
                    try:
                        await client.close()
                    except Exception as e:
                        logger.error(f"Error closing client {token}: {e}")
                logger.info("All Udemy client sessions closed.")
            await session_cache.stop_cleanup_task()

    except Exception as e:
        logger.error(f"Unexpected error during shutdown: {e}")

    logger.info("Shutting down Udemy Course Enroller API")



app_settings = get_settings()

app = FastAPI(
    title=app_settings.APP_NAME,
    version=app_settings.APP_VERSION,
    description="Automatically enroll in free/discounted Udemy courses (Async v2)",
    lifespan=lifespan,
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

@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    """Add long-lived cache headers to static files to improve Lighthouse score."""
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include routers
app.include_router(seo.router)
app.include_router(dashboard.router)
app.include_router(auth.router)
app.include_router(settings.router)
app.include_router(enrollment.router)


@app.get("/api/health")
async def health_check(request: Request):
    """Health check endpoint with dependency checks."""
    db_status = "healthy"
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {e}"

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "database": db_status,
        "version": app_settings.APP_VERSION,
    }
