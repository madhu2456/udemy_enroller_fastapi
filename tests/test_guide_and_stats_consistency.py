"""Regression tests for Fix #9: guides copy (cookie-first) and homepage zero-impact fallback.

The homepage fallback test uses the cache-bypass pattern from
tests/test_platform_stats.py: patching ``get_cached_or_compute`` with a
side_effect that calls compute_fn directly, so the real 300s module cache is
never written and no DB totals leak in from a previous test run.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


def test_homepage_zero_impact_fallback():
    from app.core.platform_stats import _platform_stats_cache

    _platform_stats_cache.clear()
    client = TestClient(app)
    try:
        with patch(
            "app.core.platform_stats.get_cached_or_compute",
            side_effect=lambda cache, key, compute_fn, ttl_seconds=300: compute_fn(),
        ), patch(
            "app.core.platform_stats.compute_platform_impact_stats",
            return_value={"total_enrolled": 0, "total_amount_saved": 0.0},
        ), patch(
            "app.core.platform_stats._public_coupon_count",
            return_value=5,
        ):
            response = client.get("/")
    finally:
        client.close()

    assert response.status_code == 200
    assert "Free coupons listed" in response.text
    assert "Courses enrolled via automation" not in response.text
    assert "Estimated savings (aggregate)" not in response.text


def test_guides_page_cookie_first():
    # Scope all assertions to the /guides response ONLY: the string "only
    # Cookie Login is available" ALSO exists on /faq, so never widen the scope.
    client = TestClient(app)
    try:
        response = client.get("/guides")
    finally:
        client.close()

    assert response.status_code == 200
    assert "Choose Cookie Login" in response.text
    assert "switch to the Cookie Login tab" in response.text
    assert "Email Login is available only when you self-host" in response.text
    assert "For the quickest setup, enter your Udemy" not in response.text
    assert "Cookie Login is the only login option on the hosted demo" in response.text


def test_f320_guides_index_lead_is_definition():
    """UI-ENR-02 / F320: /guides first prose p after H1 is a 40–60 word definition."""
    import re

    from bs4 import BeautifulSoup

    client = TestClient(app)
    try:
        response = client.get("/guides")
    finally:
        client.close()

    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    h1 = soup.select_one("#guides-hero-heading")
    assert h1 is not None
    lead = h1.find_next_sibling("p")
    assert lead is not None
    text = re.sub(r"\s+", " ", lead.get_text()).strip()
    words = text.split()
    assert 40 <= len(words) <= 60, f"lead word count {len(words)}: {text}"
    assert "session cookies" in text.lower()
    assert "5 minutes" in text
    assert lead.find("a") is None
    assert "best" not in text.lower()


def test_f320_guide_lead_promotes_existing_definition():
    """F320: first paragraph after H1 is the existing ~49w coupon definition."""
    import re

    from bs4 import BeautifulSoup

    client = TestClient(app)
    try:
        response = client.get("/guides/free-udemy-coupons")
    finally:
        client.close()

    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    h1 = soup.select_one("article header h1")
    assert h1 is not None
    lead = h1.find_next_sibling("p")
    assert lead is not None
    text = re.sub(r"\s+", " ", lead.get_text()).strip()
    words = text.split()
    assert 40 <= len(words) <= 60, f"lead word count {len(words)}: {text}"
    assert "promotional discount codes" in text
    assert "100% off" in text
    assert "Madhu Dadi" in response.text
    assert "not affiliated with udemy" in response.text.lower()
