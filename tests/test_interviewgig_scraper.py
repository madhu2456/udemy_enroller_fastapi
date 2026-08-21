import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlparse

import pytest

from app.services.http_client import AsyncHTTPClient
from app.services.scraper import InterviewGigScraper

COURSE_URL = "https://www.udemy.com/course/ig-real/?couponCode=IG"
TRK_URL = "https://trk.udemy.com/4aM7DG"


def _resp(text="", status=200, headers=None, url=""):
    mock = MagicMock()
    mock.status_code = status
    mock.text = text
    mock.content = text.encode("utf-8") if isinstance(text, str) else text
    mock.headers = headers or {}
    mock.url = url
    return mock


def _posts(*hrefs_and_text):
    links = "".join(
        f'<a href="{href}">{text}</a>' for href, text in hrefs_and_text
    )
    return [
        {
            "title": {"rendered": "Bundle Post Title Here"},
            "content": {"rendered": f"<html>{links}</html>"},
        }
    ]


@pytest.fixture
def scraper():
    return InterviewGigScraper(MagicMock(spec=AsyncHTTPClient))


def _api_mock(posts_page1):
    async def mock_get(url, *args, **kwargs):
        if "robots.txt" in url:
            return _resp("", status=404)
        if "wp-json" in url:
            if "page=1" in url:
                return _resp(json.dumps(posts_page1))
            return _resp("[]")
        return _resp("")

    return mock_get


@pytest.mark.asyncio
async def test_semaphore_one_completes_with_direct_course(scraper):
    scraper.http.get = AsyncMock(
        side_effect=_api_mock(_posts((COURSE_URL, "Interview Gig Real Course")))
    )
    await scraper.scrape(asyncio.Semaphore(1))
    assert len(scraper.data) == 1
    assert scraper.data[0].url == COURSE_URL


@pytest.mark.asyncio
async def test_direct_course_skips_trk_http(scraper):
    scraper.http.get = AsyncMock(
        side_effect=_api_mock(_posts((COURSE_URL, "Interview Gig Real Course")))
    )
    scraper._resolve_trk_redirect = AsyncMock()
    await scraper.scrape(asyncio.Semaphore(1))
    scraper._resolve_trk_redirect.assert_not_called()
    udemy_gets = [
        c.args[0]
        for c in scraper.http.get.call_args_list
        if c.args
        and urlparse(c.args[0]).netloc.lower().split(":")[0]
        in {"udemy.com", "www.udemy.com", "trk.udemy.com"}
    ]
    assert udemy_gets == []


@pytest.mark.asyncio
async def test_non_course_udemy_href_never_calls_http_get(scraper):
    scraper.http.get = AsyncMock(
        side_effect=_api_mock(
            _posts(("https://www.udemy.com/user/someone/", "Instructor"))
        )
    )
    scraper._resolve_trk_redirect = AsyncMock()
    await scraper.scrape(asyncio.Semaphore(1))
    scraper._resolve_trk_redirect.assert_not_called()
    assert scraper.data == []
    udemy_gets = [
        c.args[0]
        for c in scraper.http.get.call_args_list
        if c.args
        and urlparse(c.args[0]).netloc.lower().split(":")[0]
        in {"udemy.com", "www.udemy.com", "trk.udemy.com"}
    ]
    assert udemy_gets == []


@pytest.mark.asyncio
async def test_resolve_one_pair_and_helper_not_func(scraper):
    captured = []
    orig = scraper._run_detail_task

    async def spy(sem, func, *args):
        assert func.__name__ == "_resolve_one"
        assert func is not scraper._resolve_trk_redirect
        result = await orig(sem, func, *args)
        captured.append(result)
        return result

    scraper._run_detail_task = spy
    scraper._resolve_trk_redirect = AsyncMock(return_value=COURSE_URL)
    scraper.http.get = AsyncMock(
        side_effect=_api_mock(_posts((TRK_URL, "Interview Gig Tracked Course")))
    )
    await scraper.scrape(asyncio.Semaphore(1))

    assert captured
    for item in captured:
        assert isinstance(item, tuple)
        assert len(item) == 2
    assert len(scraper.data) == 1
    assert scraper.data[0].url == COURSE_URL


@pytest.mark.asyncio
async def test_exception_in_resolve_one_does_not_append(scraper):
    async def boom(_href):
        raise RuntimeError("trk failed")

    scraper._resolve_trk_redirect = AsyncMock(side_effect=boom)
    scraper.http.get = AsyncMock(
        side_effect=_api_mock(_posts((TRK_URL, "Interview Gig Tracked Course")))
    )
    await scraper.scrape(asyncio.Semaphore(1))
    assert scraper.data == []


@pytest.mark.asyncio
async def test_trk_http_cap_is_80(scraper):
    hrefs = [(f"https://trk.udemy.com/{i:08d}", f"Tracked Course Number {i}") for i in range(100)]
    scraper._resolve_trk_redirect = AsyncMock(return_value=COURSE_URL)
    scraper.http.get = AsyncMock(side_effect=_api_mock(_posts(*hrefs)))
    await scraper.scrape(asyncio.Semaphore(1))
    assert scraper._resolve_trk_redirect.await_count == 80
