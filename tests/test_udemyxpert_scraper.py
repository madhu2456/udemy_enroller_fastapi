import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.http_client import AsyncHTTPClient
from app.services.scraper import UdemyXpertScraper

COURSE_URL = "https://www.udemy.com/course/real-xpert/?couponCode=SAVE"
SITEMAP_RE = r"<loc>(https://udemyxpert\.com/courses/[^<]+)</loc>"


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
    return UdemyXpertScraper(MagicMock(spec=AsyncHTTPClient))


@pytest.mark.asyncio
async def test_cdn_then_coupon_href_yields_course(scraper):
    sitemap = (
        "<urlset><url><loc>https://udemyxpert.com/courses/real-xpert</loc></url></urlset>"
    )
    detail = """
    <html>
      <a href="https://cdn.udemyxpert.com/banner.jpg">img</a>
      <a href="https://udemyxpert.com/nav">Home</a>
      <a href="https://www.udemy.com/course/real-xpert/?couponCode=SAVE">Get Coupon</a>
      <title>Real Xpert - Free Udemy Coupon | UdemyXpert</title>
    </html>
    """

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if url.endswith("sitemap.xml"):
            return _resp(sitemap)
        if "/courses/real-xpert" in url:
            return _resp(detail)
        return _resp("")

    scraper.http.get = AsyncMock(side_effect=mock_get)
    await scraper.scrape(asyncio.Semaphore(1))

    assert len(scraper.data) == 1
    assert scraper.data[0].url == COURSE_URL
    assert "couponCode=" in scraper.data[0].url


@pytest.mark.asyncio
async def test_prefers_couponcode_over_plain_course_url(scraper):
    sitemap = (
        "<urlset><url><loc>https://udemyxpert.com/courses/pref</loc></url></urlset>"
    )
    detail = """
    <html>
      <a href="https://www.udemy.com/course/plain-course/">plain</a>
      <a href="https://www.udemy.com/course/pref/?couponCode=YES">Get Coupon</a>
    </html>
    """

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if url.endswith("sitemap.xml"):
            return _resp(sitemap)
        return _resp(detail)

    scraper.http.get = AsyncMock(side_effect=mock_get)
    await scraper.scrape(asyncio.Semaphore(1))

    assert len(scraper.data) == 1
    assert "couponCode=YES" in scraper.data[0].url


def test_sitemap_regex_unmodified():
    src = inspect.getsource(UdemyXpertScraper.scrape)
    assert SITEMAP_RE in src
