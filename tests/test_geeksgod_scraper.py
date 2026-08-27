import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.http_client import AsyncHTTPClient
from app.services.scraper import GeeksGodScraper

RAW_COURSE_URL = "https://www.udemy.com/course/cyber-sec-prep/?rand=4&ref=geeksgod&couponCode=AUG2026"
CLEAN_COURSE_URL = "https://www.udemy.com/course/cyber-sec-prep/?couponCode=AUG2026"


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
    return GeeksGodScraper(http)


@pytest.mark.asyncio
async def test_geeksgod_listing_and_detail_with_param_cleaning(scraper):
    listing_html = """
    <html>
      <a href="/course/cyber-security-exam-prep">Cyber Security Prep</a>
    </html>
    """
    detail_html = f"""
    <html>
      <h1>Cyber Security Practice Exam</h1>
      <a class="btn btn--primary" href="{RAW_COURSE_URL}">Enroll Now</a>
    </html>
    """

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "page=1" in url:
            return _resp(listing_html, status=200)
        if "page=2" in url:
            return _resp("", status=404)
        if "/course/cyber-security-exam-prep" in url:
            return _resp(detail_html, status=200)
        return _resp("", status=404)

    scraper.http.get = AsyncMock(side_effect=mock_get)

    await scraper.scrape(asyncio.Semaphore(5))

    assert scraper.error is None
    assert len(scraper.data) == 1
    assert scraper.data[0].url == CLEAN_COURSE_URL
    assert scraper.data[0].title == "Cyber Security Practice Exam"
    assert scraper.site_name == "GeeksGod"
    assert scraper.code_name == "gg"


@pytest.mark.asyncio
async def test_geeksgod_page1_failure_reports_error(scraper):
    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        return _resp("", status=500)

    scraper.http.get = AsyncMock(side_effect=mock_get)

    await scraper.scrape(asyncio.Semaphore(5))

    assert scraper.error == "Failed to fetch listing page 1"
    assert scraper.data == []
