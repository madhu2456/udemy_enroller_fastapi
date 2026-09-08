import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.http_client import AsyncHTTPClient
from app.services.scraper import FreebiesGlobalScraper

COURSE_URL = "https://www.udemy.com/course/minimalism-guide/?couponCode=FREE100"


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
    return FreebiesGlobalScraper(http)


@pytest.mark.asyncio
async def test_freebiesglobal_direct_card_extraction(scraper):
    listing_html = f"""
    <html>
      <article class="offer_grid">
        <h2>Minimalism Mastery</h2>
        <a class="re_track_btn" href="{COURSE_URL}">Get Deal</a>
      </article>
      <article class="offer_grid">
        <h2>Irrelevant Non-Udemy Deal</h2>
        <a class="re_track_btn" href="https://other.com/deal">Get Deal</a>
      </article>
    </html>
    """

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "tag/udemy-100-off" in url or "dealstore/udemy" in url:
            if "page/2" in url:
                return _resp("", status=404)
            return _resp(listing_html, status=200)
        return _resp("", status=404)

    scraper.http.get = AsyncMock(side_effect=mock_get)

    await scraper.scrape(asyncio.Semaphore(5))

    assert scraper.error is None
    assert len(scraper.data) == 1
    assert scraper.data[0].url == COURSE_URL
    assert scraper.data[0].title == "Minimalism Mastery"
    assert scraper.site_name == "FreebiesGlobal"
    assert scraper.code_name == "fg"


@pytest.mark.asyncio
async def test_freebiesglobal_detail_post_fallback(scraper):
    listing_html = """
    <html>
      <article class="post">
        <h2><a href="https://freebiesglobal.com/ai-for-everyone/">AI for Everyone</a></h2>
      </article>
    </html>
    """
    detail_html = """
    <html>
      <h1>AI for Everyone: Complete Crash Course</h1>
      <a class="btn_offer_block" href="https://www.udemy.com/course/ai-for-everyone/?couponCode=AIFREE">Get Deal</a>
    </html>
    """

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "tag/udemy-100-off" in url:
            if "page/2" in url:
                return _resp("", status=404)
            return _resp(listing_html, status=200)
        if "freebiesglobal.com/ai-for-everyone" in url:
            return _resp(detail_html, status=200)
        return _resp("", status=404)

    scraper.http.get = AsyncMock(side_effect=mock_get)

    await scraper.scrape(asyncio.Semaphore(5))

    assert len(scraper.data) == 1
    assert "couponCode=AIFREE" in scraper.data[0].url
    assert scraper.data[0].title == "AI for Everyone: Complete Crash Course"


@pytest.mark.asyncio
async def test_freebiesglobal_page1_failure_reports_error(scraper):
    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        return _resp("", status=500)

    scraper.http.get = AsyncMock(side_effect=mock_get)

    await scraper.scrape(asyncio.Semaphore(5))

    assert scraper.error == "Failed to fetch listing page 1"
    assert scraper.data == []


@pytest.mark.asyncio
async def test_freebiesglobal_candidate_bounding_and_detail_options(scraper):
    scraper.MAX_COURSES = 5
    articles_html = "".join([
        f'<article class="post"><h2><a href="https://freebiesglobal.com/course-{i}/">Course {i}</a></h2></article>'
        for i in range(30)
    ])
    listing_html = f"<html>{articles_html}</html>"
    detail_html = """<html><h1>Course Title</h1><a class="btn_offer_block" href="https://www.udemy.com/course/course-slug/?couponCode=FREE">Get Deal</a></html>"""

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "tag/udemy-100-off" in url:
            return _resp(listing_html, status=200)
        if "freebiesglobal.com/course-" in url:
            return _resp(detail_html, status=200)
        return _resp("", status=404)

    scraper.http.get = AsyncMock(side_effect=mock_get)
    await scraper.scrape(asyncio.Semaphore(5))

    assert len(scraper.data) <= 5
    detail_calls = [
        call for call in scraper.http.get.call_args_list
        if "freebiesglobal.com/course-" in str(call)
    ]
    assert len(detail_calls) > 0
    for call in detail_calls:
        assert call.kwargs.get("attempts") == 1
        assert call.kwargs.get("timeout") == 8
