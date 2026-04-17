"""Enrollment router - start runs, track progress, view history."""

import csv
import io
import json
import logging
import asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.models.database import get_db, UserSettings, EnrollmentRun, EnrolledCourse
from app.deps import get_current_user_id, get_udemy_client
from app.rate_limit_config import maybe_limit
from app.schemas.schemas import EnrollmentStatus, CourseInfo, RunDetail
from app.services.enrollment_manager import EnrollmentManager
from config.settings import get_settings as get_app_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/enrollment", tags=["Enrollment"])
app_settings = get_app_settings()


@router.post("/start")
@maybe_limit(app_settings.RATE_LIMIT_API)
async def start_enrollment(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    client=Depends(get_udemy_client),
):
    """Start a new enrollment run."""
    active = EnrollmentManager.get_active_run(db, user_id)
    if active:
        raise HTTPException(status_code=409, detail="An enrollment run is already active")

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
        "proxy_url": user_settings.proxy_url,
        "enable_headless": user_settings.enable_headless or False,
    }

    enabled_sites = [k for k, v in settings_dict["sites"].items() if v]
    enabled_langs = [k for k, v in settings_dict["languages"].items() if v]
    enabled_cats = [k for k, v in settings_dict["categories"].items() if v]
    if not all([enabled_sites, enabled_langs, enabled_cats]):
        raise HTTPException(
            status_code=400,
            detail="You must have at least one site, language, and category enabled.",
        )

    # Sync client proxy with current user settings
    client.set_proxy(settings_dict["proxy_url"])

    manager = EnrollmentManager(client, settings_dict, db, user_id)
    run_id = await manager.start()
    
    # Invalidate cache so the new run appears in history immediately
    clear_user_caches(user_id)

    # Start the actual scraping and enrollment pipeline in the background
    task = asyncio.create_task(manager._run_pipeline())

    EnrollmentManager.active_tasks[run_id] = task

    return {"success": True, "run_id": run_id, "message": "Enrollment started"}


@router.post("/stop")
async def stop_enrollment(db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    """Stop the active enrollment run."""
    active = EnrollmentManager.get_active_run(db, user_id)
    if not active:
        return {"success": False, "message": "No active enrollment run to stop"}

    task = EnrollmentManager.active_tasks.get(active.id)
    if task:
        task.cancel()
        return {"success": True, "message": "Enrollment stopping..."}
    else:
        # Fallback if task is not in memory
        active.status = "cancelled"
        active.error_message = "Cancelled by user"
        active.completed_at = EnrollmentManager._utcnow_naive()
        db.commit()

        # Invalidate cache
        clear_user_caches(user_id)

        return {"success": True, "message": "Enrollment run marked as cancelled"}



@router.get("/progress")
async def get_progress(db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    """Get live progress of the active enrollment run."""
    active = EnrollmentManager.get_active_run(db, user_id)
    if not active:
        return {"active": False, "message": "No active enrollment run"}
    return {"active": True, **EnrollmentManager.get_progress_from_run(active)}


@router.get("/progress/stream")
async def stream_progress(request: Request, db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    """Server-Sent Events stream for real-time progress updates."""
    async def event_generator():
        from app.core.constants import shutdown_event
        while not shutdown_event.is_set():
            if await request.is_disconnected():
                break
                
            # Need to get a fresh session per loop since this is async streaming
            from app.models.database import SessionLocal
            with SessionLocal() as stream_db:
                active = EnrollmentManager.get_active_run(stream_db, user_id)
                if not active:
                    yield f"data: {json.dumps({'active': False, 'status': 'completed'})}\n\n"
                    break
                progress = EnrollmentManager.get_progress_from_run(active)
                yield f"data: {json.dumps({'active': True, **progress})}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


from app.core.cache import _history_cache, get_cached_or_compute, clear_user_caches

@router.get("/history", response_model=list[EnrollmentStatus])
async def get_enrollment_history(
    limit: int = 20,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Get enrollment run history for the current user only."""
    def compute_history():
        runs = (
            db.query(EnrollmentRun)
            .filter(EnrollmentRun.user_id == user_id)
            .filter(EnrollmentRun.status != "deleted")
            .order_by(EnrollmentRun.started_at.desc())
            .limit(limit)
            .all()
        )

        return [
            EnrollmentStatus(
                run_id=run.id,
                status=run.status,
                total_courses_found=run.total_courses_found,
                total_processed=run.total_processed,
                successfully_enrolled=run.successfully_enrolled,
                already_enrolled=run.already_enrolled,
                expired=run.expired,
                excluded=run.excluded,
                amount_saved=float(run.amount_saved or 0),
                currency=run.currency,
                started_at=run.started_at,
                completed_at=run.completed_at,
                error_message=run.error_message,
            )
            for run in runs
        ]

    return get_cached_or_compute(_history_cache, f"{user_id}_{limit}", compute_history, ttl_seconds=10)


from app.schemas.schemas import EnrollmentStatus, CourseInfo, RunDetail

@router.get("/run/{run_id}", response_model=RunDetail)
async def get_run_details(
    run_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Get details for a specific enrollment run (only if it belongs to the current user)."""
    run = db.query(EnrollmentRun).filter(
        EnrollmentRun.id == run_id,
        EnrollmentRun.user_id == user_id,
        EnrollmentRun.status != "deleted"
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    courses_models = db.query(EnrolledCourse).filter(
        EnrolledCourse.enrollment_run_id == run_id
    ).all()

    return RunDetail(
        run=EnrollmentStatus(
            run_id=run.id,
            status=run.status,
            total_courses_found=run.total_courses_found,
            total_processed=run.total_processed,
            successfully_enrolled=run.successfully_enrolled,
            already_enrolled=run.already_enrolled,
            expired=run.expired,
            excluded=run.excluded,
            amount_saved=float(run.amount_saved or 0),
            currency=run.currency,
            started_at=run.started_at,
            completed_at=run.completed_at,
            error_message=run.error_message,
        ),
        courses=[CourseInfo.model_validate(c) for c in courses_models]
    )


@router.delete("/run/{run_id}")
async def delete_run(
    run_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Soft delete a specific enrollment run while keeping its course records for the cache."""
    run = db.query(EnrollmentRun).filter(
        EnrollmentRun.id == run_id,
        EnrollmentRun.user_id == user_id,
    ).first()

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status in ["pending", "scraping", "enrolling"]:
        raise HTTPException(status_code=400, detail="Cannot delete an active run")

    run.status = "deleted"
    run.progress_data = {}  # Clear large JSON data to save space
    db.commit()

    # Invalidate cache for UI consistency
    clear_user_caches(user_id)

    return {"success": True, "message": "Run deleted successfully"}


@router.get("/run/{run_id}/export")
async def export_run_csv(
    run_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Export run results as CSV."""
    run = db.query(EnrollmentRun).filter(
        EnrollmentRun.id == run_id,
        EnrollmentRun.user_id == user_id,
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    courses = db.query(EnrolledCourse).filter(
        EnrolledCourse.enrollment_run_id == run_id
    ).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Title", "URL", "Course ID", "Coupon Code", "Price", 
        "Category", "Language", "Rating", "Site Source", "Status", "Error", "Enrolled At"
    ])

    for c in courses:
        writer.writerow([
            c.title, c.url, c.course_id, c.coupon_code, c.price,
            c.category, c.language, c.rating, c.site_source, c.status, c.error_message, c.enrolled_at
        ])

    csv_content = output.getvalue()
    from fastapi.responses import Response
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=run_{run_id}_export.csv"}
    )
