"""Regression tests for the title-trademark fix: every title surface carries
"Udemy" at most once (≤1×) and stays ≤60 chars.

Covers the site-wide corrective batch: <title>, meta name="title", og:title,
twitter:title and the dynamic coupon SERP title.
"""

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.seo_meta import coupon_serp_title, sanitize_category_name
from main import app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DEALS_PATH = PROJECT_ROOT / "public_deals.json"

# Routes covered by the corrective batch. /about and /faq are controls that
# already complied before the change.
TITLE_ROUTES = [
    "/",
    "/udemycoupons",
    "/udemycoupons/category/development",
    "/guides/free-udemy-coupons",
    "/about",
    "/faq",
]

UDEMY_WORD = re.compile(r"\bUdemy\b")


def _count_udemy(text: str) -> int:
    return len(UDEMY_WORD.findall(text))


def _extract(pattern: str, html: str) -> str:
    m = re.search(pattern, html)
    assert m is not None, f"tag not found: {pattern}"
    return m.group(1).strip()


def _title(html: str) -> str:
    return _extract(r"<title>(.*?)</title>", html)


def _og_title(html: str) -> str:
    return _extract(r'property="og:title"\s+content="(.*?)"', html)


def _twitter_title(html: str) -> str:
    return _extract(r'name="twitter:title"\s+content="(.*?)"', html)


def _meta_name_title(html: str) -> str:
    return _extract(r'name="title"\s+content="(.*?)"', html)


def _render(route: str) -> str:
    """Render a route and return its HTML (matches repo try/finally style)."""
    client = TestClient(app)
    try:
        response = client.get(route)
        assert response.status_code == 200, route
        return response.text
    finally:
        client.close()


class TestTitleRulePages:
    """Rendered pages: <title> ≤1× Udemy, ≤60 chars, og/twitter parity."""

    def test_title_rule_on_all_routes(self):
        for route in TITLE_ROUTES:
            html = _render(route)
            title = _title(html)
            assert _count_udemy(title) <= 1, f"{route}: <title> {title!r}"
            assert len(title) <= 60, f"{route}: <title> len {len(title)}: {title!r}"

    def test_og_title_parity_on_all_routes(self):
        for route in TITLE_ROUTES:
            html = _render(route)
            title = _title(html)
            og = _og_title(html)
            assert _count_udemy(og) <= 1, f"{route}: og:title {og!r}"
            assert og == title, f"{route}: og:title {og!r} != <title> {title!r}"

    def test_twitter_title_parity_on_all_routes(self):
        for route in TITLE_ROUTES:
            html = _render(route)
            title = _title(html)
            tw = _twitter_title(html)
            assert _count_udemy(tw) <= 1, f"{route}: twitter:title {tw!r}"
            assert tw == title, f"{route}: twitter:title {tw!r} != <title> {title!r}"

    def test_meta_name_title_udemy_rule_on_all_routes(self):
        for route in TITLE_ROUTES:
            html = _render(route)
            meta = _meta_name_title(html)
            assert _count_udemy(meta) <= 1, f"{route}: meta name=title {meta!r}"


class TestTitleRuleCouponDetail:
    """Real coupon detail page: dynamic {{ seo_title }} obeys ≤1× / ≤60."""

    def _real_slug(self):
        data = json.loads(FIXTURE_DEALS_PATH.read_text(encoding="utf-8"))
        deals = data if isinstance(data, list) else data.get("deals", [])
        # Pick a non-trivial title (≥30 chars) so the SERP title really works.
        for deal in deals:
            title = (deal.get("title") or "").strip()
            if len(title) >= 30 and deal.get("slug"):
                return deal["slug"], title
        raise AssertionError("no suitable deal in public_deals.json fixture")

    def test_detail_page_title_rule(self):
        slug, raw_title = self._real_slug()
        html = _render(f"/udemycoupons/c/{slug}")
        title = _title(html)
        assert _count_udemy(title) <= 1, f"detail <title> {title!r} (from {raw_title!r})"
        assert len(title) <= 60, f"detail <title> len {len(title)}: {title!r}"
        # The detail page derives every title surface from {{ seo_title }}.
        assert _og_title(html) == title
        assert _twitter_title(html) == title
        assert _meta_name_title(html) == title


class TestCouponSerpTitleUdemyRule:
    """B2 guard: coupon_serp_title always carries "Udemy" exactly once."""

    def test_udemy_word_in_title_sanitized(self):
        title = coupon_serp_title("Udemy course")
        assert _count_udemy(title) == 1
        assert "Free course" not in title

    def test_empty_title_fallback_keeps_brand_once(self):
        title = coupon_serp_title("")
        assert "Free course" in title
        assert _count_udemy(title) == 1
        assert title.endswith("| Udemy Enroller")

    def test_case_insensitive_udemy_sanitized(self):
        title = coupon_serp_title("Learn Python UDEMY 101")
        assert _count_udemy(title) == 1
        assert "UDEMY" not in title
        assert "Learn Python 101" in title


class TestSanitizeCategoryName:
    """M4 guard: category display names never reintroduce the brand word."""

    def test_udemy_word_stripped(self):
        name = sanitize_category_name("Udemy Web Development")
        assert _count_udemy(name) == 0
        assert name == "Web Development"

    def test_long_name_truncated_to_max_len(self):
        name = sanitize_category_name("A" * 50)
        assert len(name) <= 40
        assert name.endswith("…")
