"""Main FastAPI application entry point."""

import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from config.settings import get_settings
from app.models.database import create_tables
from app.routers import auth, settings, enrollment, dashboard

# Ensure the Windows console can handle non-ASCII characters (e.g. Vietnamese,
# Arabic, Chinese course titles) without crashing the logging thread.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/app.log", mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # Startup
    os.makedirs("logs", exist_ok=True)
    os.makedirs("Courses", exist_ok=True)
    logger.info("Starting Udemy Course Enroller API")
    create_tables()
    logger.info("Database tables created")

    # Initialize app state
    app.state.udemy_clients = {}

    yield

    # Shutdown
    logger.info("Shutting down Udemy Course Enroller API")


app_settings = get_settings()

app = FastAPI(
    title=app_settings.APP_NAME,
    version=app_settings.APP_VERSION,
    description="Automatically enroll in free/discounted Udemy courses",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include routers
app.include_router(dashboard.router)
app.include_router(auth.router)
app.include_router(settings.router)
app.include_router(enrollment.router)


@app.get("/api/health")
async def health_check():
    """Health check endpoint for Digital Ocean monitoring."""
    return {
        "status": "healthy",
        "version": app_settings.APP_VERSION,
    }
