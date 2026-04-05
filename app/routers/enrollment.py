"""Enrollment router - start runs, track progress, view history."""

import json
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.models.database import get_db, User, UserSettings, EnrollmentRun, EnrolledCourse
from app.schemas.schemas import EnrollmentStatus, CourseInfo
from app.services.enrollment_manager import EnrollmentManager
from app.services.udemy_client import UdemyClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/enrollment", tags=["Enrollment"])


def get_user_id(request: Request, db: Session = Depends(get_db)) -> int:
    # Primary: in-memory state (set at login, present while server is running)
    user_id = getattr(request.app.state, "udemy_clients", {}).get("default_user_id")
    if user_id:
        return user_id

    # Fallback: persistent cookie set at login time (survives server restarts)
    cookie_user_id = request.cookies.get("user_id")
    if cookie_user_id:
        try:
            uid = int(cookie_user_id)
            user = db.query(User).filter(User.id == uid).first()
            if user:
                # Restore in-memory state so subsequent calls skip the DB lookup
                if not hasattr(request.app.state, "udemy_clients"):
                    request.app.state.udemy_clients = {}
                request.app.state.udemy_clients["default_user_id"] = uid
                return uid
        except (ValueError, Exception):
            pass

    raise HTTPException(status_code=401, detail="Not authenticated")


def get_udemy_client(request: Request) -> UdemyClient:
    session_id = request.cookies.get("session_id", "default")
    clients = getattr(request.app.state, "udemy_clients", {})
    client = clients.get(session_id)
    if not client or not client.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return client


@router.post("/start")
async def start_enrollment(
    request: Request,
    db: Session = Depends(get_db),
):
    """Start a new enrollment run."""
    user_id = get_user_id(request)
    client = get_udemy_client(request)

    # Check for active run
    active = EnrollmentManager.get_active_run(user_id)
    if active:
        raise HTTPException(status_code=409, detail="An enrollment run is already active")

    # Load settings
    user_settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if not user_settings:
        raise HTTPException(status_code=404, detail="Settings not found. Configure settings first.")

    settings_dict = {
        "sites": user_settings.sites or {},
        "languages": user_settings.languages or {},
        "categories": user_settings.categories or {},
        "instructor_exclude": user_settings.instructor_exclude or [],
        "title_exclude": user_settings.title_exclude or [],
        "min_rating": user_settings.min_rating or 0.0,
        "course_update_threshold_months": user_settings.course_update_threshold_months or 24,
        "save_txt": user_settings.save_txt or False,
        "discounted_only": user_settings.discounted_only or False,
    }

    # Validate settings
    enabled_sites = [k for k, v in settings_dict["sites"].items() if v]
    enabled_langs = [k for k, v in settings_dict["languages"].items() if v]
    enabled_cats = [k for k, v in settings_dict["categories"].items() if v]
    if not all([enabled_sites, enabled_langs, enabled_cats]):
        raise HTTPException(
            status_code=400,
            detail="You must have at least one site, language, and category enabled.",
        )

    manager = EnrollmentManager(client, settings_dict, db, user_id)
    run_id = manager.start()

    return {"success": True, "run_id": run_id, "message": "Enrollment started"}


@router.get("/progress")
async def get_progress(request: Request):
    """Get live progress of the active enrollment run."""
    user_id = get_user_id(request)
    active = EnrollmentManager.get_active_run(user_id)
    if not active:
        return {"active": False, "message": "No active enrollment run"}
    return {"active": True, **active.get_progress()}


@router.get("/progress/stream")
async def stream_progress(request: Request):
    """Server-Sent Events stream for real-time progress updates."""
    user_id = get_user_id(request)

    async def event_generator():
        import asyncio
        while True:
            active = EnrollmentManager.get_active_run(user_id)
            if not active:
                yield f"data: {json.dumps({'active': False, 'status': 'completed'})}\n\n"
                break
            progress = active.get_progress()
            yield f"data: {json.dumps({'active': True, **progress})}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/history", response_model=list[EnrollmentStatus])
async def get_enrollment_history(
    request: Request,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """Get enrollment run history."""
    user_id = get_user_id(request)
    runs = (
        db.query(EnrollmentRun)
        .filter(EnrollmentRun.user_id == user_id)
        .order_by(EnrollmentRun.started_at.desc())
        .limit(limit)
        .all()
    )
    return [
        EnrollmentStatus(
            run_id=r.id,
            status=r.status,
            total_courses_found=r.total_courses_found,
            total_processed=r.total_processed,
            successfully_enrolled=r.successfully_enrolled,
            already_enrolled=r.already_enrolled,
            expired=r.expired,
            excluded=r.excluded,
            amount_saved=r.amount_saved,
            currency=r.currency,
            started_at=r.started_at,
            completed_at=r.completed_at,
            error_message=r.error_message,
        )
        for r in runs
    ]


@router.get("/run/{run_id}")
async def get_run_details(
    run_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Get details for a specific enrollment run."""
    user_id = get_user_id(request)
    run = db.query(EnrollmentRun).filter(
        EnrollmentRun.id == run_id,
        EnrollmentRun.user_id == user_id,
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    courses = db.query(EnrolledCourse).filter(
        EnrolledCourse.enrollment_run_id == run_id
    ).all()

    return {
        "run": EnrollmentStatus(
            run_id=run.id,
            status=run.status,
            total_courses_found=run.total_courses_found,
            total_processed=run.total_processed,
            successfully_enrolled=run.successfully_enrolled,
            already_enrolled=run.already_enrolled,
            expired=run.expired,
            excluded=run.excluded,
            amount_saved=run.amount_saved,
            currency=run.currency,
            started_at=run.started_at,
            completed_at=run.completed_at,
            error_message=run.error_message,
        ),
        "courses": [
            CourseInfo(
                title=c.title,
                url=c.url,
                slug=c.slug,
                course_id=c.course_id,
                coupon_code=c.coupon_code,
                price=c.price,
                category=c.category,
                language=c.language,
                rating=c.rating,
                site_source=c.site_source,
                status=c.status,
                error_message=c.error_message,
                enrolled_at=c.enrolled_at,
            )
            for c in courses
        ],
    }
