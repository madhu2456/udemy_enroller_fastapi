"""D1 DSR (m3): data-subject export + account deletion on /api/settings.

Follows the tests/test_enrollment_csv_export.py pattern: isolated engine +
dependency override + TestClient with a seeded session. Raw cookie values
must never appear in the export; delete-account must wipe everything
including the User row.
"""

import secrets
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from app.models.database import (
    Base,
    EnrolledCourse,
    EnrollmentRun,
    User,
    UserSession,
    UserSettings,
    get_db,
)
from app.security import generate_csrf_token
from app.routers import settings as settings_router

_test_db_dir = tempfile.TemporaryDirectory(prefix="udemy-enroller-dsr-tests-")
_test_db_path = Path(_test_db_dir.name) / "test_dsr.db"
engine = create_engine(
    f"sqlite:///{_test_db_path}", connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

SECRET_CIPHERTEXT = "gAAAAABf228-dsr-leak-guard-ciphertext-value-12345"


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _dsr_env():
    app.dependency_overrides[get_db] = _override_get_db
    # Reset the export rate limiter so tests are independent.
    settings_router.export_rate_limiter._store.clear()
    try:
        yield
    finally:
        if app.dependency_overrides.get(get_db) is _override_get_db:
            app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def dsr_client():
    """TestClient with a user + completed run containing data + cookies."""
    db = TestingSessionLocal()
    user = User(
        email=f"dsr-{secrets.token_hex(6)}@example.com",
        password_hash="x",
        udemy_display_name="DSR User",
        udemy_cookies=SECRET_CIPHERTEXT,
        cookies_salt="c2FsdC1zYWx0LXNhbHQtc2FsdC1zYWx0",  # runtime-constructed fixture
        currency="usd",
        total_enrolled=3,
        total_amount_saved=120.5,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id

    token = secrets.token_hex(32)
    db.add(UserSession(token=token, user_id=user.id))
    db.add(UserSettings(user_id=user.id))
    run = EnrollmentRun(user_id=user.id, status="completed", currency="usd")
    db.add(run)
    db.commit()
    db.refresh(run)
    db.add(
        EnrolledCourse(
            enrollment_run_id=run.id,
            title="DSR Test Course",
            url="https://www.udemy.com/course/dsr-test/",
            coupon_code="DSRCOUPON",
            status="enrolled",
        )
    )
    db.commit()
    db.close()

    client = TestClient(app)
    client.cookies.set("session_id", token)
    yield client, user_id, token

    client.cookies.clear()
    db = TestingSessionLocal()
    try:
        # Clean up only what this fixture installed.
        db.query(EnrolledCourse).delete()
        db.query(EnrollmentRun).delete()
        db.query(UserSession).delete()
        db.query(UserSettings).delete()
        db.query(User).delete()
        db.commit()
    finally:
        db.close()


def _csrf_headers(token: str) -> dict:
    return {"X-CSRF-Token": generate_csrf_token(token)}


class TestDataExport:
    def test_export_requires_auth(self, dsr_client):
        client, _user_id, _token = dsr_client
        anon = TestClient(app)
        try:
            response = anon.post("/api/settings/export")
            assert response.status_code == 401
        finally:
            anon.close()

    def test_export_requires_csrf(self, dsr_client):
        client, _user_id, _token = dsr_client
        response = client.post("/api/settings/export")
        assert response.status_code == 403

    def test_export_returns_metadata_and_no_cookie_values(self, dsr_client):
        client, _user_id, token = dsr_client
        response = client.post(
            "/api/settings/export", headers=_csrf_headers(token)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["user"]["email"].startswith("dsr-")
        assert data["stats"]["total_enrolled"] == 3
        assert data["cookie_presence"] is True
        assert len(data["runs"]) == 1
        assert data["runs"][0]["successfully_enrolled"] >= 0
        assert len(data["courses"]) == 1
        assert data["courses"][0]["title"] == "DSR Test Course"
        assert len(data["sessions"]) == 1
        assert data["settings_present"] is True
        # Raw cookie ciphertext must never leak into the export.
        assert SECRET_CIPHERTEXT not in response.text
        assert "cookies_salt" not in response.text
        assert "udemy_cookies" not in response.text

    def test_export_rate_limited(self, dsr_client):
        client, _user_id, token = dsr_client
        for _ in range(5):
            assert (
                client.post("/api/settings/export", headers=_csrf_headers(token)).status_code
                == 200
            )
        response = client.post("/api/settings/export", headers=_csrf_headers(token))
        assert response.status_code == 429


class TestDeleteAccount:
    def test_delete_requires_confirm(self, dsr_client):
        client, _user_id, token = dsr_client
        response = client.post(
            "/api/settings/delete-account",
            headers=_csrf_headers(token),
            json={},
        )
        assert response.status_code == 400

    def test_delete_rejects_wrong_confirm(self, dsr_client):
        client, _user_id, token = dsr_client
        response = client.post(
            "/api/settings/delete-account",
            headers=_csrf_headers(token),
            json={"confirm": "delete"},
        )
        assert response.status_code == 400
        db = TestingSessionLocal()
        try:
            assert db.query(User).count() >= 1
        finally:
            db.close()

    def test_delete_requires_auth_and_csrf(self, dsr_client):
        client, _user_id, token = dsr_client
        anon = TestClient(app)
        try:
            assert anon.post("/api/settings/delete-account", json={"confirm": "DELETE"}).status_code == 401
        finally:
            anon.close()
        assert (
            client.post(
                "/api/settings/delete-account", json={"confirm": "DELETE"}
            ).status_code
            == 403
        )

    def test_delete_wipes_user_and_all_data(self, dsr_client):
        client, user_id, token = dsr_client
        response = client.post(
            "/api/settings/delete-account",
            headers=_csrf_headers(token),
            json={"confirm": "DELETE"},
        )
        assert response.status_code == 200
        db = TestingSessionLocal()
        try:
            assert db.query(User).filter(User.id == user_id).first() is None
            assert db.query(UserSession).filter(UserSession.user_id == user_id).count() == 0
            assert db.query(UserSettings).filter(UserSettings.user_id == user_id).count() == 0
            assert db.query(EnrollmentRun).filter(EnrollmentRun.user_id == user_id).count() == 0
            assert db.query(EnrolledCourse).count() == 0
        finally:
            db.close()

    def test_delete_account_cancels_active_runs_and_deletes(self, dsr_client):
        """Active in-flight runs have their tasks cancelled and deletion cascades (Enroller D1)."""
        from unittest.mock import MagicMock
        from app.services.enrollment_manager import EnrollmentManager

        client, user_id, token = dsr_client
        db = TestingSessionLocal()
        try:
            active = EnrollmentRun(user_id=user_id, status="pending", currency="usd")
            db.add(active)
            db.commit()
            db.refresh(active)
            active_run_id = active.id
        finally:
            db.close()

        mock_task = MagicMock()
        EnrollmentManager.active_tasks[active_run_id] = mock_task

        try:
            response = client.post(
                "/api/settings/delete-account",
                headers=_csrf_headers(token),
                json={"confirm": "DELETE"},
            )
            assert response.status_code == 200
            mock_task.cancel.assert_called_once()

            db = TestingSessionLocal()
            try:
                assert db.query(User).filter(User.id == user_id).first() is None
                assert db.query(EnrollmentRun).filter(EnrollmentRun.user_id == user_id).count() == 0
                assert db.query(UserSession).filter(UserSession.user_id == user_id).count() == 0
            finally:
                db.close()
        finally:
            EnrollmentManager.active_tasks.pop(active_run_id, None)

    def test_old_session_fails_after_delete(self, dsr_client):
        client, user_id, token = dsr_client
        response = client.post(
            "/api/settings/delete-account",
            headers=_csrf_headers(token),
            json={"confirm": "DELETE"},
        )
        assert response.status_code == 200
        # The session row is gone: re-authenticating with the old token fails.
        status = client.get("/api/auth/status")
        assert status.json()["authenticated"] is False
        settings_resp = client.get("/api/settings/")
        assert settings_resp.status_code == 401

    def test_delete_notes_backup_retention_window(self, dsr_client):
        client, _user_id, token = dsr_client
        response = client.post(
            "/api/settings/delete-account",
            headers=_csrf_headers(token),
            json={"confirm": "DELETE"},
        )
        assert response.status_code == 200
        assert "backups" in response.json()["message"].lower()


def test_privacy_page_documents_export_and_delete_account():
    """J.9: /privacy must describe Settings export and delete-account."""
    client = TestClient(app)
    try:
        response = client.get("/privacy")
    finally:
        client.close()

    assert response.status_code == 200
    body = response.text
    assert "POST /api/settings/export" in body
    assert "POST /api/settings/delete-account" in body
    assert "Export Your Data" in body
    assert "Delete Account" in body
    assert "2026-08-19" in body
    assert "Stored Udemy cookies are never included" in body
