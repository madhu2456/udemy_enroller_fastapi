"""Settings router for managing user enrollment preferences."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.models.database import get_db, UserSettings
from app.deps import get_current_user_id
from app.schemas.schemas import SettingsUpdate, SettingsResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["Settings"])


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
    )


@router.put("/")
async def update_settings(
    settings_update: SettingsUpdate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Update user settings."""
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

    update_data = settings_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(settings, field, value)

    db.commit()
    return {"success": True, "message": "Settings updated"}


@router.post("/reset")
async def reset_settings(
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

    db.commit()
    return {"success": True, "message": "Settings reset to defaults"}
