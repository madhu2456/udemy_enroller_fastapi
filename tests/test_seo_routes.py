"""Tests for SEO routes including /pricing.md (Wave 2/3)."""

from fastapi.testclient import TestClient
from main import app


def test_pricing_md_status_and_content():
    """Verify GET /pricing.md returns 200 OK with MIT open-source markdown content."""
    client = TestClient(app)
    try:
        response = client.get("/pricing.md")
    finally:
        client.close()

    assert response.status_code == 200
    assert "text/markdown" in response.headers.get("content-type", "")
    body = response.text
    assert "# Pricing — Udemy Course Enroller" in body
    assert "100% free and open-source software" in body
    assert "MIT License" in body
    assert "https://github.com/madhu2456/udemy_enroller_fastapi" in body
    assert "$0 / Free forever" in body
    assert "Self-Hosting" in body
    assert "Not Affiliated with Udemy" in body


def test_pricing_md_cache_control_headers():
    """Verify /pricing.md includes expected public cache-control headers."""
    client = TestClient(app)
    try:
        response = client.get("/pricing.md")
    finally:
        client.close()

    assert response.status_code == 200
    cc = response.headers.get("cache-control", "")
    assert "public" in cc
    assert "max-age=120" in cc
    assert "s-maxage=300" in cc
    assert "stale-while-revalidate=600" in cc


def test_robots_txt_status_and_content():
    """Verify GET /robots.txt returns text/plain."""
    client = TestClient(app)
    try:
        response = client.get("/robots.txt")
    finally:
        client.close()

    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    assert "User-agent:" in response.text


def test_humans_txt_status_and_content():
    """Verify GET /humans.txt returns text/plain."""
    client = TestClient(app)
    try:
        response = client.get("/humans.txt")
    finally:
        client.close()

    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    assert "Developer: Madhu Dadi" in response.text
