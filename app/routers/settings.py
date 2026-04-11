"""Settings router for managing user enrollment preferences."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from loguru import logger

from app.models.database import get_db, UserSettings
from app.deps import get_current_user_id
from app.rate_limit_config import maybe_limit
from app.schemas.schemas import SettingsUpdate, SettingsResponse
from app.security import validate_proxy_url
from config.settings import get_settings as get_app_settings

router = APIRouter(prefix="/api/settings", tags=["Settings"])
app_settings = get_app_settings()


@router.get("/", response_model=SettingsResponse)
async def get_settings(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Get current user settings."""
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

    return SettingsResponse(
        sites=settings.sites or {},
        languages=settings.languages or {},
        categories=settings.categories or {},
        instructor_exclude=settings.instructor_exclude or [],
        title_exclude=settings.title_exclude or [],
        min_rating=settings.min_rating or 0.0,
        course_update_threshold_months=settings.course_update_threshold_months or 24,
        save_txt=settings.save_txt or False,
        discounted_only=settings.discounted_only or False,
        proxy_url=settings.proxy_url,
        enable_headless=settings.enable_headless or False,
        schedule_interval=settings.schedule_interval or 0,
    )


@router.put("/")
@maybe_limit(app_settings.RATE_LIMIT_API)
async def update_settings(
    request: Request,
    settings_update: SettingsUpdate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Update user settings."""
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

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
    return {"status": "success", "message": "Settings updated"}


@router.post("/reset")
@maybe_limit(app_settings.RATE_LIMIT_API)
async def reset_settings(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Reset settings to defaults."""
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

    # Reset to defaults
    defaults = UserSettings(user_id=user_id)
    settings.sites = defaults.sites
    settings.languages = defaults.languages
    settings.categories = defaults.categories
    settings.instructor_exclude = []
    settings.title_exclude = []
    settings.min_rating = 0.0
    settings.course_update_threshold_months = 24
    settings.save_txt = False
    settings.discounted_only = False
    settings.proxy_url = None
    settings.enable_headless = False
    settings.schedule_interval = 0

    db.commit()
    logger.info(f"Settings reset to defaults for user {user_id}")
    return {"status": "success", "message": "Settings reset to defaults"}
