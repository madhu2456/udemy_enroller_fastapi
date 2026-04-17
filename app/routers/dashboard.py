"""Dashboard router - serves HTML pages and aggregated stats."""

import logging
import asyncio
import os
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.database import (
    get_db,
    User,
    UserSession,
    EnrollmentRun,
    EnrolledCourse,
    _utcnow_naive,
)
from app.deps import get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Dashboard"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page."""
    return templates.TemplateResponse("pages/dashboard.html", {"request": request})


@router.get("/", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    """Login page.

    Redirect authenticated users server-side to avoid an extra client-side
    auth check request on initial page load.
    """
    token = request.cookies.get("session_id")
    if token:
        session = db.query(UserSession).filter(UserSession.token == token).first()
        if session:
            if session.expires_at and session.expires_at < _utcnow_naive():
                db.delete(session)
                db.commit()
            else:
                return RedirectResponse(url="/dashboard", status_code=303)

    return templates.TemplateResponse("pages/login.html", {"request": request})


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page."""
    return templates.TemplateResponse("pages/settings.html", {"request": request})


@router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    """Enrollment history page."""
    return templates.TemplateResponse("pages/history.html", {"request": request})


from app.core.cache import _analytics_cache, _stats_cache, get_cached_or_compute

@router.get("/api/dashboard/stats")
async def dashboard_stats(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Get dashboard statistics for the current user.

    Lifetime totals come from the user row (incremented atomically after every
    course, so they survive disconnects and incomplete runs).
    Total run count still comes from enrollment_runs.
    """
    def compute_stats():
        user = db.get(User, user_id)
        if not user:
            return {"total_runs": 0, "total_enrolled": 0, "total_amount_saved": 0.0,
                    "currency": "usd", "total_already_enrolled": 0,
                    "total_expired": 0, "total_excluded": 0}

        total_runs = db.query(func.count(EnrollmentRun.id)).filter(
            EnrollmentRun.user_id == user_id,
            EnrollmentRun.status != "deleted"
        ).scalar() or 0

        return {
            "total_runs": total_runs,
            "total_enrolled": user.total_enrolled or 0,
            "total_amount_saved": float(user.total_amount_saved or 0),
            "currency": user.currency or "usd",
            "total_already_enrolled": user.total_already_enrolled or 0,
            "total_expired": user.total_expired or 0,
            "total_excluded": user.total_excluded or 0,
        }
        
    return get_cached_or_compute(_stats_cache, user_id, compute_stats, ttl_seconds=300)


@router.get("/api/dashboard/analytics")
async def dashboard_analytics(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Get historical analytics for the current user (savings per day for last 30 days)."""
    def compute_analytics():
        # Aggregate successful enrollments by date
        stats = (
            db.query(
                func.date(EnrolledCourse.enrolled_at).label("date"),
                func.count(EnrolledCourse.id).label("count"),
                func.sum(EnrolledCourse.price).label("savings")
            )
            .join(EnrollmentRun)
            .filter(
                EnrollmentRun.user_id == user_id,
                EnrolledCourse.status == "enrolled"
            )
            .group_by(func.date(EnrolledCourse.enrolled_at))
            .order_by(func.date(EnrolledCourse.enrolled_at))
            .all()
        )

        return [
            {
                "date": str(s.date),
                "count": s.count,
                "savings": float(s.savings or 0)
            }
            for s in stats
        ]
        
    return get_cached_or_compute(_analytics_cache, user_id, compute_analytics, ttl_seconds=300)



@router.get("/api/dashboard/logs/stream")
async def stream_logs(request: Request):
    """Stream application logs via SSE."""
    async def log_generator():
        log_file = "logs/app.log"
        if not os.path.exists(log_file):
            yield "data: Log file not found\n\n"
            return

        # Start by tailing the file, only last few lines then live
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            # Get last 20 lines
            f.seek(0, os.SEEK_END)
            end_pos = f.tell()
            if end_pos > 0:
                f.seek(max(0, end_pos - 4000))  # approx 20-40 lines
                if f.tell() > 0:
                    # Discard the first partial line since seek might land in the middle
                    f.readline()
                
            lines = f.readlines()
            for line in lines[-20:]:
                yield f"data: {line.strip()}\n\n"

            # Live tail
            while True:
                if await request.is_disconnected():
                    break
                line = f.readline()
                if line:
                    if line.strip():
                        yield f"data: {line.strip()}\n\n"
                else:
                    await asyncio.sleep(0.5)

    return StreamingResponse(log_generator(), media_type="text/event-stream")
