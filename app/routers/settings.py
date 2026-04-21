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

router = APIRouter(prefix="/api/settings", tags=["Settings"], redirect_slashes=True)
app_settings = get_app_settings()


@router.get("/", response_model=SettingsResponse)
async def get_settings(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Get current user settings with guaranteed defaults."""
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

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
    )


from app.core.cache import clear_user_caches

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
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

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

    db.commit()
    logger.info(f"Settings reset to defaults for user {user_id}")
    
    # Clear cache to ensure any stats derived from settings are refreshed
    clear_user_caches(user_id)
    
    return {"status": "success", "message": "Settings reset to defaults"}

