"""Settings router for managing user enrollment preferences."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from loguru import logger

from app.models.database import (
    get_db,
    UserSettings,
    User,
    UserSession,
    EnrollmentRun,
    EnrolledCourse,
)
from app.deps import get_current_user_id
from app.schemas.schemas import SettingsUpdate, SettingsResponse
from app.security import (
    RateLimiter,
    _client_key,
    analytics_rate_limiter,
    auth_status_rate_limiter,
    csp_report_rate_limiter,
    csrf_cookie_names,
    login_rate_limiter,
    public_coupons_api_limiter,
    verify_csrf_token,
)
from app.security import validate_proxy_url
from config.settings import get_settings as get_app_settings
from app.core.cache import clear_user_caches
from sqlalchemy import delete, select, update

router = APIRouter(prefix="/api/settings", tags=["Settings"])
app_settings = get_app_settings()

# D1 DSR: data-subject export is rate-limited (metadata can be large and
# repeated pulls hammer the DB).
export_rate_limiter = RateLimiter(max_requests=5, window_seconds=60)


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
        if not isinstance(user_val, dict):
            return defaults

        # Merge logic:
        # 1. Take all keys from defaults (ensures new scrapers are added)
        # 2. Use user's value if it exists for a key
        # 3. Use default value if key is new
        merged = defaults.copy()
        for k, v in user_val.items():
            if k in merged:
                merged[k] = bool(v)

        # If the user has stale keys that are NO LONGER in defaults (like Discudemy),
        # they will be naturally excluded because we started with a copy of defaults.
        return merged

    return SettingsResponse(
        sites=safe_merge(settings.sites, UserSettings.default_sites),
        languages=safe_merge(settings.languages, UserSettings.default_languages),
        categories=safe_merge(settings.categories, UserSettings.default_categories),
        instructor_exclude=settings.instructor_exclude or [],
        title_exclude=settings.title_exclude or [],
        min_rating=float(settings.min_rating or 0.0),
        course_update_threshold_months=int(
            settings.course_update_threshold_months or 24
        ),
        save_txt=bool(settings.save_txt),
        discounted_only=bool(settings.discounted_only),
        proxy_url=settings.proxy_url,
    )


@router.put("/", include_in_schema=True)
async def update_settings(
    update: SettingsUpdate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    _csrf: None = Depends(verify_csrf_token),
):
    """Update user settings."""
    settings = get_or_create_settings(db, user_id)

    update_data = update.model_dump(exclude_unset=True)

    # Validate proxy URL if provided
    if "proxy_url" in update_data and update_data["proxy_url"]:
        if not validate_proxy_url(update_data["proxy_url"]):
            logger.warning(
                f"Invalid proxy URL provided by user {user_id}: {update_data['proxy_url']}"
            )
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
async def reset_settings(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    _csrf: None = Depends(verify_csrf_token),
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

    db.commit()
    logger.info(f"Settings reset to defaults for user {user_id}")

    # Clear cache to ensure any stats derived from settings are refreshed
    clear_user_caches(user_id)

    return {"status": "success", "message": "Settings reset to defaults"}


@router.post("/clear-data")
async def clear_data(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    _csrf: None = Depends(verify_csrf_token),
):
    """Delete enrollment history/stats, app sessions, and stored Udemy cookies.

    Keeps the local user row and preference settings so the account can re-connect.
    """
    # Check for active run
    active_run = (
        db.query(EnrollmentRun)
        .filter(
            EnrollmentRun.user_id == user_id,
            EnrollmentRun.status.in_(["pending", "scraping", "enrolling"]),
        )
        .first()
    )

    if active_run:
        raise HTTPException(
            status_code=400,
            detail="Cannot clear data while an enrollment run is active",
        )

    try:
        # 1. Delete all enrolled courses associated with the user's runs
        # Correlated delete avoids race condition between SELECT and DELETE
        from sqlalchemy import select

        subq = select(EnrollmentRun.id).where(EnrollmentRun.user_id == user_id).scalar_subquery()
        db.execute(delete(EnrolledCourse).where(EnrolledCourse.enrollment_run_id.in_(subq)))

        # 2. Delete all enrollment runs
        db.execute(delete(EnrollmentRun).where(EnrollmentRun.user_id == user_id))

        # 3. Collect session tokens before deleting sessions (for cache cleanup)
        session_tokens = [
            row[0]
            for row in db.query(UserSession.token)
            .filter(UserSession.user_id == user_id)
            .all()
        ]

        # 4. Delete all app sessions for this user
        db.execute(delete(UserSession).where(UserSession.user_id == user_id))

        # 5. Reset lifetime stats and wipe encrypted Udemy cookies
        db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                total_enrolled=0,
                total_already_enrolled=0,
                total_expired=0,
                total_excluded=0,
                total_amount_saved=0.0,
                udemy_cookies=None,
                cookies_salt=None,
            )
        )

        db.commit()
        logger.info(
            f"Cleared history, stats, sessions, and Udemy cookies for user {user_id}"
        )

        # Close in-memory Udemy clients for this user's sessions
        cache = getattr(request.app.state, "session_cache", None)
        for tok in session_tokens:
            client = None
            if cache is not None:
                client = cache.pop(tok, None)
            if client is None and hasattr(request.app.state, "udemy_clients"):
                clients = request.app.state.udemy_clients
                if clients is not cache and clients is not None and hasattr(clients, "pop"):
                    client = clients.pop(tok, None)
            if client is not None:
                try:
                    close_res = client.close()
                    if asyncio.iscoroutine(close_res):
                        await close_res
                except Exception as e:
                    logger.error(f"Error closing client during clear-data: {e}")

        # Clear dashboard caches
        clear_user_caches(user_id)

        response = JSONResponse(
            content={
                "status": "success",
                "message": (
                    "Enrollment history, statistics, sessions, and stored Udemy "
                    "cookies were cleared. Connect again to use enrollment."
                ),
            }
        )
        # Force re-auth in the browser. F228: delete the session cookie and
        # BOTH possible CSRF cookie names (__Host-csrf_token on secure
        # deployments, legacy plain csrf_token) with matching flags.
        response.delete_cookie(
            "session_id", path="/", domain=None,
            httponly=True, samesite="lax", secure=app_settings.COOKIE_SECURE,
        )
        for _csrf_name in csrf_cookie_names():
            response.delete_cookie(
                _csrf_name, path="/", domain=None,
                httponly=False, samesite="strict", secure=app_settings.COOKIE_SECURE,
            )
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        return response
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to clear data for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear database records")
@router.post("/export")
async def export_user_data(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    _csrf: None = Depends(verify_csrf_token),
):
    """Data-subject access export (D1 DSR): JSON metadata of the user's runs,
    courses, and sessions, plus a cookie-presence flag.

    NEVER returns raw cookie values or ciphertext — only presence. Rate-limited.
    """
    export_rate_limiter.raise_if_limited(_client_key(request))

    from datetime import UTC, datetime

    user = db.query(User).filter(User.id == user_id).first()
    settings_row = (
        db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    )

    runs = (
        db.query(EnrollmentRun)
        .filter(EnrollmentRun.user_id == user_id)
        .order_by(EnrollmentRun.started_at.desc())
        .all()
    )
    run_meta = [
        {
            "run_id": r.id,
            "status": r.status,
            "started_at": r.started_at.isoformat() + "Z" if r.started_at else None,
            "completed_at": r.completed_at.isoformat() + "Z" if r.completed_at else None,
            "total_courses_found": r.total_courses_found,
            "successfully_enrolled": r.successfully_enrolled,
            "already_enrolled": r.already_enrolled,
            "expired": r.expired,
            "excluded": r.excluded,
            "amount_saved": float(r.amount_saved or 0.0),
            "currency": r.currency or "usd",
        }
        for r in runs
    ]

    course_meta = []
    if runs:
        run_ids = [r.id for r in runs]
        stmt = (
            select(
                EnrolledCourse.title,
                EnrolledCourse.url,
                EnrolledCourse.coupon_code,
                EnrolledCourse.status,
                EnrolledCourse.enrolled_at,
            )
            .where(EnrolledCourse.enrollment_run_id.in_(run_ids))
            .order_by(EnrolledCourse.id.desc())
        )
        for title, url, coupon, status, enrolled_at in db.execute(stmt):
            course_meta.append(
                {
                    "title": title,
                    "url": url,
                    "coupon_code": coupon,
                    "status": status,
                    "enrolled_at": enrolled_at.isoformat() + "Z"
                    if enrolled_at
                    else None,
                }
            )

    sessions = (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id)
        .order_by(UserSession.created_at.desc())
        .all()
    )
    session_meta = [
        {
            "session_id": s.id,
            "created_at": s.created_at.isoformat() + "Z" if s.created_at else None,
            "expires_at": s.expires_at.isoformat() + "Z" if s.expires_at else None,
        }
        for s in sessions
    ]

    return {
        "status": "success",
        "exported_at": datetime.now(UTC).isoformat() + "Z",
        "user": {
            "email": user.email if user else None,
            "display_name": user.udemy_display_name if user else None,
            "currency": user.currency if user else None,
            "created_at": user.created_at.isoformat() + "Z"
            if user and user.created_at
            else None,
        },
        "stats": (
            {
                "total_enrolled": user.total_enrolled,
                "total_already_enrolled": user.total_already_enrolled,
                "total_expired": user.total_expired,
                "total_excluded": user.total_excluded,
                "total_amount_saved": float(user.total_amount_saved or 0.0),
            }
            if user
            else None
        ),
        "settings_present": settings_row is not None,
        # Presence flag only — raw cookie values are NEVER exported (D1).
        "cookie_presence": bool(user and user.udemy_cookies),
        "sessions": session_meta,
        "runs": run_meta,
        "courses": course_meta,
    }


@router.post("/delete-account")
async def delete_account(
    request: Request,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
    _csrf: None = Depends(verify_csrf_token),
):
    """Permanently delete the account and ALL user data (D1 DSR).

    Requires the confirm field to be exactly "DELETE". Wipes enrolled
    courses, enrollment runs, app sessions, user settings, lifetime stats,
    encrypted Udemy cookies (+ salt), and the User row itself — unlike
    clear-data, which keeps the account.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    if not isinstance(body, dict) or body.get("confirm") != "DELETE":
        raise HTTPException(
            status_code=400,
            detail="confirmation required: confirm must be exactly 'DELETE'",
        )

    try:
        # Wrap user and related rows in transactional row-level locking (D1 DSR)
        user = db.query(User).filter(User.id == user_id).with_for_update().first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Cancel active in-flight worker tasks before cascading deletion
        from app.services.enrollment_manager import EnrollmentManager

        user_runs = (
            db.query(EnrollmentRun)
            .filter(EnrollmentRun.user_id == user_id)
            .with_for_update()
            .all()
        )
        for run in user_runs:
            task = EnrollmentManager.active_tasks.get(run.id)
            if task:
                try:
                    task.cancel()
                    logger.info(
                        f"Cancelled active in-flight task {run.id} for user {user_id} during account deletion"
                    )
                except Exception as exc:
                    logger.warning(
                        f"Failed to cancel task {run.id} during account deletion: {exc}"
                    )

        # Collect session tokens before deleting (for in-memory client cleanup).
        session_tokens = [
            row[0]
            for row in db.query(UserSession.token)
            .filter(UserSession.user_id == user_id)
            .with_for_update()
            .all()
        ]

        # Courses -> runs -> sessions -> settings -> user row (cookies, salt,
        # and lifetime stats live on the User row and go with it).
        subq = (
            select(EnrollmentRun.id)
            .where(EnrollmentRun.user_id == user_id)
            .scalar_subquery()
        )
        db.execute(
            delete(EnrolledCourse).where(EnrolledCourse.enrollment_run_id.in_(subq))
        )
        db.execute(delete(EnrollmentRun).where(EnrollmentRun.user_id == user_id))
        db.execute(delete(UserSession).where(UserSession.user_id == user_id))
        db.execute(delete(UserSettings).where(UserSettings.user_id == user_id))
        db.execute(delete(User).where(User.id == user_id))
        db.commit()
        logger.info(f"Deleted account + all data for user {user_id}")

        # Close in-memory Udemy clients owned by the deleted sessions.
        cache = getattr(request.app.state, "session_cache", None)
        for tok in session_tokens:
            client = None
            if cache is not None:
                client = cache.pop(tok, None)
            if client is None and hasattr(request.app.state, "udemy_clients"):
                clients = request.app.state.udemy_clients
                if (
                    clients is not cache
                    and clients is not None
                    and hasattr(clients, "pop")
                ):
                    client = clients.pop(tok, None)
            if client is not None:
                try:
                    close_res = client.close()
                    if asyncio.iscoroutine(close_res):
                        await close_res
                except Exception as e:
                    logger.error(f"Error closing client during delete-account: {e}")

        # Invalidate dashboard caches for this user.
        clear_user_caches(user_id)

        # Best-effort: drop this client's rate-limit state (D1).
        client_key = _client_key(request)
        for limiter in (
            export_rate_limiter,
            login_rate_limiter,
            analytics_rate_limiter,
            csp_report_rate_limiter,
            public_coupons_api_limiter,
            auth_status_rate_limiter,
        ):
            try:
                limiter.clear_key(client_key)
            except Exception:
                pass

        response = JSONResponse(
            content={
                "status": "success",
                "message": (
                    "Account and all associated data were permanently deleted. "
                    "Note: SQLite backups (retention up to 14 days / 30 files) "
                    "may still contain this data until they age out."
                ),
            }
        )
        # Force re-auth in the browser (session row is already gone; clear
        # cookies so the client cannot keep sending a dead token).
        response.delete_cookie(
            "session_id", path="/", domain=None,
            httponly=True, samesite="lax", secure=app_settings.COOKIE_SECURE,
        )
        for _csrf_name in csrf_cookie_names():
            response.delete_cookie(
                _csrf_name, path="/", domain=None,
                httponly=False, samesite="strict", secure=app_settings.COOKIE_SECURE,
            )
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        return response
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete account for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete account")
