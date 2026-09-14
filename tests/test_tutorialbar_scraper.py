import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.http_client import AsyncHTTPClient
from app.services.scraper import TutorialBarScraper

COURSE_URL = "https://www.udemy.com/course/nextjs-crash-course/?couponCode=FREE2026"


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
    return TutorialBarScraper(http)


@pytest.mark.asyncio
async def test_tutorialbar_rsc_flight_payload_extraction(scraper):
    listing_rsc_html = f"""
    <html>
      <script>
        self.__next_f.push([1, '1:[\"$\",\"$L1\",null,{{"title\":\"Next.js Crash Course \\u0026 Masterclass\",\"couponUrl\":\"{COURSE_URL}\",\"is100PercentOff\":true}}]']);
      </script>
    </html>
    """

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "live-coupons" in url:
            if "page=2" in url:
                return _resp("", status=404)
            return _resp(listing_rsc_html, status=200)
        return _resp("", status=404)

    scraper.http.get = AsyncMock(side_effect=mock_get)

    await scraper.scrape(asyncio.Semaphore(5))

    assert scraper.error is None
    assert len(scraper.data) == 1
    assert scraper.data[0].url == COURSE_URL
    assert scraper.data[0].title == "Next.js Crash Course & Masterclass"
    assert scraper.site_name == "TutorialBar"
    assert scraper.code_name == "tb"


@pytest.mark.asyncio
async def test_tutorialbar_dom_and_detail_fallback(scraper):
    listing_html = """
    <html>
      <div class="coupon-card">
        <h3><a href="/course/python-data-science">Python Data Science</a></h3>
        <a class="btn-primary" href="/course/python-data-science">Get Coupon</a>
      </div>
    </html>
    """
    detail_html = """
    <html>
      <h1>Python Data Science Mastery</h1>
      <a class="btn-primary" href="https://www.udemy.com/course/python-data-science/?couponCode=DSFREE">Enroll</a>
    </html>
    """

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "live-coupons" in url:
            if "page=2" in url:
                return _resp("", status=404)
            return _resp(listing_html, status=200)
        if "/course/python-data-science" in url:
            return _resp(detail_html, status=200)
        return _resp("", status=404)

    scraper.http.get = AsyncMock(side_effect=mock_get)

    await scraper.scrape(asyncio.Semaphore(5))

    assert len(scraper.data) == 1
    assert "couponCode=DSFREE" in scraper.data[0].url
    assert scraper.data[0].title == "Python Data Science Mastery"


@pytest.mark.asyncio
async def test_tutorialbar_page1_failure_reports_error(scraper):
    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        return _resp("", status=500)

    scraper.http.get = AsyncMock(side_effect=mock_get)

    await scraper.scrape(asyncio.Semaphore(5))

    assert scraper.error == "Failed to fetch listing page 1"
    assert scraper.data == []


@pytest.mark.asyncio
async def test_tutorialbar_nested_course_rsc_flight_payload(scraper):
    c1_url = "https://www.udemy.com/course/course-one/?couponCode=FREE1"
    c2_url = "https://www.udemy.com/course/course-two/?couponCode=FREE2"
    nested_rsc_html = f"""
    <html>
      <script>
        self.__next_f.push([1, '1:[\"$\",\"$L1\",null,{{"course":{{"title\":\"Course One \\u0026 Intro\",\"couponUrl\":\"{c1_url}\",\"extra\":123}},"course":{{"title\":\"Course Two Advanced\",\"couponUrl\":\"{c2_url}\",\"extra\":456}}}}]']);
      </script>
    </html>
    """

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "live-coupons" in url:
            if "page=" in url:
                return _resp("", status=404)
            return _resp(nested_rsc_html, status=200)
        return _resp("", status=404)

    scraper.http.get = AsyncMock(side_effect=mock_get)
    await scraper.scrape(asyncio.Semaphore(5))

    assert len(scraper.data) == 2
    assert scraper.data[0].title == "Course One & Intro"
    assert scraper.data[0].url == c1_url
    assert scraper.data[1].title == "Course Two Advanced"
    assert scraper.data[1].url == c2_url
    first_get_url = scraper.http.get.call_args_list[0].args[0]
    assert not first_get_url.endswith("/live-coupons/")

