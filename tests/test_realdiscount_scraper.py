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
    scraper.http.get = AsyncMock(return_value=None)
    scraper.http.safe_json = AsyncMock(return_value=None)
    scraper.playwright_get = AsyncMock(return_value="<html></html>")

    await scraper.scrape(asyncio.Semaphore(1))

    scraper.playwright_get.assert_not_called()
    assert scraper.error == SKIP_ERROR
    assert scraper.data == []


@pytest.mark.asyncio
async def test_api_missing_items_skips_playwright(scraper):
    scraper.http.get = AsyncMock(return_value=_resp("{}", status=200))
    scraper.http.safe_json = AsyncMock(return_value={"results": []})
    scraper.playwright_get = AsyncMock(return_value="<html></html>")

    await scraper.scrape(asyncio.Semaphore(1))

    scraper.playwright_get.assert_not_called()
    assert scraper.error == SKIP_ERROR
    assert scraper.data == []
    for call in scraper.http.get.call_args_list:
        if call.args and "cdn.real.discount" in call.args[0]:
            assert "timeout" not in call.kwargs or call.kwargs.get("timeout") != 60


@pytest.mark.asyncio
async def test_success_appends_items_skips_sponsored(scraper):
    payload = {
        "items": [
            {
                "store": "Sponsored",
                "name": "Ad Course",
                "url": "https://www.udemy.com/course/ad/",
            },
            {"store": "Udemy", "name": "Real Discount Course", "url": COURSE_URL},
        ]
    }
    scraper.http.get = AsyncMock(return_value=_resp("{}", status=200))
    scraper.http.safe_json = AsyncMock(return_value=payload)
    scraper.playwright_get = AsyncMock()

    await scraper.scrape(asyncio.Semaphore(1))

    scraper.playwright_get.assert_not_called()
    assert scraper.error is None
    assert len(scraper.data) == 1
    assert scraper.data[0].url == COURSE_URL
    assert scraper.data[0].title == "Real Discount Course"
