"""Unit and integration tests for Scheduler API, timing mathematics, and socket safety."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import secrets
import tempfile
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import (
    Base,
    EnrollmentRun,
    User,
    UserSession,
    UserSettings,
    get_db,
)
from app.schemas.schemas import SchedulerStatusResponse
from app.security import (
    encrypt_cookies_salted,
    generate_cookie_salt,
    generate_csrf_token,
)
from app.services.scheduler import (
    EnrollmentScheduler,
    _to_naive_utc,
    compute_scheduler_timings,
    trigger_run_for_user,
)
from main import app

# Isolated SQLite database for scheduler test suite
_temp_dir = tempfile.TemporaryDirectory(prefix="scheduler-api-tests-")
_test_db = Path(_temp_dir.name) / "test_scheduler.db"
test_engine = create_engine(
    f"sqlite:///{_test_db}", connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine
)

Base.metadata.create_all(bind=test_engine)


def _override_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _scheduler_test_env(monkeypatch):
    app.dependency_overrides[get_db] = _override_db
    monkeypatch.setattr("app.services.scheduler.SessionLocal", TestingSessionLocal)
    yield
    if app.dependency_overrides.get(get_db) is _override_db:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def auth_client():
    """Create test client with authenticated user and valid cookies."""
    db = TestingSessionLocal()
    salt = generate_cookie_salt()
    encrypted_cookies = encrypt_cookies_salted(
        {"access_token": "valid_token", "client_id": "client_123"}, salt
    )

    user = User(
        email=f"sched-user-{secrets.token_hex(4)}@example.com",
        password_hash="pw",
        udemy_display_name="Scheduler User",
        udemy_cookies=encrypted_cookies,
        cookies_salt=salt,
        currency="usd",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id

    settings = UserSettings(
        user_id=user_id,
        schedule_interval_hours=2,
        last_scheduled_run=None,
        sites={"Coursevania": True},
        languages=["en"],
        categories=["Development"],
    )
    db.add(settings)

    token = secrets.token_hex(32)
    session = UserSession(
        user_id=user_id,
        token=token,
    )
    db.add(session)
    db.commit()
    db.close()

    csrf = generate_csrf_token(token)
    client = TestClient(app)
    client.cookies.set("session_id", token)
    client.headers.update({"X-CSRF-Token": csrf})
    return client, user_id, csrf


# ── Unit Tests: Timing Mathematics & Timezone Normalization ───────────

def test_to_naive_utc():
    """Verify _to_naive_utc correctly normalizes both naive and aware datetimes."""
    assert _to_naive_utc(None) is None

    naive = datetime(2026, 10, 3, 12, 0, 0)
    assert _to_naive_utc(naive) == naive
    assert _to_naive_utc(naive).tzinfo is None

    aware_utc = datetime(2026, 10, 3, 12, 0, 0, tzinfo=timezone.utc)
    res_aware = _to_naive_utc(aware_utc)
    assert res_aware.tzinfo is None
    assert res_aware == naive

    # Arbitrary offset: UTC+5:30 at 17:30 is 12:00 UTC
    offset_ist = timezone(timedelta(hours=5, minutes=30))
    aware_ist = datetime(2026, 10, 3, 17, 30, 0, tzinfo=offset_ist)
    res_ist = _to_naive_utc(aware_ist)
    assert res_ist.tzinfo is None
    assert res_ist == naive


def test_compute_scheduler_timings_disabled():
    """Disabled intervals (<=0) return disabled state."""
    assert compute_scheduler_timings(0, None) == (False, None, None)
    assert compute_scheduler_timings(-2, datetime.now()) == (False, None, None)


def test_compute_scheduler_timings_never_run():
    """When schedule is enabled but never executed, next run is immediate."""
    now_fixed = datetime(2026, 10, 3, 12, 0, 0)
    is_enabled, next_run_at, remaining = compute_scheduler_timings(
        schedule_interval_hours=4,
        last_scheduled_run=None,
        now_utc=now_fixed,
    )
    assert is_enabled is True
    assert next_run_at == now_fixed
    assert remaining == 0


def test_compute_scheduler_timings_future_run():
    """When interval has not elapsed, computes remaining seconds accurately."""
    now_fixed = datetime(2026, 10, 3, 13, 0, 0)
    last_run = datetime(2026, 10, 3, 12, 0, 0)  # 1 hour elapsed, interval 4 hours
    is_enabled, next_run_at, remaining = compute_scheduler_timings(
        schedule_interval_hours=4,
        last_scheduled_run=last_run,
        now_utc=now_fixed,
    )
    assert is_enabled is True
    assert next_run_at == datetime(2026, 10, 3, 16, 0, 0)
    assert remaining == 3 * 3600  # 3 hours remaining


def test_compute_scheduler_timings_overdue_run_clamped():
    """Overdue run clamps remaining seconds to 0 (FM-04)."""
    now_fixed = datetime(2026, 10, 3, 16, 0, 0)
    last_run = datetime(2026, 10, 3, 12, 0, 0)  # 4 hours elapsed, interval 2 hours
    is_enabled, next_run_at, remaining = compute_scheduler_timings(
        schedule_interval_hours=2,
        last_scheduled_run=last_run,
        now_utc=now_fixed,
    )
    assert is_enabled is True
    assert next_run_at == datetime(2026, 10, 3, 14, 0, 0)
    assert remaining == 0  # Clamped to 0, not negative


def test_compute_scheduler_timings_aware_vs_naive_safety():
    """No TypeError raised when passing mixed aware and naive datetimes (FM-03)."""
    aware_now = datetime(2026, 10, 3, 15, 0, 0, tzinfo=timezone.utc)
    naive_last = datetime(2026, 10, 3, 12, 0, 0)
    is_enabled, next_run_at, remaining = compute_scheduler_timings(
        schedule_interval_hours=6,
        last_scheduled_run=naive_last,
        now_utc=aware_now,
    )
    assert is_enabled is True
    assert remaining == 3 * 3600


# ── Integration Tests: /api/scheduler/* Endpoints ─────────────────────

def test_scheduler_status_unauthenticated():
    """GET /api/scheduler/status requires authentication."""
    client = TestClient(app)
    resp = client.get("/api/scheduler/status")
    assert resp.status_code == 401


def test_scheduler_status_authenticated(auth_client):
    """GET /api/scheduler/status returns complete telemetry payload."""
    client, user_id, _ = auth_client
    resp = client.get("/api/scheduler/status")
    assert resp.status_code == 200
    data = resp.json()

    # Validate against Pydantic schema
    status_obj = SchedulerStatusResponse(**data)
    assert status_obj.is_enabled is True
    assert status_obj.schedule_interval_hours == 2
    assert status_obj.cron_expression == "0 */2 * * *"
    assert status_obj.human_description == "Every 2 hours"
    assert status_obj.has_udemy_auth is True
    assert status_obj.active_scrapers_count == 19
    assert status_obj.is_run_in_progress is False


def test_scheduler_update_csrf_rejection(auth_client):
    """POST /api/scheduler/update requires valid CSRF token."""
    client, _, _ = auth_client
    resp = client.post(
        "/api/scheduler/update",
        json={"schedule_interval_hours": 4},
        headers={"X-CSRF-Token": "invalid_csrf_token"},
    )
    assert resp.status_code == 403


def test_scheduler_update_empty_payload(auth_client):
    """POST /api/scheduler/update rejects empty payload with 400 Bad Request."""
    client, _, _ = auth_client
    resp = client.post("/api/scheduler/update", json={})
    assert resp.status_code == 400
    assert "Either schedule_interval_hours or cron_preset" in resp.json()["detail"]


def test_scheduler_update_invalid_hours(auth_client):
    """POST /api/scheduler/update rejects negative hours with 422."""
    client, _, _ = auth_client
    resp = client.post("/api/scheduler/update", json={"schedule_interval_hours": -1})
    assert resp.status_code == 422


def test_scheduler_update_preset_success(auth_client):
    """POST /api/scheduler/update supports named presets (1h, 4h, 24h, disabled)."""
    client, _, _ = auth_client
    resp = client.post("/api/scheduler/update", json={"cron_preset": "4h"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["schedule_interval_hours"] == 4
    assert data["cron_expression"] == "0 */4 * * *"
    assert data["human_description"] == "Every 4 hours"

    # Disable schedule
    resp2 = client.post("/api/scheduler/update", json={"cron_preset": "disabled"})
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["is_enabled"] is False
    assert data2["schedule_interval_hours"] == 0
    assert data2["cron_expression"] is None


def test_scheduler_trigger_conflict_when_run_active(auth_client):
    """POST /api/scheduler/trigger returns 409 Conflict if a run is already active."""
    client, user_id, _ = auth_client
    db = TestingSessionLocal()
    active_run = EnrollmentRun(
        user_id=user_id,
        status="scraping",
        total_courses_found=10,
        successfully_enrolled=0,
    )
    db.add(active_run)
    db.commit()
    db.close()

    resp = client.post("/api/scheduler/trigger")
    assert resp.status_code == 409
    assert "already active" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_trigger_run_socket_cleanup_on_error():
    """Verify UdemyClient.close() is awaited if EnrollmentManager.start_run fails."""
    db = TestingSessionLocal()
    salt = generate_cookie_salt()
    encrypted_cookies = encrypt_cookies_salted({"access_token": "valid"}, salt)

    user = User(
        email=f"sched-leak-{secrets.token_hex(4)}@example.com",
        password_hash="pw",
        udemy_cookies=encrypted_cookies,
        cookies_salt=salt,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    settings = UserSettings(
        user_id=user.id,
        sites={"Coursevania": True},
        languages=["en"],
        categories=["Development"],
    )
    db.add(settings)
    db.commit()

    mock_client = AsyncMock()
    mock_client.close = AsyncMock()

    with patch.object(EnrollmentScheduler, "restore_user_client", return_value=mock_client), \
         patch("app.services.enrollment_manager.EnrollmentManager.start_run", side_effect=ValueError("Simulated pipeline crash")):
        with pytest.raises(Exception):
            await trigger_run_for_user(user.id, db)

        # Assert socket was cleaned up in finally block (FM-01, FM-02)
        mock_client.close.assert_awaited_once()

    db.close()


def test_scheduler_update_explicit_json_success(auth_client):
    """POST /api/scheduler/update with explicit application/json header succeeds."""
    client, _, _ = auth_client
    resp = client.post(
        "/api/scheduler/update",
        data=json.dumps({"cron_preset": "4h"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_enabled"] is True
    assert data["schedule_interval_hours"] == 4


def test_scheduler_update_text_plain_rejection_reproduction(auth_client):
    """POST /api/scheduler/update with text/plain header reproduces 422 Unprocessable Entity."""
    client, _, _ = auth_client
    resp = client.post(
        "/api/scheduler/update",
        data='{"cron_preset": "2h"}',
        headers={"Content-Type": "text/plain;charset=UTF-8"},
    )
    assert resp.status_code == 422
    data = resp.json()
    assert data["detail"][0]["loc"] == ["body"]


def test_frontend_assets_scheduler_content_type_and_error_handling():
    """Verify frontend assets enforce error handling and Content-Type defense."""
    app_js_path = Path("app/static/js/app.js")
    dashboard_html_path = Path("app/templates/pages/dashboard.html")

    app_js_content = app_js_path.read_text(encoding="utf-8")
    dashboard_content = dashboard_html_path.read_text(encoding="utf-8")

    assert "extractErrorDetail" in dashboard_content
    assert "extractErrorDetail(err" in dashboard_content
    assert dashboard_content.count("extractErrorDetail") >= 3
    assert "formatToastMessage" in app_js_content
    assert 'options.headers["Content-Type"] = "application/json"' in app_js_content
    assert '"Content-Type": "application/json"' in dashboard_content
