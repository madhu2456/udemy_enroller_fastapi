"""Scheduler API router for status monitoring, frequency updates, and manual triggers."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy.orm import Session

from app.core.cache import clear_user_caches
from app.deps import get_current_user_id
from app.models.database import EnrollmentRun, User, UserSettings, get_db
from app.routers.settings import get_or_create_settings
from app.schemas.schemas import (
    SchedulerStatusResponse,
    SchedulerTriggerResponse,
    SchedulerUpdateRequest,
)
from app.security import verify_csrf_token
from app.services.scheduler import compute_scheduler_timings, trigger_run_for_user

router = APIRouter(prefix="/api/scheduler", tags=["Scheduler"])

PRESET_MAP: dict[str, int] = {
    "1h": 1,
    "2h": 2,
    "4h": 4,
    "6h": 6,
    "12h": 12,
    "24h": 24,
    "disabled": 0,
}

CRON_MAP: dict[int, str] = {
    1: "0 * * * *",
    2: "0 */2 * * *",
    4: "0 */4 * * *",
    6: "0 */6 * * *",
    12: "0 */12 * * *",
    24: "0 0 * * *",
}


def _get_scheduler_meta(interval_hours: int) -> tuple[Optional[str], str]:
    if interval_hours <= 0:
        return None, "Disabled (Manual runs only)"
    cron = CRON_MAP.get(interval_hours, f"0 */{interval_hours} * * *")
    if interval_hours == 1:
        return cron, "Every hour"
    elif interval_hours == 24:
        return cron, "Every 24 hours (Daily at midnight UTC)"
    return cron, f"Every {interval_hours} hours"


def _build_status_response(
    user: User, settings: Optional[UserSettings], db: Session
) -> SchedulerStatusResponse:
    interval_hours = settings.schedule_interval_hours if settings else 0
    last_scheduled = settings.last_scheduled_run if settings else None

    active_run = (
        db.query(EnrollmentRun)
        .filter(
            EnrollmentRun.user_id == user.id,
            EnrollmentRun.status.in_(["pending", "scraping", "enrolling"]),
        )
        .first()
    )
    is_run_in_progress = active_run is not None
    active_run_id = active_run.id if active_run else None

    has_udemy_auth = bool(user.udemy_cookies and user.cookies_salt)

    from app.services.scraper import SCRAPER_REGISTRY
    active_scrapers_count = len(SCRAPER_REGISTRY)

    is_enabled, next_run_at, next_run_in_seconds = compute_scheduler_timings(
        interval_hours, last_scheduled
    )
    cron_expr, human_desc = _get_scheduler_meta(interval_hours)

    return SchedulerStatusResponse(
        is_enabled=is_enabled,
        schedule_interval_hours=interval_hours,
        cron_expression=cron_expr,
        human_description=human_desc,
        last_scheduled_run=last_scheduled,
        next_run_at=next_run_at,
        next_run_in_seconds=next_run_in_seconds,
        is_run_in_progress=is_run_in_progress,
        active_run_id=active_run_id,
        has_udemy_auth=has_udemy_auth,
        active_scrapers_count=active_scrapers_count,
    )


@router.get("/status", response_model=SchedulerStatusResponse)
async def get_scheduler_status(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Retrieve current scheduler telemetry, countdown, and active state."""
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _build_status_response(user, user.settings, db)


@router.post("/update", response_model=SchedulerStatusResponse)
async def update_scheduler(
    body: SchedulerUpdateRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    _csrf: None = Depends(verify_csrf_token),
):
    """Update scheduler frequency interval or preset."""
    # Guardrail 3: Return 400 Bad Request if both fields are null
    if body.schedule_interval_hours is None and body.cron_preset is None:
        raise HTTPException(
            status_code=400,
            detail="Either schedule_interval_hours or cron_preset must be provided",
        )

    if body.schedule_interval_hours is not None:
        interval_hours = body.schedule_interval_hours
    else:
        preset_key = body.cron_preset.strip().lower()
        if preset_key not in PRESET_MAP:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid preset: {body.cron_preset}. Supported presets: {list(PRESET_MAP.keys())}",
            )
        interval_hours = PRESET_MAP[preset_key]

    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    settings = get_or_create_settings(db, user_id)
    settings.schedule_interval_hours = interval_hours
    db.commit()
    db.refresh(settings)

    clear_user_caches(user_id)
    logger.info(f"Updated scheduler interval to {interval_hours}h for user {user_id}")

    return _build_status_response(user, settings, db)


@router.post("/trigger", response_model=SchedulerTriggerResponse)
async def trigger_scheduler_run(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    _csrf: None = Depends(verify_csrf_token),
):
    """Manually trigger an immediate scheduled enrollment run."""
    run_id = await trigger_run_for_user(user_id, db)
    clear_user_caches(user_id)
    return SchedulerTriggerResponse(
        success=True,
        message=f"Scheduled run #{run_id} launched successfully",
        run_id=run_id,
    )
