import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.http_client import AsyncHTTPClient
from app.services.scraper import OnlineCoursesScraper

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
    challenge_html = '<html><head><title>Attention Required! | Cloudflare</title></head><body><div id="cf-turnstile"></div></body></html>'
    mock_resp = _resp(challenge_html, status=403)
    scraper.http.get = AsyncMock(return_value=mock_resp)

    await scraper.scrape(asyncio.Semaphore(2))

    assert scraper.error == "Blocked by Cloudflare Turnstile WAF"
    assert len(scraper.data) == 0
    assert getattr(scraper, "_cf_403_observed", False) is True
