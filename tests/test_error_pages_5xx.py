"""F040: 5xx error template and safe exception handler (server errors).

Mirrors the TestClient render-assertion pattern from tests/test_cache_headers.py
(404 noindex precedent) and the leak-hygiene pattern from
tests/test_logout_transaction.py (exception detail must not surface).
"""

from fastapi import HTTPException
from fastapi.testclient import TestClient

from main import app


def _boom():
    raise RuntimeError("secret stack trace: SELECT * FROM users; TOKEN=abc123")


def test_browser_500_renders_safe_html_error_page():
    """HTML requests get the branded 500 page: no stack, SQL, or env leak."""
    client = TestClient(app, raise_server_exceptions=False)
    try:
        app.get("/boom-f040", include_in_schema=False)(_boom)
        response = client.get(
            "/boom-f040", headers={"Accept": "text/html,application/xhtml+xml"}
        )
    finally:
        app.router.routes = [
            route for route in app.router.routes
            if getattr(route, "path", None) != "/boom-f040"
        ]
        client.close()

    assert response.status_code == 500
    assert "text/html" in response.headers.get("content-type", "")
    body = response.text
    assert "Something went wrong" in body
    assert "secret stack trace" not in body
    assert "SELECT * FROM users" not in body
    assert "TOKEN=abc123" not in body
    assert "ueEvent('error_view', { error_code: '500' })" in body
    # X-Robots-Tag mirrors the 404 handler's noindex posture
    robots = response.headers.get("x-robots-tag", "").lower()
    assert "noindex" in robots
    cc = response.headers.get("cache-control", "")
    assert "no-store" in cc and "no-cache" in cc


def test_api_500_keeps_json_contract_without_leaking_details():
    """API paths (and non-HTML clients) keep a JSON body with a generic detail."""
    client = TestClient(app, raise_server_exceptions=False)
    try:
        app.get("/api/boom-f040", include_in_schema=False)(_boom)
        response = client.get("/api/boom-f040")
    finally:
        app.router.routes = [
            route for route in app.router.routes
            if getattr(route, "path", None) != "/api/boom-f040"
        ]
        client.close()

    assert response.status_code == 500
    assert "application/json" in response.headers.get("content-type", "")
    assert response.json() == {"detail": "Internal server error."}
    assert "secret stack trace" not in response.text


def test_intentional_json_500_from_settings_style_endpoints_unaffected():
    """Deliberate HTTPException(500) JSON responses are not hijacked by F040.

    The Exception-keyed handler lives at the ServerErrorMiddleware layer, so
    HTTPException-based JSON 5xx contracts (settings/auth style) keep both
    their status and their exact JSON shape.
    """

    def _teapot():
        raise HTTPException(status_code=500, detail="Failed to clear database records")

    client = TestClient(app)
    try:
        app.get("/teapot-f040", include_in_schema=False)(_teapot)
        response = client.get("/teapot-f040")
    finally:
        app.router.routes = [
            route for route in app.router.routes
            if getattr(route, "path", None) != "/teapot-f040"
        ]
        client.close()

    assert response.status_code == 500
    assert response.json() == {"detail": "Failed to clear database records"}


def test_accessibility_page_still_renders_with_statement_content():
    """F016: strengthened statement renders: date, honesty, keyboard notes."""
    client = TestClient(app)
    try:
        response = client.get("/accessibility")
    finally:
        client.close()

    assert response.status_code == 200
    body = response.text
    assert "Last updated: September 4, 2026" in body
    assert "WCAG 2.2 Level AA" in body
    assert "not a formal third-party certification claim" in body
    assert "Conformance status" in body
    assert "Keyboard and focus support" in body
    assert "prefers-reduced-motion" in body
    assert "Known limitations" in body
    assert "dashboard" in body.lower()
    assert "/contact" in body
    assert 'name="robots"' not in body or "noindex" not in body
