import asyncio
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.http_client import AsyncHTTPClient
from app.services.scraper import DiscudemyScraper


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
    return DiscudemyScraper(http_client)


def _get_urls(scraper):
    urls = []
    for call in scraper.http.get.call_args_list:
        if call.args:
            urls.append(call.args[0])
    return urls


@pytest.mark.asyncio
async def test_couponami_card_listing_does_not_fetch_go(scraper):
    listing = """
    <html>
      <a class="couponami-card" href="https://www.couponami.com/development/some-course">Card</a>
      <a href="https://www.couponami.com/go/some-course">Go</a>
    </html>
    """

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if url.rstrip("/").endswith("/all") or "/all/" in url:
            if url.rstrip("/").endswith("/all"):
                return _resp(listing)
            return _resp("")
        return _resp("unexpected")

    scraper.http.get = AsyncMock(side_effect=mock_get)

    with patch("app.services.scraper.CouponamiScraper") as mock_ca:
        await scraper.scrape(asyncio.Semaphore(1))
        mock_ca.assert_not_called()

    urls = _get_urls(scraper)
    assert not any("couponami.com/go/" in u for u in urls)
    assert scraper.data == []


@pytest.mark.asyncio
async def test_native_detail_couponcode_yields_discudemy_course(scraper):
    listing = (
        '<a href="https://www.discudemy.com/python-for-beginners">Python for Beginners</a>'
    )
    detail = (
        '<html><a href="https://www.udemy.com/course/python-for-beginners/'
        '?couponCode=SAVE123">enroll</a></html>'
    )

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if url.rstrip("/").endswith("/all"):
            return _resp(listing)
        if "/all/" in url:
            return _resp("")
        if "discudemy.com/python-for-beginners" in url:
            return _resp(detail)
        return _resp("")

    scraper.http.get = AsyncMock(side_effect=mock_get)
    await scraper.scrape(asyncio.Semaphore(1))

    assert len(scraper.data) >= 1
    assert all(c.site == "Discudemy" for c in scraper.data)
    assert any("couponCode=" in c.url for c in scraper.data)


def test_is_native_detail_rejects_chrome_keeps_real_slug(scraper):
    assert scraper._is_native_detail(
        "https://www.discudemy.com/ai-foundation-introduction-to-mcp"
    )
    assert not scraper._is_native_detail(
        "https://www.discudemy.com/apple-touch-icon.png"
    )
    assert not scraper._is_native_detail(
        "https://www.discudemy.com/favicon-32x32.png"
    )
    assert not scraper._is_native_detail("https://www.discudemy.com/manifest.json")
    assert not scraper._is_native_detail("https://www.discudemy.com/search")
    assert not scraper._is_native_detail("https://www.discudemy.com/contact")
    assert not scraper._is_native_detail("https://www.discudemy.com/login")
    assert not scraper._is_native_detail("https://www.discudemy.com/register")


@pytest.mark.asyncio
async def test_listing_chrome_hrefs_are_not_fetched(scraper):
    listing = """
    <html>
      <a href="/apple-touch-icon.png">icon</a>
      <a href="/favicon-32x32.png">fav</a>
      <a href="/manifest.json">manifest</a>
      <a href="/search">search</a>
      <a href="/contact">contact</a>
      <a href="https://www.discudemy.com/ai-foundation-introduction-to-mcp">MCP</a>
    </html>
    """
    detail = (
        '<html><a href="https://www.udemy.com/course/ai-foundation-introduction-to-mcp/'
        '?couponCode=MCP123">enroll</a></html>'
    )

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if url.rstrip("/").endswith("/all"):
            return _resp(listing)
        if "/all/" in url:
            return _resp("")
        if "discudemy.com/ai-foundation-introduction-to-mcp" in url:
            return _resp(detail)
        return _resp("unexpected")

    scraper.http.get = AsyncMock(side_effect=mock_get)
    await scraper.scrape(asyncio.Semaphore(1))

    urls = _get_urls(scraper)
    assert any("ai-foundation-introduction-to-mcp" in u for u in urls)
    assert not any("apple-touch-icon" in u for u in urls)
    assert not any("favicon" in u for u in urls)
    assert not any("manifest.json" in u for u in urls)
    assert not any(u.rstrip("/").endswith("/search") for u in urls)
    assert not any(u.rstrip("/").endswith("/contact") for u in urls)
    assert len(scraper.data) >= 1
    assert any("couponCode=" in c.url for c in scraper.data)


@pytest.mark.asyncio
async def test_native_detail_only_go_skips_without_couponami_get(scraper):
    listing = '<a href="https://www.discudemy.com/native-slug">Native Course</a>'
    detail = '<html><a href="https://www.couponami.com/go/native-slug">go</a></html>'

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if url.rstrip("/").endswith("/all"):
            return _resp(listing)
        if "/all/" in url:
            return _resp("")
        if "couponami.com" in url:
            return _resp("should never fetch couponami")
        if "discudemy.com/native-slug" in url:
            return _resp(detail)
        return _resp("")

    scraper.http.get = AsyncMock(side_effect=mock_get)
    with patch("app.services.scraper.CouponamiScraper") as mock_ca:
        await scraper.scrape(asyncio.Semaphore(1))
        mock_ca.assert_not_called()

    urls = _get_urls(scraper)
    assert not any("couponami.com" in u for u in urls)
    assert scraper.data == []


@pytest.mark.asyncio
async def test_many_go_only_details_never_get_couponami(scraper):
    cards = "".join(
        f'<a href="https://www.discudemy.com/slug-{i}">Course {i}</a>'
        for i in range(50)
    )

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if url.rstrip("/").endswith("/all"):
            return _resp(f"<html>{cards}</html>")
        if "/all/" in url:
            return _resp("")
        if "couponami.com" in url:
            return _resp("should never fetch couponami")
        if "discudemy.com/slug-" in url:
            slug = url.rstrip("/").split("/")[-1]
            return _resp(
                f'<a href="https://www.couponami.com/go/{slug}">go</a>'
            )
        return _resp("")

    scraper.http.get = AsyncMock(side_effect=mock_get)
    with patch("app.services.scraper.CouponamiScraper") as mock_ca:
        await scraper.scrape(asyncio.Semaphore(5))
        mock_ca.assert_not_called()

    urls = _get_urls(scraper)
    assert not any("couponami.com" in u for u in urls)
    assert scraper.data == []


@pytest.mark.asyncio
async def test_listing_http_get_kwargs_timeout_and_cloudscraper(scraper):
    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "discudemy.com/all" in url:
            return _resp("")
        return _resp("")

    scraper.http.get = AsyncMock(side_effect=mock_get)
    await scraper.scrape(asyncio.Semaphore(1))

    listing_calls = [
        c
        for c in scraper.http.get.call_args_list
        if c.args and "discudemy.com/all" in c.args[0]
    ]
    assert listing_calls
    for call in listing_calls:
        assert call.kwargs.get("timeout") == 15
        assert call.kwargs.get("use_cloudscraper") is True


@pytest.mark.asyncio
async def test_logs_candidate_and_found_counts(scraper):
    listing = (
        '<a href="https://www.discudemy.com/python-for-beginners">Python for Beginners</a>'
    )
    detail = (
        '<html><a href="https://www.udemy.com/course/python-for-beginners/'
        '?couponCode=SAVE123">enroll</a></html>'
    )

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if url.rstrip("/").endswith("/all"):
            return _resp(listing)
        if "/all/" in url:
            return _resp("")
        if "discudemy.com/python-for-beginners" in url:
            return _resp(detail)
        return _resp("")

    scraper.http.get = AsyncMock(side_effect=mock_get)
    with patch("app.services.scraper.logger") as mock_logger:
        await scraper.scrape(asyncio.Semaphore(1))
        logged = " ".join(str(c) for c in mock_logger.info.call_args_list)
    assert "native candidates" in logged
    assert "unique Udemy courses" in logged
    assert re.search(r"\b\d+\b", logged)
