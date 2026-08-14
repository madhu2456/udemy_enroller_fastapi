"""F-ENRL-C03: anonymous double-submit CSRF guard on the login POSTs.

The login page sets a random ``csrf_token`` cookie (samesite=strict); both
``POST /api/auth/login`` and ``POST /api/auth/login/cookies`` must receive the
same value in the ``X-CSRF-Token`` header, and browser requests must be
same-origin. Requests without an Origin/Referer header (curl, API clients)
cannot be CSRF targets and are allowed.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.routers import auth
from main import app

LOGIN_ENDPOINTS = ["/api/auth/login", "/api/auth/login/cookies"]

COOKIE_BODY = {
    "access_token": "csrf-access-token",
    "client_id": "csrf-client-id",
    "csrf_token": "csrf-cookie-token",
}


def _email_body() -> dict:
    return {
        "email": f"csrf-{secrets.token_hex(4)}@example.com",
        "password": "SecurePassword123!",
    }


def _body_for(path: str) -> dict:
    return COOKIE_BODY if path.endswith("/cookies") else _email_body()


def _mock_udemy_client() -> MagicMock:
    client = MagicMock()
    client.manual_login = AsyncMock(return_value=None)
    client.cookie_login = MagicMock(return_value=None)
    client.get_session_info = AsyncMock(return_value=None)
    client.close = AsyncMock(return_value=None)
    client.udemy_user_id = 90210
    client.display_name = "CSRF Test"
    client.currency = "USD"
    client.cookie_dict = {"access_token": "t", "client_id": "c"}
    return client


@pytest.fixture(autouse=True)
def _login_edges(monkeypatch):
    """Local mode + bypassed rate limiter so CSRF is the only gate under test."""
    monkeypatch.setattr(auth.settings, "DEPLOYMENT_ENV", "local")
    monkeypatch.setattr(
        auth.login_rate_limiter, "is_allowed_redis", AsyncMock(return_value=True)
    )


def _fresh_client() -> TestClient:
    client = TestClient(app)
    client.cookies.clear()
    return client


def _load_csrf_cookie(client: TestClient) -> str:
    """GET / like a browser would, returning the anonymous csrf_token cookie."""
    page = client.get("/", follow_redirects=False)
    assert page.status_code == 200
    token = page.cookies.get("csrf_token")
    assert token, "login page must set the anonymous csrf_token cookie"
    return token


@pytest.mark.parametrize("path", LOGIN_ENDPOINTS)
def test_login_without_csrf_header_is_rejected(path):
    client = _fresh_client()
    try:
        response = client.post(path, json=_body_for(path))
        assert response.status_code == 403
        assert response.json()["detail"] == "CSRF token missing"
    finally:
        client.close()


@pytest.mark.parametrize("path", LOGIN_ENDPOINTS)
def test_login_with_forged_csrf_header_is_rejected(path):
    client = _fresh_client()
    try:
        _load_csrf_cookie(client)
        response = client.post(
            path,
            json=_body_for(path),
            headers={"X-CSRF-Token": "forged-token-value"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "CSRF token invalid"
    finally:
        client.close()


@pytest.mark.parametrize("path", LOGIN_ENDPOINTS)
def test_login_from_cross_origin_is_rejected(path):
    client = _fresh_client()
    try:
        token = _load_csrf_cookie(client)
        response = client.post(
            path,
            json=_body_for(path),
            headers={"X-CSRF-Token": token, "Origin": "https://evil.example"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Cross-origin request rejected"
    finally:
        client.close()


@pytest.mark.parametrize("path", LOGIN_ENDPOINTS)
def test_login_with_cross_origin_referer_is_rejected(path):
    client = _fresh_client()
    try:
        token = _load_csrf_cookie(client)
        response = client.post(
            path,
            json=_body_for(path),
            headers={
                "X-CSRF-Token": token,
                "Referer": "https://evil.example/phishing-page",
            },
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Cross-origin request rejected"
    finally:
        client.close()


@pytest.mark.parametrize("path", LOGIN_ENDPOINTS)
def test_login_succeeds_with_valid_csrf(monkeypatch, path):
    client = _fresh_client()
    try:
        token = _load_csrf_cookie(client)
        mock_client = _mock_udemy_client()
        monkeypatch.setattr(auth, "UdemyClient", lambda: mock_client)
        response = client.post(
            path,
            json=_body_for(path),
            headers={"X-CSRF-Token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert mock_client.close.await_count == 0  # client handed off to session
    finally:
        client.close()


@pytest.mark.parametrize("path", LOGIN_ENDPOINTS)
def test_login_accepts_same_origin_origin_header(monkeypatch, path):
    """Browsers send Origin on POSTs — same-origin must pass the origin gate."""
    client = _fresh_client()
    try:
        token = _load_csrf_cookie(client)
        mock_client = _mock_udemy_client()
        monkeypatch.setattr(auth, "UdemyClient", lambda: mock_client)
        response = client.post(
            path,
            json=_body_for(path),
            headers={"X-CSRF-Token": token, "Origin": "http://testserver"},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True
    finally:
        client.close()


@pytest.mark.parametrize("path", LOGIN_ENDPOINTS)
def test_login_origin_gate_passes_behind_scheme_mismatched_proxy(monkeypatch, path):
    """Cloudflare Flexible repro (R1): browsers send Origin https while the app
    sees http (nginx X-Forwarded-Proto: $scheme, rewritten by uvicorn proxy
    headers). The netloc-only comparison must pass; the double-submit token
    check must still reject a forged header."""
    client = _fresh_client()
    try:
        token = _load_csrf_cookie(client)
        mock_client = _mock_udemy_client()
        monkeypatch.setattr(auth, "UdemyClient", lambda: mock_client)
        headers = {
            "X-CSRF-Token": token,
            "Origin": "https://testserver",
            "X-Forwarded-Proto": "http",
        }
        response = client.post(path, json=_body_for(path), headers=headers)
        assert response.status_code == 200
        assert response.json()["success"] is True

        forged = client.post(
            path,
            json=_body_for(path),
            headers={**headers, "X-CSRF-Token": "forged-token-value"},
        )
        assert forged.status_code == 403
        assert forged.json()["detail"] == "CSRF token invalid"
    finally:
        client.close()


@pytest.mark.parametrize("path", LOGIN_ENDPOINTS)
def test_login_origin_gate_honors_public_base_url(monkeypatch, path):
    """When PUBLIC_BASE_URL is set, its netloc is the expected origin instead
    of request.base_url — usable behind proxies where the app cannot infer the
    public host/scheme."""
    monkeypatch.setattr(
        auth.settings, "PUBLIC_BASE_URL", "https://udemyenroller.madhudadi.in"
    )
    client = _fresh_client()
    try:
        token = _load_csrf_cookie(client)
        mock_client = _mock_udemy_client()
        monkeypatch.setattr(auth, "UdemyClient", lambda: mock_client)
        response = client.post(
            path,
            json=_body_for(path),
            headers={
                "X-CSRF-Token": token,
                "Origin": "https://udemyenroller.madhudadi.in",
            },
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

        cross = client.post(
            path,
            json=_body_for(path),
            headers={"X-CSRF-Token": token, "Origin": "https://evil.example"},
        )
        assert cross.status_code == 403
        assert cross.json()["detail"] == "Cross-origin request rejected"
    finally:
        client.close()
