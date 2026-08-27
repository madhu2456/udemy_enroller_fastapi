import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.http_client import AsyncHTTPClient
from app.services.scraper import RealDiscountScraper

COURSE_URL = "https://www.udemy.com/course/rd-real/?couponCode=RD"
SKIP_ERROR = "API unreachable; Playwright skipped"


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
    http.safe_json = AsyncMock()
    return RealDiscountScraper(http)


@pytest.mark.asyncio
async def test_api_none_skips_playwright_and_sets_error(scraper):
    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        return None

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.http.safe_json = AsyncMock(return_value=None)
    scraper.playwright_get = AsyncMock(return_value="<html></html>")

    await scraper.scrape(asyncio.Semaphore(1))

    scraper.playwright_get.assert_not_called()
    assert scraper.error == SKIP_ERROR
    assert scraper.data == []


@pytest.mark.asyncio
async def test_api_missing_items_skips_playwright(scraper):
    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        return _resp("{}", status=200)

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.http.safe_json = AsyncMock(return_value={"results": []})
    scraper.playwright_get = AsyncMock(return_value="<html></html>")

    await scraper.scrape(asyncio.Semaphore(1))

    scraper.playwright_get.assert_not_called()
    assert scraper.error == SKIP_ERROR
    assert scraper.data == []


@pytest.mark.asyncio
async def test_success_appends_items_skips_sponsored_ads_and_paid(scraper):
    page1_payload = {
        "items": [
            {
                "store": "Sponsored",
                "name": "Sponsored Course",
                "url": "https://www.udemy.com/course/sponsored/?couponCode=SPON",
            },
            {
                "store": "Udemy",
                "type": "ad",
                "name": "Ad Course",
                "url": "https://www.udemy.com/course/ad/?couponCode=AD",
            },
            {
                "store": "Udemy",
                "sale_price": 9.99,
                "name": "Paid Discount Course",
                "url": "https://www.udemy.com/course/paid/?couponCode=PAID",
            },
            {
                "store": "Udemy",
                "sale_price": 0,
                "name": "Free Course 1",
                "url": COURSE_URL,
            },
        ]
    }

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        return _resp("{}", status=200)

    async def mock_safe_json(resp):
        if not resp:
            return None
        return page1_payload

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.http.safe_json = AsyncMock(side_effect=mock_safe_json)

    await scraper.scrape(asyncio.Semaphore(1))

    assert scraper.error is None
    assert len(scraper.data) == 1
    assert scraper.data[0].url == COURSE_URL
    assert scraper.data[0].title == "Free Course 1"
