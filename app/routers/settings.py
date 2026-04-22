"""Settings router for managing user enrollment preferences."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from loguru import logger

from app.models.database import get_db, UserSettings, User, EnrollmentRun, EnrolledCourse
from app.deps import get_current_user_id
from app.rate_limit_config import maybe_limit
from app.schemas.schemas import SettingsUpdate, SettingsResponse
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
        if not isinstance(user_val, dict) or not user_val:
            return defaults
        # Ensure all default keys exist in the user dict
        merged = defaults.copy()
        merged.update(user_val)
        return merged

    return SettingsResponse(
        sites=safe_merge(settings.sites, UserSettings.default_sites),
        languages=safe_merge(settings.languages, UserSettings.default_languages),
        categories=safe_merge(settings.categories, UserSettings.default_categories),
        instructor_exclude=settings.instructor_exclude or [],
        title_exclude=settings.title_exclude or [],
        min_rating=float(settings.min_rating or 0.0),
        course_update_threshold_months=int(settings.course_update_threshold_months or 24),
        save_txt=bool(settings.save_txt),
        discounted_only=bool(settings.discounted_only),
        proxy_url=settings.proxy_url,
        enable_headless=bool(settings.enable_headless),
        firecrawl_api_key=settings.firecrawl_api_key,
    )


@router.put("/", include_in_schema=True)
@router.put("", include_in_schema=False)
@maybe_limit(app_settings.RATE_LIMIT_API)
async def update_settings(
    request: Request,
    settings_update: SettingsUpdate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Update user settings."""
    settings = get_or_create_settings(db, user_id)

    update_data = settings_update.model_dump(exclude_unset=True)
    
    # Validate proxy URL if provided
    if "proxy_url" in update_data and update_data["proxy_url"]:
        if not validate_proxy_url(update_data["proxy_url"]):
            logger.warning(f"Invalid proxy URL provided by user {user_id}: {update_data['proxy_url']}")
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
@maybe_limit(app_settings.RATE_LIMIT_API)
async def reset_settings(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
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
    settings.enable_headless = False
    settings.firecrawl_api_key = None

    db.commit()
    logger.info(f"Settings reset to defaults for user {user_id}")
    
    # Clear cache to ensure any stats derived from settings are refreshed
    clear_user_caches(user_id)
    
    return {"status": "success", "message": "Settings reset to defaults"}


@router.post("/clear-data")
@maybe_limit(app_settings.RATE_LIMIT_API)
async def clear_data(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Delete all enrollment runs and course data for the user, and reset lifetime stats."""
    # Check for active run
    active_run = db.query(EnrollmentRun).filter(
        EnrollmentRun.user_id == user_id,
        EnrollmentRun.status.in_(["pending", "scraping", "enrolling"])
    ).first()
    
    if active_run:
        raise HTTPException(status_code=400, detail="Cannot clear data while an enrollment run is active")

    try:
        # 1. Delete all enrolled courses associated with the user's runs
        # Use a join to find courses belonging to the user
        course_ids_to_delete = db.query(EnrolledCourse.id).join(EnrollmentRun).filter(EnrollmentRun.user_id == user_id).all()
        course_ids = [c[0] for c in course_ids_to_delete]
        
        if course_ids:
            db.execute(delete(EnrolledCourse).where(EnrolledCourse.id.in_(course_ids)))

        # 2. Delete all enrollment runs
        db.execute(delete(EnrollmentRun).where(EnrollmentRun.user_id == user_id))

        # 3. Reset user lifetime stats
        db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                total_enrolled=0,
                total_already_enrolled=0,
                total_expired=0,
                total_excluded=0,
                total_amount_saved=0.0
            )
        )

        db.commit()
        logger.info(f"All data cleared and stats reset for user {user_id}")
        
        # Clear cache to ensure UI stats are refreshed
        clear_user_caches(user_id)
        
        return {"status": "success", "message": "All enrollment history and statistics have been cleared"}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to clear data for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear database records")
