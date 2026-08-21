import asyncio
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlparse

import pytest

from app.services.http_client import AsyncHTTPClient
from app.services.scraper import CoursonScraper


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
    return CoursonScraper(http_client)


def _get_urls(scraper):
    return [c.args[0] for c in scraper.http.get.call_args_list if c.args]


@pytest.mark.asyncio
async def test_claim_href_is_never_fetched_and_course_data_is_used(scraper):
    homepage = """
    <html>
      <a href="/claim/foo">CLAIM COUPON</a>
      <a href="/coupon/foo">PSPO I</a>
    </html>
    """
    coupon_html = """
    <html>
      <a href="/claim/foo">CLAIM COUPON</a>
      <script>window.courseData={course_id:"pspo1-practice-test",course_title:"PSPO I Practice",coupon_code:"ABC",course_quality_score:None}</script>
    </html>
    """

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        parsed = urlparse(url)
        if parsed.path in ("", "/") and "sitemap" not in url:
            return _resp(homepage)
        if url.endswith("sitemap.xml"):
            return _resp("<urlset></urlset>")
        if parsed.path.startswith("/coupon/"):
            return _resp(coupon_html)
        if parsed.path.startswith("/claim/"):
            return _resp("should never fetch claim")
        return _resp("")

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.playwright_get = AsyncMock(return_value="")

    await scraper.scrape(asyncio.Semaphore(1))

    urls = _get_urls(scraper)
    assert not any("/claim/" in u for u in urls)
    scraper.playwright_get.assert_not_called()
    assert len(scraper.data) >= 1
    assert any("couponCode=" in c.url for c in scraper.data)
    assert any("couponCode=ABC" in c.url for c in scraper.data)
    assert all(c.site == "Courson" for c in scraper.data)


@pytest.mark.asyncio
async def test_missing_coupon_code_skips_without_error(scraper):
    homepage = '<a href="/coupon/foo">Course</a>'
    coupon_html = (
        '<script>window.courseData={course_id:"pspo1-practice-test",'
        'course_title:"PSPO I Practice"}</script>'
    )

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        parsed = urlparse(url)
        if parsed.path in ("", "/") and "sitemap" not in url:
            return _resp(homepage)
        if url.endswith("sitemap.xml"):
            return _resp("<urlset></urlset>")
        if parsed.path.startswith("/coupon/"):
            return _resp(coupon_html)
        return _resp("")

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.playwright_get = AsyncMock(return_value="")

    await scraper.scrape(asyncio.Semaphore(1))

    assert scraper.data == []
    assert scraper.error is None
    scraper.playwright_get.assert_not_called()
    assert not any("/claim/" in u for u in _get_urls(scraper))


@pytest.mark.asyncio
async def test_sitemap_cap_at_most_80_coupon_page_gets(scraper):
    locs = "".join(
        f"<loc>https://courson.xyz/coupon/course-{i}</loc>" for i in range(100)
    )
    sitemap = f"<urlset>{locs}</urlset>"

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        parsed = urlparse(url)
        if parsed.path in ("", "/") and "sitemap" not in url:
            return _resp("<html></html>")
        if url.endswith("sitemap.xml"):
            return _resp(sitemap)
        if parsed.path.startswith("/coupon/"):
            slug = parsed.path.rstrip("/").split("/")[-1]
            return _resp(
                f'<script>window.courseData={{course_id:"{slug}",'
                f'course_title:"{slug}",coupon_code:"CODE{slug}"}}</script>'
            )
        return _resp("")

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.playwright_get = AsyncMock(return_value="")

    await scraper.scrape(asyncio.Semaphore(5))

    coupon_gets = [
        u
        for u in _get_urls(scraper)
        if urlparse(u).path.startswith("/coupon/")
    ]
    assert len(coupon_gets) <= 80
    assert len(scraper.data) <= 80
    scraper.playwright_get.assert_not_called()
