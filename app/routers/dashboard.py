"""Dashboard router - serves HTML pages and aggregated stats."""

import logging
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.database import get_db, User, EnrollmentRun, EnrolledCourse
from app.deps import get_current_user_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Dashboard"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page."""
    return templates.TemplateResponse("pages/dashboard.html", {"request": request})


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page."""
    return templates.TemplateResponse("pages/login.html", {"request": request})


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page."""
    return templates.TemplateResponse("pages/settings.html", {"request": request})


@router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    """Enrollment history page."""
    return templates.TemplateResponse("pages/history.html", {"request": request})


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
    user = db.get(User, user_id)
    if not user:
        return {"total_runs": 0, "total_enrolled": 0, "total_amount_saved": 0.0,
                "currency": "usd", "total_already_enrolled": 0,
                "total_expired": 0, "total_excluded": 0}

    total_runs = db.query(func.count(EnrollmentRun.id)).filter(
        EnrollmentRun.user_id == user_id
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
