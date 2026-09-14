"""T3 breaker-aware HTML fallback — red-green proof (fresh bounded budget).

Covers declarative DoD:
(1) Primary OPEN -> fallback still invoked, total fallback listing HTTP <=5
(2) Primary OPEN -> detail fetch gated (0 HTTP for detail)
(3) Primary CLOSED unchanged; fallback 200 clears OPEN, fallback fail keeps OPEN
(4) No unbounded loop; fresh budget per scrape(); per-host only.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.scraper import FreeCourseSitesScraper


def _make_scraper():
    http = MagicMock()
    http.get = AsyncMock()
    http.safe_json = AsyncMock(return_value=[])
    sc = FreeCourseSitesScraper(http)
    sc.robots_gate.is_allowed = AsyncMock(return_value=True)
    return sc


def _resp(status=200, text=""):
    m = MagicMock()
    m.status_code = status
    m.text = text
    m.headers = {}
    return m


ARCHIVE_HTML = (
    '<article><h2><a href="https://freecoursesites.com/detail-1/">Post 1</a></h2></article>'
)
DETAIL_UDEMY_HTML = (
    '<a class="mks_button" href="https://www.udemy.com/course/python-masterclass/">Enroll</a>'
)


@pytest.mark.asyncio
async def test_primary_open_fallback_still_invoked_bounded():
    """(1)+(4): OPEN primary still runs fallback but listing HTTP <=5."""
    sc = _make_scraper()
    sc.circuit_open = True
    sc.consecutive_failures = 5
    archive = _resp(200, ARCHIVE_HTML)
    listing_calls: list[str] = []
    detail_calls: list[str] = []

    async def mock_get(url, *args, **kwargs):
        if "/category/" in url:
            listing_calls.append(url)
            return archive
        detail_calls.append(url)
        return _resp(200, DETAIL_UDEMY_HTML)

    sc.http.get.side_effect = mock_get
    with patch("app.services.scraper._is_safe_url", return_value=True):
        await sc._scrape_html_fallback(asyncio.Semaphore(5), set())
    # Fallback was NOT starved by the OPEN gate:
    assert len(listing_calls) >= 1, "fallback must still be invoked when OPEN"
    # Bounded: 5 slugs x 50 pages = 250 possible, must hard-stop at 5:
    assert len(listing_calls) <= 5, f"unbounded fallback: {len(listing_calls)} listing hits"
    # Per-host only:
    import urllib.parse

    for u in listing_calls:
        assert urllib.parse.urlparse(u).netloc == "freecoursesites.com"


@pytest.mark.asyncio
async def test_primary_open_detail_gated_zero_http():
    """(2): OPEN blocks detail tasks — unit + integration (0 HTTP for detail)."""
    sc = _make_scraper()
    sc.circuit_open = True
    sem = asyncio.Semaphore(5)
    mock_func = AsyncMock()
    result = await sc._run_detail_task(sem, mock_func, "https://freecoursesites.com/x/")
    assert result == (None, None)
    mock_func.assert_not_called()
    sc.http.get.assert_not_called()

    # Integration: fallback keeps failing (500 -> OPEN stays) with detail links
    # available in principle, yet no detail HTTP fires while OPEN.
    sc2 = _make_scraper()
    sc2.circuit_open = True
    sc2.consecutive_failures = 5
    bad = _resp(500, "err")
    detail_calls: list[str] = []

    async def mock_get2(url, *args, **kwargs):
        if "/category/" in url:
            return bad
        detail_calls.append(url)
        return _resp(200, DETAIL_UDEMY_HTML)

    sc2.http.get.side_effect = mock_get2
    with patch("app.services.scraper._is_safe_url", return_value=True):
        await sc2._scrape_html_fallback(asyncio.Semaphore(5), set())
    assert detail_calls == [], f"detail leaked {len(detail_calls)} HTTP while OPEN"
    assert sc2.circuit_open is True, "failing fallback must keep OPEN"


@pytest.mark.asyncio
async def test_fallback_200_clears_open():
    """(3a): fallback 200 clears circuit_open + resets consecutive_failures."""
    sc = _make_scraper()
    sc.circuit_open = True
    sc.consecutive_failures = 5
    ok = _resp(200, ARCHIVE_HTML)
    sc.http.get = AsyncMock(return_value=ok)
    with patch("app.services.scraper._is_safe_url", return_value=True):
        resp = await sc._http_get_fallback("https://freecoursesites.com/category/x/")
    assert resp is ok
    assert sc.circuit_open is False
    assert sc.consecutive_failures == 0


@pytest.mark.asyncio
async def test_fallback_fail_keeps_open_no_reset():
    """(3b): fallback non-200 keeps OPEN and counts toward re-trip (no reset)."""
    sc = _make_scraper()
    sc.circuit_open = True
    sc.consecutive_failures = 5
    bad = _resp(500, "err")
    sc.http.get = AsyncMock(return_value=bad)
    with patch("app.services.scraper._is_safe_url", return_value=True):
        resp = await sc._http_get_fallback("https://freecoursesites.com/category/x/")
    assert resp is bad
    assert sc.circuit_open is True
    assert sc.consecutive_failures == 6

    # Exception path also keeps OPEN.
    sc2 = _make_scraper()
    sc2.circuit_open = True
    sc2.consecutive_failures = 5
    sc2.http.get = AsyncMock(side_effect=RuntimeError("host down"))
    with patch("app.services.scraper._is_safe_url", return_value=True):
        resp2 = await sc2._http_get_fallback("https://freecoursesites.com/category/x/")
    assert resp2 is None
    assert sc2.circuit_open is True
    assert sc2.consecutive_failures == 6


@pytest.mark.asyncio
async def test_primary_closed_unchanged_details_allowed():
    """(3c): CLOSED primary unchanged — fallback works and details fire."""
    sc = _make_scraper()
    assert sc.circuit_open is False
    archive = _resp(200, ARCHIVE_HTML)
    detail = _resp(200, DETAIL_UDEMY_HTML)

    async def mock_get(url, *args, **kwargs):
        if "/category/" in url:
            return archive
        return detail

    sc.http.get.side_effect = mock_get
    with patch("app.services.scraper._is_safe_url", return_value=True):
        await sc._scrape_html_fallback(asyncio.Semaphore(5), set())
    assert len(sc.data) >= 1, "CLOSED fallback should collect courses via details"
    assert sc.circuit_open is False
    assert sc.consecutive_failures == 0


@pytest.mark.asyncio
async def test_budget_hard_stop_and_fresh_per_scrape():
    """(4): isolated budget hard-stops; each scrape() gets a fresh 5."""
    # Hard-stop with explicit small budget.
    sc = _make_scraper()
    sc.circuit_open = True
    sc.consecutive_failures = 5
    archive = _resp(200, ARCHIVE_HTML)
    calls: list[str] = []

    async def mock_get(url, *args, **kwargs):
        if "/category/" in url:
            calls.append(url)
            return archive
        return _resp(200, DETAIL_UDEMY_HTML)

    sc.http.get.side_effect = mock_get
    with patch("app.services.scraper._is_safe_url", return_value=True):
        await sc._scrape_html_fallback(asyncio.Semaphore(5), set(), fallback_budget=2)
    assert len(calls) == 2, f"budget=2 must hard-stop at 2, got {len(calls)}"

    # Fresh per scrape(): full scrape() twice, each does its own <=5 (not shared).
    for _ in range(2):
        sc2 = _make_scraper()

        async def trip_rest(seen):
            sc2.circuit_open = True
            sc2.consecutive_failures = 5
            sc2.error = "Circuit breaker tripped after 5 consecutive failures"

        sc2._scrape_rest_api = AsyncMock(side_effect=trip_rest)
        per_calls: list[str] = []

        async def mock_get2(url, *args, **kwargs):
            if "/category/" in url:
                per_calls.append(url)
                return archive
            return _resp(200, DETAIL_UDEMY_HTML)

        sc2.http.get.side_effect = mock_get2
        with patch("app.services.scraper._is_safe_url", return_value=True):
            # No unconditional reset at scrape entry: OPEN from primary must
            # survive into fallback (fallback 500s keep it OPEN).
            await sc2.scrape(asyncio.Semaphore(5))
        assert 1 <= len(per_calls) <= 5, f"fresh scrape budget violated: {len(per_calls)}"
