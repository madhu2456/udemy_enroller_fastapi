"""Unit tests for Wave 2: Scraper velocity and Turnstile fail-fast."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.http_client import (
    TURNSTILE_SIGNATURES,
    AsyncHTTPClient,
    is_turnstile_challenge,
)
from app.services.scraper import CourseFolderScraper


def test_turnstile_signatures_constant():
    """Verify expected Turnstile challenge signatures are defined."""
    assert "challenges.cloudflare.com" in TURNSTILE_SIGNATURES
    assert "cf-turnstile" in TURNSTILE_SIGNATURES
    assert "cf_chl_prog" in TURNSTILE_SIGNATURES
    assert "data-sitekey" in TURNSTILE_SIGNATURES


def test_is_turnstile_challenge_detection():
    """Test Turnstile detection in headers, body text, and clean responses."""
    assert is_turnstile_challenge(None) is False

    # Header indicator
    resp_hdr = httpx.Response(403, headers={"cf-mitigated": "cf-turnstile"})
    assert is_turnstile_challenge(resp_hdr) is True

    # Body indicator
    resp_body = httpx.Response(
        200,
        text="<html><script src='https://challenges.cloudflare.com/turnstile/v0/api.js'></script></html>",
    )
    assert is_turnstile_challenge(resp_body) is True

    # Clean response
    clean_resp = httpx.Response(200, text="<html><body>Hello World</body></html>")
    assert is_turnstile_challenge(clean_resp) is False


@pytest.mark.asyncio
async def test_resolve_redirect_hop_success():
    """Test resolve_redirect_hop extracts Location header on 302 without following redirect."""
    client = AsyncHTTPClient()
    mock_resp = httpx.Response(
        302,
        headers={"Location": "https://www.udemy.com/course/python-mastery/?couponCode=FREE"},
        request=httpx.Request("GET", "https://example.com/out/test"),
    )
    client.client.get = AsyncMock(return_value=mock_resp)

    res = await client.resolve_redirect_hop("https://example.com/out/test")
    assert res == "https://www.udemy.com/course/python-mastery/?couponCode=FREE"
    client.client.get.assert_called_once()
    assert client.client.get.call_args.kwargs["follow_redirects"] is False
    await client.close()


@pytest.mark.asyncio
async def test_resolve_redirect_hop_turnstile_fail_fast():
    """Test resolve_redirect_hop immediately aborts on Turnstile challenge without retry."""
    client = AsyncHTTPClient()
    mock_resp = httpx.Response(
        403,
        text="<div class='cf-turnstile' data-sitekey='abc'></div>",
        request=httpx.Request("GET", "https://example.com/out/test"),
    )
    client.client.get = AsyncMock(return_value=mock_resp)

    with patch("app.services.http_client.logger") as mock_logger:
        res = await client.resolve_redirect_hop("https://example.com/out/test")
        assert res is None
        assert any("Turnstile challenge detected" in str(c) for c in mock_logger.warning.call_args_list)

    await client.close()


@pytest.mark.asyncio
async def test_http_get_resilient_turnstile_abort():
    """Test Scraper._http_get_resilient aborts without CloudScraper retry when Turnstile is detected."""
    mock_http = MagicMock(spec=AsyncHTTPClient)
    turnstile_resp = httpx.Response(
        200,
        text="<div id='cf-turnstile'>challenges.cloudflare.com</div>",
        request=httpx.Request("GET", "https://example.com/item"),
    )
    mock_http.get = AsyncMock(return_value=turnstile_resp)

    scraper = CourseFolderScraper(mock_http)
    res = await scraper._http_get_resilient("https://example.com/item")

    assert res == turnstile_resp
    assert mock_http.get.call_count == 1
    assert mock_http.get.call_args.kwargs.get("use_cloudscraper") is False


@pytest.mark.asyncio
async def test_process_detail_pool_worker_queue():
    """Test continuous worker pool bounds concurrency, tracks progress, and collects non-None results."""
    mock_http = MagicMock(spec=AsyncHTTPClient)
    scraper = CourseFolderScraper(mock_http)
    items = [f"item_{i}" for i in range(10)]
    max_active = 0
    active = 0

    async def _fetch(item):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        if "item_2" in item:
            raise RuntimeError("network failure")
        return (item, f"https://www.udemy.com/course/{item}/?couponCode=FREE")

    results = await scraper._process_detail_pool(items, _fetch, concurrency=3)
    assert len(results) == 9
    assert max_active <= 3
    assert scraper.progress == len(items)


@pytest.mark.asyncio
async def test_coursefolder_parallel_listings():
    """Test CourseFolderScraper fetches paginated listings concurrently with bounded concurrency."""
    mock_http = MagicMock(spec=AsyncHTTPClient)
    scraper = CourseFolderScraper(mock_http)
    scraper.MAX_PAGES = 4

    async def mock_http_get(url, *args, **kwargs):
        mock = MagicMock()
        mock.status_code = 200
        mock.text = """
        <div class="udemycdn">
            <a href="https://coursefolder.net/sample-course">Sample</a>
        </div>
        """
        return mock

    scraper._http_get = AsyncMock(side_effect=mock_http_get)
    await scraper.scrape(asyncio.Semaphore(2))
    assert scraper._http_get.call_count == 4
