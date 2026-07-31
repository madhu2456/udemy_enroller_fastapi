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
