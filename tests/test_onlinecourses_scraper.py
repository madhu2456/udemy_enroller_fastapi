import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.http_client import AsyncHTTPClient
from app.services.scraper import SCRAPER_REGISTRY, OnlineCoursesScraper

COURSE_URL = "https://www.udemy.com/course/linux-sec/?couponCode=LINUXFREE"


def _resp(text="", status=200, headers=None, url=""):
    mock = MagicMock()
    mock.status_code = status
    mock.text = text
    mock.content = text.encode("utf-8") if isinstance(text, str) else text
    mock.headers = headers or {}
    mock.url = url
    return mock


@pytest.fixture
def scraper():
    http = MagicMock(spec=AsyncHTTPClient)
    http.get = AsyncMock()
    return OnlineCoursesScraper(http)


@pytest.mark.asyncio
async def test_onlinecourses_feed_and_detail_resolution(scraper):
    feed_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>Linux Security Course</title>
          <link>https://www.onlinecourses.ooo/coupon/linux-security/</link>
        </item>
      </channel>
    </rss>
    """
    detail_html = f"""
    <html>
      <h1>Linux Security & Hardening</h1>
      <a class="btn_offer_block re_track_btn" href="{COURSE_URL}">Get Coupon</a>
    </html>
    """

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "feed" in url:
            return _resp(feed_xml, status=200)
        if "/coupon/linux-security" in url:
            return _resp(detail_html, status=200)
        return _resp("", status=404)

    scraper.http.get = AsyncMock(side_effect=mock_get)

    await scraper.scrape(asyncio.Semaphore(5))

    assert scraper.error is None
    assert len(scraper.data) == 1
    assert scraper.data[0].url == COURSE_URL
    assert scraper.data[0].title == "Linux Security & Hardening"
    assert scraper.site_name == "OnlineCourses.ooo"
    assert scraper.code_name == "oc"


@pytest.mark.asyncio
async def test_onlinecourses_listing_pagination_fallback(scraper):
    listing_html = """
    <html>
      <article>
        <h2><a href="https://www.onlinecourses.ooo/coupon/python-mastery/">Python Mastery</a></h2>
      </article>
    </html>
    """
    detail_html = """
    <html>
      <h1>Python Mastery Bootcamp</h1>
      <a class="re_track_btn" href="https://www.udemy.com/course/python-bootcamp/?couponCode=PYFREE">Redeem</a>
    </html>
    """

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "feed" in url:
            return _resp("", status=500)
        if url == "https://www.onlinecourses.ooo/":
            return _resp(listing_html, status=200)
        if "/coupon/python-mastery" in url:
            return _resp(detail_html, status=200)
        return _resp("", status=404)

    scraper.http.get = AsyncMock(side_effect=mock_get)

    await scraper.scrape(asyncio.Semaphore(5))

    assert len(scraper.data) == 1
    assert "couponCode=PYFREE" in scraper.data[0].url


@pytest.mark.asyncio
async def test_onlinecourses_turnstile_fails_fast_with_error(scraper):
    # Live unique=0 is origin-wide Cloudflare Turnstile WAF, not a selector miss.
    challenge_html = '<html><head><title>Attention Required! | Cloudflare</title></head><body><div id="cf-turnstile"></div></body></html>'
    mock_resp = _resp(challenge_html, status=403)
    fetched: list[str] = []

    async def record_get(url, *args, **kwargs):
        fetched.append(str(url))
        return mock_resp

    scraper.http.get = AsyncMock(side_effect=record_get)

    await scraper.scrape(asyncio.Semaphore(2))

    assert scraper.error == "Blocked by Cloudflare Turnstile WAF"
    assert scraper.data == []
    assert getattr(scraper, "_cf_403_observed", False) is True
    # RobotsGate may still GET /robots.txt (fail-open); no /coupon/ or /page/ hops.
    assert not any("/coupon/" in url or "/page/" in url for url in fetched)
    assert not any(url.rstrip("/").endswith("onlinecourses.ooo") for url in fetched)


def test_onlinecourses_stays_registered_discudemy_does_not():
    assert "OnlineCourses.ooo" in SCRAPER_REGISTRY
    assert SCRAPER_REGISTRY["OnlineCourses.ooo"] is OnlineCoursesScraper
    assert "Discudemy" not in SCRAPER_REGISTRY
    doc = OnlineCoursesScraper.__doc__ or ""
    assert "Blocked by Cloudflare Turnstile WAF" in doc
    assert "unique=0" in doc
    assert "Playwright" in doc


@pytest.mark.asyncio
async def test_onlinecourses_listing_turnstile_after_failed_feed_abort_closes(scraper):
    """Empty/non-200 feed plus listing 403 is WAF abort-close, not a selector miss."""
    challenge_html = (
        '<html><head><title>Just a moment...</title></head>'
        '<body><div id="cf-turnstile"></div></body></html>'
    )
    fetched: list[str] = []

    async def record_get(url, *args, **kwargs):
        fetched.append(str(url))
        if "robots.txt" in url:
            return _resp("", status=404)
        if "/feed" in url:
            return _resp("", status=500)
        return _resp(challenge_html, status=403)

    scraper.http.get = AsyncMock(side_effect=record_get)

    await scraper.scrape(asyncio.Semaphore(2))

    assert scraper.error == "Blocked by Cloudflare Turnstile WAF"
    assert scraper.data == []
    assert getattr(scraper, "_cf_403_observed", False) is True
    assert not any("/coupon/" in url for url in fetched)
    assert any(url.rstrip("/") == "https://www.onlinecourses.ooo" or url.endswith("onlinecourses.ooo/") for url in fetched)


@pytest.mark.asyncio
async def test_onlinecourses_plain_403_without_cf_body_still_abort_closes(scraper):
    fetched: list[str] = []

    async def record_get(url, *args, **kwargs):
        fetched.append(str(url))
        return _resp("forbidden", status=403)

    scraper.http.get = AsyncMock(side_effect=record_get)

    await scraper.scrape(asyncio.Semaphore(2))

    assert scraper.error == "Blocked by Cloudflare Turnstile WAF"
    assert scraper.data == []
    assert getattr(scraper, "_cf_403_observed", False) is True
    assert not any("/coupon/" in url or "/page/" in url for url in fetched)
