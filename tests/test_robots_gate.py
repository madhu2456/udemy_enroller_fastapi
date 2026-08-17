"""F252: robots.txt gate — mocked responses only, no network.

RobotsGate must cache robots.txt per host (TTL), honor Disallow for the
scraper's user-agent family, fail OPEN (allow) when robots.txt is
unavailable/5xx/redirect-loops, and the Scraper base class must skip the
listing fetch when a host disallows it.
"""

from unittest.mock import AsyncMock

import httpx
import pytest

from app.services.robots_gate import (
    RobotsGate,
    ROBOTS_MAX_REDIRECTS,
)
from app.services.scraper import Scraper


class FakeHTTPClient:
    def __init__(self):
        self.get = AsyncMock()


def _robots_response(host: str, rules: str) -> httpx.Response:
    return httpx.Response(
        200,
        text=f"User-agent: *\n{rules}",
        request=httpx.Request("GET", f"https://{host}/robots.txt"),
    )


def _page_response(url: str) -> httpx.Response:
    return httpx.Response(200, text="<html>ok</html>", request=httpx.Request("GET", url))


def _gate_with(host: str, robots_rules: str, status: int = 200):
    http = FakeHTTPClient()
    if status != 200:
        http.get.return_value = httpx.Response(
            status, request=httpx.Request("GET", f"https://{host}/robots.txt")
        )
    else:
        http.get.return_value = _robots_response(host, robots_rules)
    return RobotsGate(http), http


class TestRobotsGate:
    @pytest.mark.asyncio
    async def test_allow_when_no_disallow(self):
        gate, http = _gate_with("coupon.example", "Allow: /\n")
        assert await gate.is_allowed("https://coupon.example/courses") is True
        http.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disallow_root_blocks_fetch(self):
        gate, http = _gate_with("coupon.example", "Disallow: /\n")
        assert await gate.is_allowed("https://coupon.example/courses") is False

    @pytest.mark.asyncio
    async def test_path_specific_disallow(self):
        gate, _ = _gate_with(
            "coupon.example", "Disallow: /private/\nAllow: /courses\n"
        )
        assert await gate.is_allowed("https://coupon.example/private/course-1") is False
        assert await gate.is_allowed("https://coupon.example/courses") is True

    @pytest.mark.asyncio
    async def test_user_agent_group_honored(self):
        http = FakeHTTPClient()
        http.get.return_value = httpx.Response(
            200,
            text=(
                "User-agent: SomeOtherBot\nDisallow: /\n\n"
                "User-agent: *\nAllow: /\n"
            ),
            request=httpx.Request("GET", "https://coupon.example/robots.txt"),
        )
        gate = RobotsGate(http)
        # Our Chrome-family UA matches the * group -> allowed.
        assert await gate.is_allowed("https://coupon.example/courses") is True

    @pytest.mark.asyncio
    async def test_per_host_cache_avoids_refetch(self):
        gate, http = _gate_with("coupon.example", "Allow: /\n")
        assert await gate.is_allowed("https://coupon.example/courses") is True
        assert await gate.is_allowed("https://coupon.example/another") is True
        assert http.get.await_count == 1

    @pytest.mark.asyncio
    async def test_cache_ttl_expiry_refetches(self, monkeypatch):
        gate, http = _gate_with("coupon.example", "Allow: /\n")
        monkeypatch.setattr("app.services.robots_gate.ROBOTS_CACHE_TTL_SECONDS", 0)
        assert await gate.is_allowed("https://coupon.example/courses") is True
        assert await gate.is_allowed("https://coupon.example/courses") is True
        assert http.get.await_count == 2

    @pytest.mark.asyncio
    async def test_fail_open_on_500(self):
        gate, _ = _gate_with("coupon.example", "", status=500)
        assert await gate.is_allowed("https://coupon.example/courses") is True

    @pytest.mark.asyncio
    async def test_fail_open_on_404(self):
        gate, _ = _gate_with("coupon.example", "", status=404)
        assert await gate.is_allowed("https://coupon.example/courses") is True

    @pytest.mark.asyncio
    async def test_fail_open_on_transport_error(self):
        http = FakeHTTPClient()
        http.get.side_effect = httpx.ConnectError("boom")
        gate = RobotsGate(http)
        assert await gate.is_allowed("https://coupon.example/courses") is True

    @pytest.mark.asyncio
    async def test_fail_open_on_redirect_loop(self):
        http = FakeHTTPClient()
        http.get.side_effect = httpx.TooManyRedirects(
            "Exceeded max redirects", request=httpx.Request("GET", "https://coupon.example/robots.txt")
        )
        gate = RobotsGate(http)
        assert await gate.is_allowed("https://coupon.example/courses") is True
        # The redirect cap is applied to the robots.txt fetch.
        assert ROBOTS_MAX_REDIRECTS == 3

    @pytest.mark.asyncio
    async def test_fail_open_on_none_response(self):
        http = FakeHTTPClient()
        http.get.return_value = None
        gate = RobotsGate(http)
        assert await gate.is_allowed("https://coupon.example/courses") is True

    @pytest.mark.asyncio
    async def test_invalid_url_without_host_allowed(self):
        gate, _ = _gate_with("coupon.example", "Disallow: /\n")
        assert await gate.is_allowed("not-a-url") is True


class DummyScraper(Scraper):
    @property
    def site_name(self):
        return "Dummy"

    @property
    def code_name(self):
        return "dummy"

    async def scrape(self, detail_semaphore):
        pass


class TestScraperIntegration:
    @pytest.mark.asyncio
    async def test_http_get_skips_fetch_when_disallowed(self):
        http = FakeHTTPClient()
        http.get.side_effect = lambda url, **kw: (
            _robots_response("coupon.example", "Disallow: /\n")
            if url.endswith("robots.txt")
            else _page_response(url)
        )
        scraper = DummyScraper(http)
        result = await scraper._http_get(
            "https://coupon.example/courses", use_cloudscraper=True, timeout=15
        )
        assert result is None
        # Only the robots.txt fetch happened — the listing fetch was skipped.
        assert http.get.await_count == 1

    @pytest.mark.asyncio
    async def test_http_get_passes_through_when_allowed(self):
        http = FakeHTTPClient()
        http.get.side_effect = lambda url, **kw: (
            _robots_response("coupon.example", "Allow: /\n")
            if url.endswith("robots.txt")
            else _page_response(url)
        )
        scraper = DummyScraper(http)
        result = await scraper._http_get(
            "https://coupon.example/courses", use_cloudscraper=True, timeout=15
        )
        assert result is not None
        assert result.status_code == 200
        assert http.get.await_count == 2

    @pytest.mark.asyncio
    async def test_http_get_fail_open_when_robots_unreachable(self):
        http = FakeHTTPClient()

        async def _side_effect(url, **kw):
            if url.endswith("robots.txt"):
                return httpx.Response(
                    503, request=httpx.Request("GET", url)
                )
            return _page_response(url)

        http.get.side_effect = _side_effect
        scraper = DummyScraper(http)
        result = await scraper._http_get(
            "https://coupon.example/courses", use_cloudscraper=True, timeout=15
        )
        assert result is not None
        assert result.status_code == 200
