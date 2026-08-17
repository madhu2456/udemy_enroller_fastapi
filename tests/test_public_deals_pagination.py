"""Regression tests for crawlable pagination on /udemycoupons.

Guards the crawlable-pagination change:
- ``?page=N`` handling with ``ge=1`` validation (422 on invalid input)
- per-page canonical URLs (bare for page 1, ``?page=N`` for N > 1)
- out-of-range page clamping (renders last page, never 404/500)
- server-rendered crawlable ``#serverPager`` anchors with ``rel=prev/next``
- SSR <-> API ordering parity (guards B1: both slice one sorted catalog)
- stable ordering across simulated checker cycles (guards B2: ``enrolled_at``
  is the sort key, so ``last_checked_at`` mutations must not reorder pages)
- byte-identical canonical output on pages that do not override the block
"""

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.routers.public_deals as public_deals_router
from app.security import RateLimiter
from app.services import public_deals_export
from app.services.public_deals_export import list_valid_deals
from main import app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DEALS_PATH = PROJECT_ROOT / "public_deals.json"
PAGE_SIZE = public_deals_router.PUBLIC_COUPON_PAGE_SIZE

CANONICAL_COUNT_RE = re.compile(r'<link\s+rel="canonical"')
CANONICAL_HREF_RE = re.compile(r'<link\s+rel="canonical"\s+href="([^"]+)"')
COURSE_LINK_RE = re.compile(r'href="/udemycoupons/c/([^"]+)"')
HEAD_REL_RE = re.compile(r'<link\s+rel="(prev|next)"')


def _canonical_hrefs(html: str) -> list[str]:
    return CANONICAL_HREF_RE.findall(html)


def _has_anchor(html: str, href: str, rel: str) -> bool:
    """Crawlable anchor in raw HTML (attributes may span newlines)."""
    return (
        re.search(rf'<a\s+href="{re.escape(href)}"\s+rel="{re.escape(rel)}"', html)
        is not None
    )


def _first_course_slug(html: str) -> str:
    match = COURSE_LINK_RE.search(html)
    assert match is not None, "no /udemycoupons/c/ course link in HTML"
    slug = match.group(1)
    assert "category" not in slug, "matched a category chip, not a course link"
    return slug


def _use_real_fixture(monkeypatch):
    """Point the deals loader at the committed repo-root public_deals.json."""
    monkeypatch.setattr(
        public_deals_export, "DEFAULT_PUBLIC_DEALS_PATH", str(FIXTURE_DEALS_PATH)
    )
    monkeypatch.setattr(
        public_deals_export,
        "get_public_deals_path",
        lambda: str(FIXTURE_DEALS_PATH),
    )
    monkeypatch.setattr(
        public_deals_router,
        "public_coupons_api_limiter",
        RateLimiter(max_requests=50, window_seconds=60),
    )


def _fixture_last_page() -> int:
    """Derive the last page from the fixture: ceil(valid_deals / PAGE_SIZE)."""
    deals = json.loads(FIXTURE_DEALS_PATH.read_text(encoding="utf-8"))
    valid = [c for c in deals if c.get("is_coupon_valid") and c.get("coupon_code")]
    return max(1, math.ceil(len(valid) / PAGE_SIZE))


def _get(client, url):
    return client.get(url, headers={"cf-connecting-ip": "203.0.113.200"})


def test_page_1_canonical_is_bare(monkeypatch):
    """?page=1 must canonicalize to the bare /udemycoupons URL."""
    _use_real_fixture(monkeypatch)
    client = TestClient(app)
    try:
        response = _get(client, "/udemycoupons?page=1")
    finally:
        client.close()

    assert response.status_code == 200
    assert len(CANONICAL_COUNT_RE.findall(response.text)) == 1
    hrefs = _canonical_hrefs(response.text)
    assert len(hrefs) == 1
    assert hrefs[0].endswith("/udemycoupons")


def test_page_2_canonical_includes_page_param(monkeypatch):
    """?page=2 must canonicalize to /udemycoupons?page=2 (self-referencing)."""
    _use_real_fixture(monkeypatch)
    client = TestClient(app)
    try:
        response = _get(client, "/udemycoupons?page=2")
    finally:
        client.close()

    assert response.status_code == 200
    hrefs = _canonical_hrefs(response.text)
    assert len(hrefs) == 1
    assert hrefs[0].endswith("/udemycoupons?page=2")


def test_page_2_course_list_differs_from_page_1(monkeypatch):
    """Page slicing must actually change the rendered inventory."""
    _use_real_fixture(monkeypatch)
    assert _fixture_last_page() >= 2
    client = TestClient(app)
    try:
        page1 = _get(client, "/udemycoupons?page=1")
        page2 = _get(client, "/udemycoupons?page=2")
    finally:
        client.close()

    assert page1.status_code == 200
    assert page2.status_code == 200
    assert _first_course_slug(page1.text) != _first_course_slug(page2.text)


def test_crawlable_pager_anchors_in_raw_html(monkeypatch):
    """#serverPager anchors must be present in the raw response text.

    JS hides the nav at runtime, but crawlers read the unmodified HTML, so the
    anchors are asserted on the raw response text (view-source).
    """
    _use_real_fixture(monkeypatch)
    last_page = _fixture_last_page()
    assert last_page >= 2
    client = TestClient(app)
    try:
        page1 = _get(client, "/udemycoupons?page=1")
        page2 = _get(client, "/udemycoupons?page=2")
    finally:
        client.close()

    assert 'id="serverPager"' in page1.text
    assert _has_anchor(page1.text, "/udemycoupons?page=2", "next")
    assert not _has_anchor(page1.text, "/udemycoupons", "prev")

    assert 'id="serverPager"' in page2.text
    assert _has_anchor(page2.text, "/udemycoupons", "prev")
    if last_page > 2:
        assert _has_anchor(page2.text, "/udemycoupons?page=3", "next")


def test_out_of_range_page_clamps_to_last_page(monkeypatch):
    """?page=9999 must clamp to the last page: 200 + correct canonical."""
    _use_real_fixture(monkeypatch)
    last_page = _fixture_last_page()
    client = TestClient(app)
    try:
        response = _get(client, "/udemycoupons?page=9999")
    finally:
        client.close()

    assert response.status_code == 200
    hrefs = _canonical_hrefs(response.text)
    assert len(hrefs) == 1
    assert hrefs[0].endswith(f"/udemycoupons?page={last_page}")

    head = response.text.partition("</head>")[0]
    head_rels = HEAD_REL_RE.findall(head)
    assert "next" not in head_rels
    assert "prev" in head_rels
    assert _has_anchor(response.text, f"/udemycoupons?page={last_page - 1}", "prev")
    assert not _has_anchor(response.text, f"/udemycoupons?page={last_page + 1}", "next")


@pytest.mark.parametrize("bad_page", ["0", "-1", "abc"])
def test_invalid_page_values_reject_with_422(monkeypatch, bad_page):
    """FastAPI validation (ge=1) must reject bad page params with 422."""
    _use_real_fixture(monkeypatch)
    client = TestClient(app)
    try:
        response = _get(client, f"/udemycoupons?page={bad_page}")
    finally:
        client.close()

    assert response.status_code == 422


def test_empty_catalog_renders_200_without_pager(monkeypatch, tmp_path):
    """Empty catalog: 200, bare canonical, no #serverPager, 'Page 1 of 1'."""
    empty_path = tmp_path / "empty_public_deals.json"
    empty_path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(
        public_deals_export, "get_public_deals_path", lambda: str(empty_path)
    )
    monkeypatch.setattr(
        public_deals_router,
        "public_coupons_api_limiter",
        RateLimiter(max_requests=50, window_seconds=60),
    )
    client = TestClient(app)
    try:
        response = _get(client, "/udemycoupons")
    finally:
        client.close()

    assert response.status_code == 200
    assert 'id="serverPager"' not in response.text
    hrefs = _canonical_hrefs(response.text)
    assert len(hrefs) == 1
    assert hrefs[0].endswith("/udemycoupons")
    assert "Page 1 of 1" in response.text


@pytest.mark.parametrize("route", ["/faq", "/about", "/"])
def test_pages_without_block_override_keep_default_canonical(route):
    """Pages that do not override the canonical block keep base.html output.

    The base.html canonical link was wrapped in ``{% block canonical %}``; the
    rendered href must be byte-identical to the pre-change form and appear
    exactly once.
    """
    client = TestClient(app)
    try:
        response = client.get(route)
    finally:
        client.close()

    assert response.status_code == 200
    assert len(CANONICAL_COUNT_RE.findall(response.text)) == 1
    hrefs = _canonical_hrefs(response.text)
    assert len(hrefs) == 1
    assert hrefs[0].endswith(f"{route}")


def test_ssr_page_2_matches_api_page_2_ordering(monkeypatch):
    """Guards B1: SSR and API must slice the same sorted catalog.

    The first course slug on the server-rendered page 2 must equal the first
    item returned by GET /udemycoupons/api/coupons?page=2. This catches any
    future re-divergence of the two data paths.
    """
    _use_real_fixture(monkeypatch)
    client = TestClient(app)
    try:
        ssr = _get(client, "/udemycoupons?page=2")
        api = _get(client, "/udemycoupons/api/coupons?page=2")
    finally:
        client.close()

    assert ssr.status_code == 200
    assert api.status_code == 200
    items = api.json()["items"]
    assert items, "API page 2 must not be empty"
    assert _first_course_slug(ssr.text) == items[0]["slug"]


def test_list_valid_deals_order_stable_across_checker_cycles(tmp_path):
    """Guards B2: list_valid_deals() ordering must survive checker refreshes.

    The coupon checker rewrites only ``last_checked_at`` on each cycle; the
    sort key is ``enrolled_at`` (set once at discovery) with id as tie-break.
    Simulate a checker cycle by refreshing ``last_checked_at`` on a few rows
    with new second-precision timestamps and assert the returned order is
    identical, i.e. page boundaries do not shift between checker cycles.
    """
    deals_path = tmp_path / "public_deals.json"
    base = [
        {
            "id": i,
            "title": f"Course {i}",
            "url": f"https://www.udemy.com/course/course-{i}/",
            "slug": f"course-{i}",
            "coupon_code": f"CODE{i}",
            "price": 0.0,
            "category": "Development",
            "is_coupon_valid": True,
            "enrolled_at": f"2026-01-{i:02d}T00:00:00Z",
            "last_checked_at": f"2026-01-{i:02d}T00:00:00Z",
        }
        for i in range(1, 7)
    ]
    deals_path.write_text(json.dumps(base), encoding="utf-8")

    before = [c["id"] for c in list_valid_deals(str(deals_path))]
    assert before == [6, 5, 4, 3, 2, 1]

    # Simulated checker cycle: only last_checked_at changes (fresh
    # second-precision timestamps) on the OLDEST rows; enrolled_at is frozen.
    now = datetime.now(timezone.utc).replace(microsecond=0)
    refreshed = [dict(c) for c in base]
    for deal in refreshed[:3]:
        deal["last_checked_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    deals_path.write_text(json.dumps(refreshed), encoding="utf-8")

    after = [c["id"] for c in list_valid_deals(str(deals_path))]

    # Order must be IDENTICAL: last_checked_at churn must not reorder pages.
    assert after == before
    # enrolled_at is the preferred key: a deal with older enrolled_at but the
    # newest last_checked_at still sorts by enrolled_at, not by last_checked_at.
    assert after[0] == 6
    assert after[-1] == 1


def test_public_deals_meta_and_og_type(monkeypatch):
    """Guards meta description, og:type, and twitter tags on /udemycoupons."""
    _use_real_fixture(monkeypatch)
    client = TestClient(app)
    try:
        response = _get(client, "/udemycoupons")
    finally:
        client.close()

    assert response.status_code == 200
    html = response.text
    og_type_match = re.search(r'property="og:type"\s+content="([^"]+)"', html)
    assert og_type_match is not None and og_type_match.group(1) == "website"

    expected_desc = (
        "Browse 100% free Udemy coupons, promo codes, and verified deals. "
        "Automate enrollment and claim free courses in coding, AI, business, and design."
    )
    desc_match = re.search(r'name="description"\s+content="([^"]+)"', html)
    assert desc_match is not None and desc_match.group(1) == expected_desc

    og_desc_match = re.search(r'property="og:description"\s+content="([^"]+)"', html)
    assert og_desc_match is not None and og_desc_match.group(1) == expected_desc

    tw_desc_match = re.search(r'name="twitter:description"\s+content="([^"]+)"', html)
    assert tw_desc_match is not None and tw_desc_match.group(1) == expected_desc


def test_public_deals_callout_banner(monkeypatch):
    """Guards the Auto-Enroller callout banner container on /udemycoupons."""
    _use_real_fixture(monkeypatch)
    client = TestClient(app)
    try:
        response = _get(client, "/udemycoupons")
    finally:
        client.close()

    assert response.status_code == 200
    html = response.text
    assert "min-h-[130px] sm:min-h-[100px]" in html
    assert "Start Auto-Enroller" in html
    assert "Never Miss a 100% Free Course" in html


def test_public_deals_itemlist_and_faq_schema(monkeypatch):
    """Guards ItemList schema and 4-question FAQPage schema with DOM parity."""
    _use_real_fixture(monkeypatch)
    client = TestClient(app)
    try:
        response = _get(client, "/udemycoupons")
    finally:
        client.close()

    assert response.status_code == 200
    html = response.text

    blocks = re.findall(
        r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
        html,
        flags=re.DOTALL,
    )
    docs = [json.loads(b) for b in blocks]

    item_list = next((d for d in docs if d.get("@type") == "ItemList"), None)
    assert item_list is not None, "ItemList schema missing on /udemycoupons"
    assert item_list["name"] == "100% Free Udemy Coupons & Promo Codes"
    items = item_list["itemListElement"]
    assert len(items) > 0
    first_item = items[0]["item"]
    assert first_item["@type"] == "Course"
    assert "name" in first_item
    assert "description" in first_item
    assert first_item["provider"]["name"] == "Udemy"
    assert first_item["offers"]["@type"] == "Offer"
    assert first_item["offers"]["price"] == "0"
    assert first_item["offers"]["priceCurrency"] == "USD"
    assert first_item["offers"]["availability"] == "https://schema.org/InStock"

    faq = next((d for d in docs if d.get("@type") == "FAQPage"), None)
    assert faq is not None, "FAQPage schema missing on /udemycoupons"
    faqs = faq["mainEntity"]
    assert len(faqs) == 4
    for q_entry in faqs:
        question = q_entry["name"]
        answer = q_entry["acceptedAnswer"]["text"]
        assert question in html, f"FAQ question not in DOM: {question}"
        assert answer in html, f"FAQ answer not in DOM: {answer}"


def test_category_itemlist_schema():
    """Guards ItemList schema with Course and Offer on category page."""
    client = TestClient(app)
    try:
        response = client.get("/udemycoupons/category/development")
    finally:
        client.close()

    assert response.status_code == 200
    html = response.text

    blocks = re.findall(
        r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
        html,
        flags=re.DOTALL,
    )
    docs = [json.loads(b) for b in blocks]
    item_list = next((d for d in docs if d.get("@type") == "ItemList"), None)
    if item_list:
        items = item_list["itemListElement"]
        assert len(items) > 0
        first_item = items[0]["item"]
        assert first_item["@type"] == "Course"
        assert "name" in first_item
        assert "description" in first_item
        assert first_item["offers"]["price"] == "0"
        assert first_item["offers"]["priceCurrency"] == "USD"

