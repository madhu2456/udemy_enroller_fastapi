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


def test_f319_robots_comments_search_visibility_not_citation_labels():
    """F319: crawler-purpose comments say search-visibility; Allow/Deny unchanged.

    Tight pattern: only robots_txt comment lines. Google-Extended lines may
    still say the bot is *not* Search/AIO citation. Do not use ``citation = 0``.
    """
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "app/routers/seo.py"
    text = src.read_text(encoding="utf-8")
    start = text.index("async def robots_txt")
    end = text.index("return Response", start)
    block = text[start:end]
    comment_lines = [
        line.strip() for line in block.splitlines() if line.strip().startswith("#")
    ]
    for line in comment_lines:
        if "citation" not in line.lower():
            continue
        assert "google-extended" in line.lower(), line
        assert "not" in line.lower(), line
        assert "search/citation" not in line.lower(), line

    client = TestClient(app)
    try:
        response = client.get("/robots.txt")
    finally:
        client.close()

    body = response.text
    assert "search/citation" not in body
    assert "search-visibility" in body
    assert "not Search/AIO citation" in body
    assert "User-agent: OAI-SearchBot" in body
    assert "User-agent: ChatGPT-User" in body
    assert "User-agent: Google-Extended" in body
    assert "User-agent: GPTBot" in body
    assert "Disallow: /history" in body
    assert "Disallow: /login" in body
    assert "Disallow: /settings" in body
    assert "Disallow: /api/" in body
    assert "Disallow: /dashboard" in body
    assert "Disallow: /" in body
    assert "Allow: /" in body


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
