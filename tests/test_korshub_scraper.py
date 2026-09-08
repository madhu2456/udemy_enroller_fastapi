import asyncio
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlparse

import pytest

from app.services.http_client import AsyncHTTPClient
from app.services.scraper import KorshubScraper

COURSE_URL = "https://www.udemy.com/course/kh-real/?couponCode=KH"
GO_UUID = "550e8400-e29b-41d4-a716-446655440000"


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
    return KorshubScraper(MagicMock(spec=AsyncHTTPClient))


def _get_urls(scraper):
    return [c.args[0] for c in scraper.http.get.call_args_list if c.args]


@pytest.mark.asyncio
async def test_listing_without_udemy_suffix_collects_slug(scraper):
    listing = '<a href="/courses/python-basics">Python Basics</a>'
    detail = f'<html><a href="{COURSE_URL}">enroll</a><title>Python Basics | Korshub</title></html>'

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "/courses/python-basics" in url:
            return _resp(detail)
        if "korshub.com/free-courses" in url or "korshub.com/courses" in url:
            if "page=" in url and not url.endswith("page=0") and "page=1" not in url:
                return _resp("")
            return _resp(listing)
        return _resp("")

    scraper.http.get = AsyncMock(side_effect=mock_get)
    await scraper.scrape(asyncio.Semaphore(1))

    assert any("korshub.com/courses/python-basics" in u for u in _get_urls(scraper))
    assert len(scraper.data) == 1
    assert scraper.data[0].url == COURSE_URL


@pytest.mark.asyncio
async def test_coupon_text_without_udemy_or_go_yields_zero(scraper):
    listing = '<a href="/courses/python-basics">Python Basics</a>'
    detail = """
    <html>
      <title>python-basics | Korshub</title>
      <p>Coupon: SAVE50 use this code on Udemy</p>
    </html>
    """

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "/courses/python-basics" in url:
            return _resp(detail)
        if "korshub.com/free-courses" in url or "korshub.com/courses" in url:
            if "page=" in url and not url.endswith("page=0") and "page=1" not in url:
                return _resp("")
            return _resp(listing)
        return _resp("unexpected")

    scraper.http.get = AsyncMock(side_effect=mock_get)
    await scraper.scrape(asyncio.Semaphore(1))

    assert scraper.data == []
    assert not any("udemy.com/course/python-basics" in u for u in _get_urls(scraper))
    assert not any("udemy.com/course/" in (c.url or "") for c in scraper.data)


@pytest.mark.asyncio
async def test_same_origin_go_hop_kwargs_and_302(scraper):
    listing = '<a href="/courses/go-course">Go Course</a>'
    detail = f'<html><a href="/go/{GO_UUID}">Get course</a><title>Go Course | Korshub</title></html>'

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if f"/go/{GO_UUID}" in url:
            return _resp("", status=302, headers={"location": COURSE_URL})
        if "/courses/go-course" in url:
            return _resp(detail)
        if "korshub.com/free-courses" in url or "korshub.com/courses" in url:
            if "page=" in url and not url.endswith("page=0") and "page=1" not in url:
                return _resp("")
            return _resp(listing)
        return _resp("")

    scraper.http.get = AsyncMock(side_effect=mock_get)
    await scraper.scrape(asyncio.Semaphore(1))

    assert len(scraper.data) == 1
    assert scraper.data[0].url == COURSE_URL
    hop_calls = [c for c in scraper.http.get.call_args_list if c.args and "/go/" in c.args[0]]
    assert hop_calls
    for call in hop_calls:
        parsed = urlparse(call.args[0])
        host = parsed.netloc.lower().split(":")[0]
        assert host in {"korshub.com", "www.korshub.com"}
        assert parsed.path == f"/go/{GO_UUID}"
        assert call.kwargs.get("use_cloudscraper") is True
        assert call.kwargs.get("allow_redirects") is False
        assert call.kwargs.get("follow_redirects") is False
        assert call.kwargs.get("raise_for_status") is False
        assert call.kwargs.get("attempts") == 1


TRK_LOCATION = f"https://trk.udemy.com/{GO_UUID}"


@pytest.mark.asyncio
async def test_go_hop_with_query_strips_query_and_yields_trk(scraper):
    listing = '<a href="/courses/go-course">Go Course</a>'
    detail = (
        f'<html><a href="/go/{GO_UUID}?s=product_page">Get course</a>'
        "<title>Go Course | Korshub</title></html>"
    )

    scraper._resolve_trk_redirect = AsyncMock(return_value=COURSE_URL)

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if f"/go/{GO_UUID}" in url:
            return _resp("", status=302, headers={"location": TRK_LOCATION})
        if "/courses/go-course" in url:
            return _resp(detail)
        if "korshub.com/free-courses" in url or "korshub.com/courses" in url:
            if "page=" in url and not url.endswith("page=0") and "page=1" not in url:
                return _resp("")
            return _resp(listing)
        return _resp("")

    scraper.http.get = AsyncMock(side_effect=mock_get)
    await scraper.scrape(asyncio.Semaphore(1))

    assert len(scraper.data) == 1
    assert scraper.data[0].url == COURSE_URL
    hop_calls = [c for c in scraper.http.get.call_args_list if c.args and "/go/" in c.args[0]]
    assert hop_calls
    for call in hop_calls:
        parsed = urlparse(call.args[0])
        host = parsed.netloc.lower().split(":")[0]
        assert host in {"korshub.com", "www.korshub.com"}
        assert parsed.path == f"/go/{GO_UUID}"
        assert parsed.query == ""
        assert call.args[0] in {f"https://korshub.com/go/{GO_UUID}", f"https://www.korshub.com/go/{GO_UUID}"}
        assert call.kwargs.get("use_cloudscraper") is True
        assert call.kwargs.get("allow_redirects") is False
        assert call.kwargs.get("follow_redirects") is False
        assert call.kwargs.get("raise_for_status") is False
        assert call.kwargs.get("attempts") == 1
        assert call.kwargs.get("timeout") == 15
    scraper._resolve_trk_redirect.assert_awaited()
    trk_arg = scraper._resolve_trk_redirect.await_args.args[0]
    assert trk_arg == TRK_LOCATION
    assert not any(f"/course/{GO_UUID}" in (c.url or "") for c in scraper.data)


APEX_TRK_LOCATION = (
    "https://trk.udemy.com/c/x?u=https://www.udemy.com/course/slug/?couponCode=ABC"
)
EVIL_GO_UUID = "550e8400-e29b-41d4-a716-446655440001"
NOTGO_UUID = "550e8400-e29b-41d4-a716-446655440002"


@pytest.mark.asyncio
async def test_www_to_apex_go_hop_then_trk(scraper):
    listing = (
        '<a href="https://www.korshub.com/courses/go-course">Go Course</a>'
        '<a href="https://www.korshub.com/courses/evil-go">Evil Go</a>'
        '<a href="https://www.korshub.com/courses/not-go">Not Go</a>'
    )
    detail = (
        f'<html><a href="/go/{GO_UUID}?s=product_page">Get course</a>'
        "<title>Go Course | Korshub</title></html>"
    )
    evil_detail = (
        f'<html><a href="/go/{EVIL_GO_UUID}?s=product_page">Get course</a>'
        "<title>Evil Go | Korshub</title></html>"
    )
    notgo_detail = (
        f'<html><a href="/go/{NOTGO_UUID}?s=product_page">Get course</a>'
        "<title>Not Go | Korshub</title></html>"
    )

    scraper._resolve_trk_redirect = AsyncMock(return_value=COURSE_URL)

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if url == f"https://www.korshub.com/go/{GO_UUID}":
            return _resp(
                "",
                status=301,
                headers={"location": f"https://korshub.com/go/{GO_UUID}"},
            )
        if url == f"https://korshub.com/go/{GO_UUID}":
            return _resp("", status=302, headers={"location": APEX_TRK_LOCATION})
        if url == f"https://www.korshub.com/go/{EVIL_GO_UUID}":
            return _resp(
                "",
                status=301,
                headers={"location": f"https://evil.com/go/{EVIL_GO_UUID}"},
            )
        if url == f"https://www.korshub.com/go/{NOTGO_UUID}":
            return _resp(
                "",
                status=301,
                headers={"location": "https://korshub.com/not-go"},
            )
        if url == "https://www.korshub.com/courses/go-course":
            return _resp(detail)
        if url == "https://www.korshub.com/courses/evil-go":
            return _resp(evil_detail)
        if url == "https://www.korshub.com/courses/not-go":
            return _resp(notgo_detail)
        if "korshub.com/free-courses" in url or "korshub.com/courses" in url:
            if "page=" in url and not url.endswith("page=0") and "page=1" not in url:
                return _resp("")
            return _resp(listing)
        return _resp("unexpected")

    scraper.http.get = AsyncMock(side_effect=mock_get)
    await scraper.scrape(asyncio.Semaphore(1))

    assert len(scraper.data) == 1
    assert scraper.data[0].url == COURSE_URL

    hop_calls = [
        c
        for c in scraper.http.get.call_args_list
        if c.args and f"/go/{GO_UUID}" in c.args[0]
    ]
    assert len(hop_calls) == 2
    assert hop_calls[0].args[0] == f"https://www.korshub.com/go/{GO_UUID}"
    assert hop_calls[1].args[0] == f"https://korshub.com/go/{GO_UUID}"
    for call in hop_calls:
        assert call.kwargs.get("use_cloudscraper") is True
        assert call.kwargs.get("allow_redirects") is False
        assert call.kwargs.get("follow_redirects") is False
        assert call.kwargs.get("raise_for_status") is False
        assert call.kwargs.get("attempts") == 1
        assert call.kwargs.get("timeout") == 15

    requested = _get_urls(scraper)
    assert f"https://www.korshub.com/go/{EVIL_GO_UUID}" in requested
    assert f"https://www.korshub.com/go/{NOTGO_UUID}" in requested
    assert not any("evil.com" in u for u in requested)
    assert "https://korshub.com/not-go" not in requested
    all_go_hops = [
        c for c in scraper.http.get.call_args_list if c.args and "/go/" in c.args[0]
    ]
    for call in all_go_hops:
        assert call.kwargs.get("allow_redirects") is False
        assert call.kwargs.get("follow_redirects") is False

    scraper._resolve_trk_redirect.assert_awaited()
    assert scraper._resolve_trk_redirect.await_args.args[0] == APEX_TRK_LOCATION
    assert scraper._resolve_trk_redirect.await_count == 1


@pytest.mark.asyncio
async def test_off_host_go_never_requested(scraper):
    listing = '<a href="/courses/evil-go">Evil Go</a>'
    detail = (
        '<html><a href="https://evil.example/go/abc123">go</a>'
        "<title>Evil Go | Korshub</title></html>"
    )

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "/courses/evil-go" in url:
            return _resp(detail)
        if "korshub.com/free-courses" in url or "korshub.com/courses" in url:
            if "page=" in url and not url.endswith("page=0") and "page=1" not in url:
                return _resp("")
            return _resp(listing)
        return _resp("unexpected")

    scraper.http.get = AsyncMock(side_effect=mock_get)
    await scraper.scrape(asyncio.Semaphore(1))

    urls = _get_urls(scraper)
    assert not any("evil.example" in u for u in urls)
    assert not any("/go/" in u for u in urls)
    assert scraper.data == []


@pytest.mark.asyncio
async def test_korshub_nextjs_flight_unicode_unescape(scraper):
    listing = '<a href="/courses/nextjs-ai-course">NextJS AI Course</a>'
    detail = (
        '<html><script>self.__next_f.push([1,"4a:[\\"$\\",\\"article\\",'
        '{\\"url\\":\\"https://www.udemy.com/course/nextjs-ai/?couponCode=FREE2026\\\\u0026ref=korshub\\"}"]);'
        '</script><title>NextJS AI Course | Korshub</title></html>'
    )

    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "/courses/nextjs-ai-course" in url:
            return _resp(detail)
        if "korshub.com/free-courses" in url:
            if "page=" in url and not url.endswith("page=0") and "page=1" not in url:
                return _resp("")
            return _resp(listing)
        return _resp("")

    scraper.http.get = AsyncMock(side_effect=mock_get)
    await scraper.scrape(asyncio.Semaphore(1))

    assert len(scraper.data) == 1
    assert scraper.data[0].url == "https://www.udemy.com/course/nextjs-ai/?couponCode=FREE2026"
    assert scraper.data[0].title == "NextJS AI Course"



def test_korshub_json_ld_udemy_anchoring(scraper):
    unescaped = '{"url": "https://www.udemy.com/course/python-mastery/?couponCode=FREE"}'
    assert scraper._extract_udemy_url_from_text(unescaped) == "https://www.udemy.com/course/python-mastery/?couponCode=FREE"

    escaped = '{"url": "https:\\/\\/www.udemy.com\\/course\\/python-mastery\\/?couponCode=FREE"}'
    assert scraper._extract_udemy_url_from_text(escaped) == "https://www.udemy.com/course/python-mastery/?couponCode=FREE"

    other_domain = '{"url": "https://korshub.com/course/python-mastery/"}'
    assert scraper._extract_udemy_url_from_text(other_domain) is None

    other_domain_escaped = '{"url": "https:\\/\\/korshub.com\\/course\\/python-mastery\\/"}'
    assert scraper._extract_udemy_url_from_text(other_domain_escaped) is None
