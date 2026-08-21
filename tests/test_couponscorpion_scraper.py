import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.http_client import AsyncHTTPClient
from app.services.scraper import CouponScorpionScraper

UDEMY_LOCATION = (
    "https://www.udemy.com/course/specflow-bdd-c-testing-mastery/?couponCode=AUGUSTFREE2026"
)
REST_TITLE = "Specflow BDD: C# Testing Mastery"


def _resp(text="", status=200, headers=None, url=""):
    mock = MagicMock()
    mock.status_code = status
    mock.text = text
    mock.content = text.encode("utf-8") if isinstance(text, str) else text
    mock.headers = headers or {}
    mock.url = url
    return mock


@pytest.fixture
def http_client():
    return MagicMock(spec=AsyncHTTPClient)


@pytest.fixture
def scraper(http_client):
    return CouponScorpionScraper(http_client)


def _get_calls(scraper):
    return [c for c in scraper.http.get.call_args_list if c.args]


def _get_urls(scraper):
    return [c.args[0] for c in _get_calls(scraper)]


@pytest.mark.asyncio
async def test_get_coupon_code_and_out_php_do_not_append(scraper):
    html = """
    <html>
      <a href="/scripts/udemy/out.php?go=1&s=abc">GET COUPON CODE</a>
    </html>
    """

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "wp-json" in url:
            return _resp("not-json")
        if "out.php" in url:
            return _resp("ok", status=200)
        return _resp(html)

    scraper.http.get = AsyncMock(side_effect=mock_get)
    await scraper.scrape(asyncio.Semaphore(1))

    assert scraper.data == []
    assert not any(
        "out.php" in (c.url or "") or "GET COUPON CODE" in (c.title or "")
        for c in scraper.data
    )


@pytest.mark.asyncio
async def test_rest_title_and_302_location_appends_course(scraper):
    rest = [
        {
            "id": 699220,
            "link": "https://couponscorpion.com/specflow-bdd-c-testing-mastery/",
            "title": {"rendered": REST_TITLE},
        }
    ]
    detail = """
    <html>
      <a href="/scripts/udemy/out.php?go=699220&s=f71912b5b1">GET COUPON CODE</a>
    </html>
    """

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "wp-json" in url:
            if "page=1" in url:
                return _resp(json.dumps(rest))
            return _resp("[]")
        if "out.php" in url:
            return _resp("", status=302, headers={"location": UDEMY_LOCATION})
        if "specflow-bdd-c-testing-mastery" in url:
            return _resp(detail)
        return _resp("")

    scraper.http.get = AsyncMock(side_effect=mock_get)
    await scraper.scrape(asyncio.Semaphore(1))

    assert len(scraper.data) == 1
    assert scraper.data[0].title == REST_TITLE
    assert scraper.data[0].title != "GET COUPON CODE"
    assert scraper.data[0].site == "CouponScorpion"
    assert "couponCode=" in scraper.data[0].url
    assert "out.php" not in scraper.data[0].url


@pytest.mark.asyncio
async def test_out_php_http_get_kwargs(scraper):
    rest = [
        {
            "id": 1,
            "link": "https://couponscorpion.com/some-course/",
            "title": {"rendered": REST_TITLE},
        }
    ]
    detail = '<a href="/scripts/udemy/out.php?go=1&s=abc">GET COUPON CODE</a>'

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "wp-json" in url:
            if "page=1" in url:
                return _resp(json.dumps(rest))
            return _resp("[]")
        if "out.php" in url:
            return _resp("", status=302, headers={"location": UDEMY_LOCATION})
        return _resp(detail)

    scraper.http.get = AsyncMock(side_effect=mock_get)
    await scraper.scrape(asyncio.Semaphore(1))

    out_calls = [c for c in _get_calls(scraper) if "out.php" in c.args[0]]
    assert out_calls
    for call in out_calls:
        assert call.kwargs.get("use_cloudscraper") is True
        assert call.kwargs.get("allow_redirects") is False
        assert call.kwargs.get("follow_redirects") is False
        assert call.kwargs.get("raise_for_status") is False
        assert call.kwargs.get("attempts") == 1


@pytest.mark.asyncio
async def test_missing_s_uses_go_only_and_location_not_logged(scraper):
    rest = [
        {
            "id": 42,
            "link": "https://couponscorpion.com/go-only-course/",
            "title": {"rendered": REST_TITLE},
        }
    ]
    detail = '<a href="/scripts/udemy/out.php?go=42">GET COUPON CODE</a>'

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "wp-json" in url:
            if "page=1" in url:
                return _resp(json.dumps(rest))
            return _resp("[]")
        if "out.php" in url:
            return _resp("", status=302, headers={"location": UDEMY_LOCATION})
        return _resp(detail)

    scraper.http.get = AsyncMock(side_effect=mock_get)

    with patch("app.services.scraper.logger") as mock_logger:
        await scraper.scrape(asyncio.Semaphore(1))
        logged = str(mock_logger.mock_calls)
        assert UDEMY_LOCATION not in logged

    out_urls = [u for u in _get_urls(scraper) if "out.php" in u]
    assert out_urls
    for url in out_urls:
        assert "go=42" in url
        assert "s=" not in url
    assert len(scraper.data) == 1
    assert scraper.data[0].title == REST_TITLE


@pytest.mark.asyncio
async def test_hostile_location_does_not_append(scraper):
    rest = [
        {
            "id": 1,
            "link": "https://couponscorpion.com/hostile-course/",
            "title": {"rendered": REST_TITLE},
        }
    ]
    detail = '<a href="/scripts/udemy/out.php?go=1&s=abc">GET COUPON CODE</a>'
    hostile = "https://udemy.com.evil.com/course/x/?couponCode=FREE"

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "wp-json" in url:
            if "page=1" in url:
                return _resp(json.dumps(rest))
            return _resp("[]")
        if "out.php" in url:
            return _resp("", status=302, headers={"location": hostile})
        return _resp(detail)

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.playwright_get = AsyncMock()
    await scraper.scrape(asyncio.Semaphore(1))

    assert scraper.data == []
    scraper.playwright_get.assert_not_called()


@pytest.mark.asyncio
async def test_out_php_403_skips_without_playwright(scraper):
    rest = [
        {
            "id": 1,
            "link": "https://couponscorpion.com/blocked-course/",
            "title": {"rendered": REST_TITLE},
        }
    ]
    detail = '<a href="/scripts/udemy/out.php?go=1&s=abc">GET COUPON CODE</a>'

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "wp-json" in url:
            if "page=1" in url:
                return _resp(json.dumps(rest))
            return _resp("[]")
        if "out.php" in url:
            return _resp("", status=403)
        return _resp(detail)

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.playwright_get = AsyncMock()
    await scraper.scrape(asyncio.Semaphore(1))

    assert scraper.data == []
    scraper.playwright_get.assert_not_called()
