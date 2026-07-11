"""Settings router for managing user enrollment preferences."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from loguru import logger

from app.models.database import (
    get_db,
    UserSettings,
    User,
    UserSession,
    EnrollmentRun,
    EnrolledCourse,
)
from app.deps import get_current_user_id
from app.schemas.schemas import SettingsUpdate, SettingsResponse
from app.security import verify_csrf_token
from app.security import validate_proxy_url
from config.settings import get_settings as get_app_settings
from app.core.cache import clear_user_caches
from sqlalchemy import delete, update

router = APIRouter(prefix="/api/settings", tags=["Settings"])
app_settings = get_app_settings()


def get_or_create_settings(db: Session, user_id: int) -> UserSettings:
    """Helper to ensure a settings record exists for the user."""
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not settings:
        logger.info(f"Auto-creating missing UserSettings for user {user_id}")
        settings = UserSettings(user_id=user_id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.get("/", response_model=SettingsResponse)
@router.get("", response_model=SettingsResponse, include_in_schema=False)
async def get_settings(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Get current user settings with guaranteed defaults."""
    settings = get_or_create_settings(db, user_id)

    def safe_merge(user_val, default_func):
        defaults = default_func()
        if not isinstance(user_val, dict):
            return defaults

        # Merge logic:
        # 1. Take all keys from defaults (ensures new scrapers are added)
        # 2. Use user's value if it exists for a key
        # 3. Use default value if key is new
        merged = defaults.copy()
        for k, v in user_val.items():
            if k in merged:
                merged[k] = bool(v)

        # If the user has stale keys that are NO LONGER in defaults (like Discudemy),
        # they will be naturally excluded because we started with a copy of defaults.
        return merged

    return SettingsResponse(
        sites=safe_merge(settings.sites, UserSettings.default_sites),
        languages=safe_merge(settings.languages, UserSettings.default_languages),
        categories=safe_merge(settings.categories, UserSettings.default_categories),
        instructor_exclude=settings.instructor_exclude or [],
        title_exclude=settings.title_exclude or [],
        min_rating=float(settings.min_rating or 0.0),
        course_update_threshold_months=int(
            settings.course_update_threshold_months or 24
        ),
        save_txt=bool(settings.save_txt),
        discounted_only=bool(settings.discounted_only),
        proxy_url=settings.proxy_url,
    )


@router.put("/", include_in_schema=True)
async def update_settings(
    update: SettingsUpdate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    _csrf: None = Depends(verify_csrf_token),
):
    """Update user settings."""
    settings = get_or_create_settings(db, user_id)

    update_data = update.model_dump(exclude_unset=True)

    # Validate proxy URL if provided
    if "proxy_url" in update_data and update_data["proxy_url"]:
        if not validate_proxy_url(update_data["proxy_url"]):
            logger.warning(
                f"Invalid proxy URL provided by user {user_id}: {update_data['proxy_url']}"
            )
            raise HTTPException(status_code=400, detail="Invalid proxy URL format")

    for field, value in update_data.items():
        if value is not None:
            setattr(settings, field, value)

    db.commit()
    logger.info(f"Settings updated for user {user_id}")

    # Clear cache to ensure any stats derived from settings are refreshed
    clear_user_caches(user_id)

    return {"status": "success", "message": "Settings updated"}


@router.post("/reset")
async def reset_settings(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    _csrf: None = Depends(verify_csrf_token),
):
    """Reset settings to defaults."""
    settings = get_or_create_settings(db, user_id)

    # Reset using static default methods
    settings.sites = UserSettings.default_sites()
    settings.languages = UserSettings.default_languages()
    settings.categories = UserSettings.default_categories()
    settings.instructor_exclude = []
    settings.title_exclude = []
    settings.min_rating = 0.0
    settings.course_update_threshold_months = 24
    settings.save_txt = False
    settings.discounted_only = False
    settings.proxy_url = None

    db.commit()
    logger.info(f"Settings reset to defaults for user {user_id}")

    # Clear cache to ensure any stats derived from settings are refreshed
    clear_user_caches(user_id)

    return {"status": "success", "message": "Settings reset to defaults"}


@router.post("/clear-data")
async def clear_data(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    _csrf: None = Depends(verify_csrf_token),
):
    """Delete enrollment history/stats, app sessions, and stored Udemy cookies.

    Keeps the local user row and preference settings so the account can re-connect.
    """
    # Check for active run
    active_run = (
        db.query(EnrollmentRun)
        .filter(
            EnrollmentRun.user_id == user_id,
            EnrollmentRun.status.in_(["pending", "scraping", "enrolling"]),
        )
        .first()
    )

    if active_run:
        raise HTTPException(
            status_code=400,
            detail="Cannot clear data while an enrollment run is active",
        )

    try:
        # 1. Delete all enrolled courses associated with the user's runs
        # Correlated delete avoids race condition between SELECT and DELETE
        from sqlalchemy import select

        subq = select(EnrollmentRun.id).where(EnrollmentRun.user_id == user_id).scalar_subquery()
        db.execute(delete(EnrolledCourse).where(EnrolledCourse.enrollment_run_id.in_(subq)))

        # 2. Delete all enrollment runs
        db.execute(delete(EnrollmentRun).where(EnrollmentRun.user_id == user_id))

        # 3. Collect session tokens before deleting sessions (for cache cleanup)
        session_tokens = [
            row[0]
            for row in db.query(UserSession.token)
            .filter(UserSession.user_id == user_id)
            .all()
        ]

        # 4. Delete all app sessions for this user
        db.execute(delete(UserSession).where(UserSession.user_id == user_id))

        # 5. Reset lifetime stats and wipe encrypted Udemy cookies
        db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                total_enrolled=0,
                total_already_enrolled=0,
                total_expired=0,
                total_excluded=0,
                total_amount_saved=0.0,
                udemy_cookies=None,
            )
        )

        db.commit()
        logger.info(
            f"Cleared history, stats, sessions, and Udemy cookies for user {user_id}"
        )

        # Close in-memory Udemy clients for this user's sessions
        cache = getattr(request.app.state, "session_cache", None)
        for tok in session_tokens:
            client = None
            if cache is not None:
                client = cache.pop(tok, None)
            if client is None and hasattr(request.app.state, "udemy_clients"):
                clients = request.app.state.udemy_clients
                if clients is not cache and clients is not None and hasattr(clients, "pop"):
                    client = clients.pop(tok, None)
            if client is not None:
                try:
                    close_res = client.close()
                    if asyncio.iscoroutine(close_res):
                        await close_res
                except Exception as e:
                    logger.error(f"Error closing client during clear-data: {e}")

        # Clear dashboard caches
        clear_user_caches(user_id)

        response = JSONResponse(
            content={
                "status": "success",
                "message": (
                    "Enrollment history, statistics, sessions, and stored Udemy "
                    "cookies were cleared. Connect again to use enrollment."
                ),
            }
        )
        # Force re-auth in the browser
        response.delete_cookie("session_id", path="/", domain=None)
        response.delete_cookie("csrf_token", path="/", domain=None)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        return response
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to clear data for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear database records")
