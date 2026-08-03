"""Cache-Control policy for public vs private pages (Fix 14)."""

from fastapi.testclient import TestClient

from main import app


def test_public_faq_allows_short_cdn_cache():
    client = TestClient(app)
    try:
        response = client.get("/faq")
    finally:
        client.close()

    assert response.status_code == 200
    cc = response.headers.get("cache-control", "")
    assert "public" in cc
    assert "max-age=120" in cc
    assert "s-maxage=300" in cc
    assert "stale-while-revalidate=600" in cc


def test_public_contact_allows_short_cdn_cache():
    client = TestClient(app)
    try:
        response = client.get("/contact")
    finally:
        client.close()

    assert response.status_code == 200
    cc = response.headers.get("cache-control", "")
    assert "public" in cc
    assert "max-age=120" in cc
    assert "s-maxage=300" in cc
    assert "stale-while-revalidate=600" in cc


def test_public_terms_allows_short_cdn_cache():
    client = TestClient(app)
    try:
        response = client.get("/terms")
    finally:
        client.close()

    assert response.status_code == 200
    cc = response.headers.get("cache-control", "")
    assert "public" in cc
    assert "max-age=120" in cc
    assert "s-maxage=300" in cc
    assert "stale-while-revalidate=600" in cc


def test_public_udemycoupons_allows_short_cdn_cache():
    client = TestClient(app)
    try:
        response = client.get("/udemycoupons")
    finally:
        client.close()

    assert response.status_code == 200
    cc = response.headers.get("cache-control", "")
    assert "public" in cc
    assert "s-maxage=300" in cc
    assert "max-age=120" in cc


def test_homepage_anonymous_is_public_with_vary_cookie():
    client = TestClient(app)
    try:
        response = client.get("/", follow_redirects=False)
    finally:
        client.close()

    assert response.status_code == 200
    cc = response.headers.get("cache-control", "")
    assert "public" in cc
    assert "s-maxage=300" in cc
    vary_parts = {
        p.strip().lower()
        for p in response.headers.get("vary", "").split(",")
        if p.strip()
    }
    assert "cookie" in vary_parts


def test_public_guides_missing_is_not_stored():
    client = TestClient(app)
    try:
        response = client.get("/guides/missing", follow_redirects=False)
    finally:
        client.close()

    assert response.status_code == 404
    cc = response.headers.get("cache-control", "")
    assert "no-store" in cc
    assert "no-cache" in cc


def test_static_missing_is_not_stored():
    client = TestClient(app)
    try:
        response = client.get(
            "/static/does-not-exist-fix14.css", follow_redirects=False
        )
    finally:
        client.close()

    assert response.status_code == 404
    cc = response.headers.get("cache-control", "")
    assert "no-store" in cc
    assert "no-cache" in cc


def test_sitemap_allows_six_hour_cache():
    client = TestClient(app)
    try:
        response = client.get("/sitemap.xml", follow_redirects=False)
    finally:
        client.close()

    assert response.status_code == 200
    cc = response.headers.get("cache-control", "")
    assert "public" in cc
    assert "max-age=21600" in cc or "s-maxage=21600" in cc


def test_dashboard_is_not_stored():
    client = TestClient(app)
    try:
        response = client.get("/dashboard", follow_redirects=False)
    finally:
        client.close()

    # Unauthenticated may redirect; either way must not be publicly cached
    cc = response.headers.get("cache-control", "")
    assert "no-store" in cc
    assert "no-cache" in cc


def test_settings_is_not_stored():
    client = TestClient(app)
    try:
        response = client.get("/settings", follow_redirects=False)
    finally:
        client.close()

    cc = response.headers.get("cache-control", "")
    assert "no-store" in cc
    assert "no-cache" in cc


def test_api_health_is_not_stored():
    client = TestClient(app)
    try:
        response = client.get("/api/health", follow_redirects=False)
    finally:
        client.close()

    # Endpoint may 404 if absent; private/API paths still must not be cached
    cc = response.headers.get("cache-control", "")
    assert "no-store" in cc
    assert "no-cache" in cc


def test_manifest_webmanifest_served_at_root():
    """Fix H3: PWA manifest is served at /manifest.webmanifest with the W3C media type."""
    client = TestClient(app)
    try:
        response = client.get("/manifest.webmanifest", follow_redirects=False)
    finally:
        client.close()

    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("application/manifest+json")

    data = response.json()
    assert data["name"] == "Udemy Enroller"
    assert data["short_name"] == "Udemy Enroller"
    assert data["start_url"] == "/"
    assert data["theme_color"] == "#ffffff"
    assert any(i.get("purpose") == "maskable" for i in data["icons"])


def test_hsts_max_age_matches_network(monkeypatch):
    """M1: HSTS in server mode must use the 2-year max-age used across the network."""
    from config.settings import Settings
    from cryptography.fernet import Fernet

    settings = Settings(
        DEPLOYMENT_ENV="server",
        SECRET_KEY="test-secret-key-0123456789abcdefghijklmnop",
        COOKIE_ENCRYPTION_KEY=Fernet.generate_key().decode(),
    )
    monkeypatch.setattr("main.get_settings", lambda: settings)

    client = TestClient(app)
    try:
        response = client.get("/", follow_redirects=False)
    finally:
        client.close()

    hsts = response.headers.get("strict-transport-security", "")
    assert "max-age=63072000" in hsts
    assert "includeSubDomains" in hsts
    assert "preload" in hsts
