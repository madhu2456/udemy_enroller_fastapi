"""Tests for HTTP security headers and PWA mobile meta tags."""

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from config.settings import Settings
from main import app

FORBIDDEN_POLICY_TOKENS = [
    "attribution-reporting",
    "private-aggregation",
    "private-state-token-issuance",
    "private-state-token-redemption",
    "join-ad-interest-group",
    "run-ad-auction",
    "browsing-topics",
]


def test_permissions_policy_header_standards_and_hygiene():
    """Verify Permissions-Policy is present, standard, and free of noisy experimental tokens."""
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        policy = response.headers.get("permissions-policy", "")
        assert "camera=()" in policy
        assert "microphone=()" in policy
        assert "geolocation=()" in policy
        for token in FORBIDDEN_POLICY_TOKENS:
            assert token not in policy, f"Forbidden Privacy Sandbox token found in Permissions-Policy: {token}"


def test_security_headers_baseline():
    """Verify baseline security headers: nosniff, frame denial, and referrer posture."""
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        headers = response.headers
        assert headers.get("x-content-type-options") == "nosniff"
        assert headers.get("x-frame-options") == "DENY"
        assert headers.get("referrer-policy") == "strict-origin-when-cross-origin"
        assert headers.get("cross-origin-opener-policy") == "same-origin-allow-popups"
        assert headers.get("cross-origin-embedder-policy") == "unsafe-none"
        assert headers.get("cross-origin-resource-policy") == "same-site"
        csp = headers.get("content-security-policy", "")
        assert "'self'" in csp
        assert "nonce-" in csp
        assert "'strict-dynamic'" in csp
        assert "script-src-attr 'none'" in csp
        assert "style-src-attr 'none'" in csp


def test_hsts_header_in_server_env(monkeypatch):
    """Verify Strict-Transport-Security header is injected when DEPLOYMENT_ENV='server'."""
    settings = Settings(
        DEPLOYMENT_ENV="server",
        SECRET_KEY="test-secret-key-0123456789abcdefghijklmnop",
        COOKIE_ENCRYPTION_KEY=Fernet.generate_key().decode(),
    )
    monkeypatch.setattr("main.get_settings", lambda: settings)

    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        hsts = response.headers.get("strict-transport-security", "")
        assert "max-age=63072000" in hsts
        assert "includeSubDomains" in hsts
        assert "preload" in hsts


def test_template_meta_tags_standards():
    """Verify HTML responses include standard mobile-web-app-capable and legacy apple tag."""
    with TestClient(app) as client:
        for path in ("/faq", "/login"):
            response = client.get(path)
            assert response.status_code == 200
            html = response.text
            assert '<meta name="mobile-web-app-capable" content="yes" />' in html or '<meta name="mobile-web-app-capable" content="yes">' in html
            assert '<meta name="apple-mobile-web-app-capable" content="yes" />' in html or '<meta name="apple-mobile-web-app-capable" content="yes">' in html
            assert '<meta name="apple-mobile-web-app-title" content="Udemy Enroller" />' in html or '<meta name="apple-mobile-web-app-title" content="Udemy Enroller">' in html
            assert '<link rel="manifest" href="/manifest.webmanifest"' in html
