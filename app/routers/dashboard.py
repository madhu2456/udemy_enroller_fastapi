"""Dashboard router - serves HTML pages and aggregated stats."""

import logging
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.database import get_db, EnrollmentRun, EnrolledCourse

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
    request: Request,
    db: Session = Depends(get_db),
):
    """Get aggregated dashboard statistics."""
    user_id = getattr(request.app.state, "udemy_clients", {}).get("default_user_id")
    if not user_id:
        return {
            "total_runs": 0,
            "total_enrolled": 0,
            "total_amount_saved": 0.0,
            "currency": "usd",
            "total_already_enrolled": 0,
            "total_expired": 0,
            "total_excluded": 0,
        }

    stats = db.query(
        func.count(EnrollmentRun.id).label("total_runs"),
        func.coalesce(func.sum(EnrollmentRun.successfully_enrolled), 0).label("total_enrolled"),
        func.coalesce(func.sum(EnrollmentRun.amount_saved), 0.0).label("total_amount_saved"),
        func.coalesce(func.sum(EnrollmentRun.already_enrolled), 0).label("total_already_enrolled"),
        func.coalesce(func.sum(EnrollmentRun.expired), 0).label("total_expired"),
        func.coalesce(func.sum(EnrollmentRun.excluded), 0).label("total_excluded"),
    ).filter(EnrollmentRun.user_id == user_id).first()

    latest_run = (
        db.query(EnrollmentRun)
        .filter(EnrollmentRun.user_id == user_id)
        .order_by(EnrollmentRun.started_at.desc())
        .first()
    )

    return {
        "total_runs": stats.total_runs or 0,
        "total_enrolled": stats.total_enrolled or 0,
        "total_amount_saved": float(stats.total_amount_saved or 0),
        "currency": latest_run.currency if latest_run else "usd",
        "total_already_enrolled": stats.total_already_enrolled or 0,
        "total_expired": stats.total_expired or 0,
        "total_excluded": stats.total_excluded or 0,
    }
