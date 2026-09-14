"""T4-T2 FCS Playwright last-resort — triple-guard proof (mocked, no browser)."""
import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.services import scraper as scraper_mod
from app.services.scraper import FreeCourseSitesScraper
PW_HTML = '<a class="mks_button" href="https://www.udemy.com/course/pw-resort-course/?couponCode=9">Advanced Python Masterclass</a><a class="mks_button" href="https://www.udemy.com/course/pw-resort-course-2/?couponCode=9">Data Science Bootcamp</a>'
SINGLE_HTML = '<a class="mks_button" href="https://www.udemy.com/course/pw-single/?couponCode=9">Single Junk Course</a>'
TRK_HTML = '<a class="mks_button" href="https://trk.udemy.com/abc123/?couponCode=9">Trk Only Course</a>'
CF_HTML = "<html><body>Just a moment... cf-browser-verification</body></html>"
@pytest.fixture
def scraper(monkeypatch):
    monkeypatch.setenv("FCS_PLAYWRIGHT_FALLBACK", "1")
    http = MagicMock(get=AsyncMock(), safe_json=AsyncMock(return_value=[]))
    sc = FreeCourseSitesScraper(http)
    sc.robots_gate.is_allowed = AsyncMock(return_value=True)
    sc._scrape_rest_api = AsyncMock()
    sc._scrape_html_fallback = AsyncMock(return_value=0)  # budget exhausted
    sc.playwright_get = AsyncMock(return_value=PW_HTML)
    sc.circuit_open = True
    sc.consecutive_failures = 5
    sc._cf_403_observed = True
    FreeCourseSitesScraper._last_playwright_ts = 0.0
    yield sc

@pytest.mark.asyncio
async def test_a_called_once_clears_open(scraper):
    await scraper.scrape(asyncio.Semaphore(2))
    scraper.playwright_get.assert_awaited_once()
    url = scraper.playwright_get.await_args[0][0]
    assert url.startswith(FreeCourseSitesScraper.BASE_URL) and FreeCourseSitesScraper.CATEGORY_SOURCES[0]["slug"] in url
    assert len(scraper.data) == 2 and scraper.circuit_open is False and scraper.consecutive_failures == 0
    assert FreeCourseSitesScraper._last_playwright_ts > 0
    src = inspect.getsource(FreeCourseSitesScraper._scrape_playwright_resort)
    assert "100-off-udemy-coupon" not in src and "timeout=40" in src

@pytest.mark.asyncio
async def test_b_not_called_guards(scraper, monkeypatch):
    monkeypatch.setenv("FCS_PLAYWRIGHT_FALLBACK", "0")  # flag OFF
    await scraper.scrape(asyncio.Semaphore(2))
    monkeypatch.setenv("FCS_PLAYWRIGHT_FALLBACK", "1")
    scraper.append_to_list("Advanced Python Masterclass", "https://www.udemy.com/course/keep/")
    await scraper.scrape(asyncio.Semaphore(2))  # data non-empty
    scraper.data = []
    scraper.circuit_open = False
    scraper.consecutive_failures = 5
    scraper._cf_403_observed = False  # CLOSED non-CF despite fails>=5
    await scraper.scrape(asyncio.Semaphore(2))
    with patch.object(scraper_mod, "_is_safe_url", return_value=False):  # SSRF block
        scraper.circuit_open = True
        await scraper.scrape(asyncio.Semaphore(2))
    scraper.robots_gate.is_allowed = AsyncMock(return_value=False)  # robots block
    with patch.object(scraper_mod, "_is_safe_url", return_value=True):
        await scraper.scrape(asyncio.Semaphore(2))
    scraper.playwright_get.assert_not_called()

@pytest.mark.asyncio
async def test_d_blocked_cf_cooldown(scraper):
    scraper.playwright_get = AsyncMock(return_value="")  # BLOCKED_BY_ENV
    await scraper.scrape(asyncio.Semaphore(2))
    assert len(scraper.data) == 0 and scraper.circuit_open is True and scraper.consecutive_failures == 5
    await scraper.scrape(asyncio.Semaphore(2))  # cooldown: no second call
    assert scraper.playwright_get.await_count == 1
    FreeCourseSitesScraper._last_playwright_ts = 0.0
    scraper.playwright_get = AsyncMock(return_value=CF_HTML)  # CF unresolved
    await scraper.scrape(asyncio.Semaphore(2))
    assert len(scraper.data) == 0 and scraper.circuit_open is True

@pytest.mark.asyncio
async def test_e_single_partial_no_clear(scraper):
    scraper.playwright_get = AsyncMock(return_value=SINGLE_HTML)
    scraper._resolve_trk_redirect = AsyncMock(side_effect=AssertionError("no trk resolve on resort"))
    await scraper.scrape(asyncio.Semaphore(2))
    assert len(scraper.data) == 1 and scraper.circuit_open is True and scraper.consecutive_failures == 5

@pytest.mark.asyncio
async def test_f_trk_only_no_resolve_no_clear(scraper):
    scraper.playwright_get = AsyncMock(return_value=TRK_HTML)
    scraper._resolve_trk_redirect = AsyncMock(side_effect=AssertionError("no trk resolve on resort"))
    await scraper.scrape(asyncio.Semaphore(2))
    assert len(scraper.data) == 0 and scraper.circuit_open is True and scraper.consecutive_failures == 5
