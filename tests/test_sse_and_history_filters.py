"""Unit and integration tests for SSE streaming endpoints and history faceted filtering (Wave 5)."""

import secrets
import pytest
from fastapi.testclient import TestClient

from app.models.database import SessionLocal, User, UserSession, UserSettings
from main import app


@pytest.fixture
def auth_client():
    """Client with authenticated test user session."""
    db = SessionLocal()
    user = User(
        email=f"sse-{secrets.token_hex(6)}@example.com",
        password_hash="x",
        udemy_display_name="SSE User",
        currency="usd",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id

    token = secrets.token_hex(32)
    db.add(UserSession(token=token, user_id=user.id))
    db.add(UserSettings(user_id=user.id))
    db.commit()
    db.close()

    client = TestClient(app)
    client.cookies.set("session_id", token)
    yield client, user_id

    client.cookies.clear()
    cleanup_db = SessionLocal()
    try:
        cleanup_db.query(UserSettings).filter_by(user_id=user_id).delete()
        cleanup_db.query(UserSession).filter_by(user_id=user_id).delete()
        cleanup_db.query(User).filter_by(id=user_id).delete()
        cleanup_db.commit()
    finally:
        cleanup_db.close()


def test_progress_stream_headers_and_completion_event(auth_client):
    """Verify /api/enrollment/progress/stream emits SSE headers and completed payload when idle (FM-007)."""
    client, _ = auth_client
    with client.stream("GET", "/api/enrollment/progress/stream") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        assert "no-cache" in response.headers.get("cache-control", "")
        assert response.headers.get("connection") == "keep-alive"
        assert response.headers.get("x-accel-buffering") == "no"

        # Read first event emitted
        first_line = next(response.iter_lines())
        assert first_line.startswith("data: ")
        assert "active" in first_line


def test_dashboard_logs_stream_headers(auth_client):
    """Verify /api/dashboard/logs/stream sets anti-buffering headers (FM-007)."""
    client, _ = auth_client
    with client.stream("GET", "/api/dashboard/logs/stream?tail=false") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        assert "no-cache" in response.headers.get("cache-control", "")
        assert response.headers.get("x-accel-buffering") == "no"


def test_dashboard_template_contains_sse_integration(auth_client):
    """Verify dashboard.html embeds EventSource streaming logic with fallback."""
    client, _ = auth_client
    response = client.get("/dashboard")
    assert response.status_code == 200
    html = response.text
    assert "startProgressStream" in html
    assert "/api/enrollment/progress/stream" in html
    assert "startProgressPollingFallback" in html


def test_history_template_contains_search_and_faceted_filters(auth_client):
    """Verify history.html embeds search and status filter controls."""
    client, _ = auth_client
    response = client.get("/history")
    assert response.status_code == 200
    html = response.text
    assert 'id="history-search-input"' in html
    assert 'id="history-status-filter"' in html
    assert "renderHistoryFeed" in html
    assert "searchDebounceTimer" in html
