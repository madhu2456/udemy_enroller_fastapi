"""RSS feed for free coupon listings (Fix 31)."""

from fastapi.testclient import TestClient

from main import app


def test_feed_xml_returns_rss():
    client = TestClient(app)
    try:
        response = client.get("/feed.xml", follow_redirects=False)
    finally:
        client.close()

    assert response.status_code == 200
    ct = response.headers.get("content-type", "")
    assert "application/rss+xml" in ct
    body = response.text
    assert 'rss version="2.0"' in body
    assert "<channel>" in body
    assert "Free Udemy Coupons — Enroller" in body
    assert "Not affiliated with Udemy" in body


def test_rss_xml_alias_matches_feed():
    client = TestClient(app)
    try:
        feed = client.get("/feed.xml", follow_redirects=False)
        alias = client.get("/rss.xml", follow_redirects=False)
    finally:
        client.close()

    assert feed.status_code == 200
    assert alias.status_code == 200
    assert "application/rss+xml" in alias.headers.get("content-type", "")
    assert 'rss version="2.0"' in alias.text
    assert "Free Udemy Coupons — Enroller" in alias.text


def test_feed_xml_cache_headers():
    client = TestClient(app)
    try:
        response = client.get("/feed.xml", follow_redirects=False)
    finally:
        client.close()

    assert response.status_code == 200
    cc = response.headers.get("cache-control", "")
    assert "public" in cc
    assert "max-age=900" in cc
    assert "s-maxage=900" in cc
