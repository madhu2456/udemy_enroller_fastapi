"""T1 UA-forwarding red-green proof (mock transport only, no network).

Acceptance:
 (1) custom UA=X appears verbatim in outbound wire headers
 (2) no-UA call still sends non-empty default UA (Chrome-like, not python-httpx)
 (3) 403 log equals wire UA
 (4) no signature change
Guards: per-host pin, sec-ch-ua major consistency + forwarding to cloudscraper.
"""
from urllib.parse import urlparse

import httpx
import pytest
from unittest.mock import AsyncMock, patch

from app.services.http_client import AsyncHTTPClient


CUSTOM_UA = "CustomWireUA/9.9 Chrome/142.0.0.0 FORWARD-CHECK"
CHROME_133 = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
CHROME_142 = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"


async def _make_client(is_server=False):
    c = AsyncHTTPClient()
    c._is_server = is_server
    c._apply_human_like_delay = AsyncMock(return_value=None)
    c._is_safe_url = lambda url: True
    return c


class _FakeCookies:
    def get_dict(self):
        return {}


class _FakeResp:
    def __init__(self, status=200):
        self.status_code = status
        self.content = b"ok"
        self.headers = {}
        self.url = "https://example.com/page"
        self.cookies = _FakeCookies()


class _FakeScraper:
    def __init__(self, captured, status=200):
        self.captured = captured
        self.status = status

    def get(self, url, headers=None, timeout=None, allow_redirects=None):
        self.captured.clear()
        self.captured.update(headers or {})
        return _FakeResp(status=self.status)


@pytest.mark.asyncio
async def test_custom_ua_reaches_wire_httpx():
    """Acceptance (1): custom UA appears verbatim on httpx wire (MockTransport)."""
    client = await _make_client(is_server=False)
    try:
        captured = {}

        def handler(request):
            captured.update(dict(request.headers))
            return httpx.Response(200, content=b"ok", request=request)

        await client.client.aclose()
        client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        resp = await client.get(
            "https://example.com/page",
            headers={"User-Agent": CUSTOM_UA},
            raise_for_status=False,
            attempts=1,
        )
        assert resp is not None and resp.status_code == 200
        wire_ua = captured.get("user-agent") or captured.get("User-Agent")
        assert wire_ua == CUSTOM_UA, f"wire UA {wire_ua!r} != custom {CUSTOM_UA!r}"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_custom_ua_reaches_wire_cloudscraper_desktop():
    """Acceptance (1) cloudscraper desktop: explicit UA must reach wire verbatim."""
    for is_server in (False, True):
        client = await _make_client(is_server=is_server)
        try:
            captured = {}
            fake = _FakeScraper(captured, status=200)
            with patch.object(client, "_get_scraper", return_value=fake):
                resp = await client.get(
                    "https://example.com/page",
                    headers={"User-Agent": CUSTOM_UA},
                    use_cloudscraper=True,
                    raise_for_status=False,
                    attempts=1,
                    req_type="document",
                )
                assert resp is not None
                assert captured.get("User-Agent") == CUSTOM_UA, (
                    f"server={is_server} wire UA {captured.get('User-Agent')!r} != {CUSTOM_UA!r}"
                )
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_default_ua_is_chrome_not_python_httpx():
    """Acceptance (2): no-UA call sends non-empty Chrome-like UA, never python-httpx."""
    for is_server in (False, True):
        client = await _make_client(is_server=is_server)
        try:
            headers = client._get_headers("https://example.com/", None, req_type="document")
            ua = headers.get("User-Agent", "")
            assert ua, f"server={is_server} default UA must be non-empty"
            assert "python-httpx" not in ua.lower(), (
                f"server={is_server} default UA must not be python-httpx, got {ua!r}"
            )
            assert ("Mozilla" in ua or "Chrome" in ua or "Safari" in ua or "okhttp" in ua), (
                f"server={is_server} default UA should be browser-like, got {ua!r}"
            )
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_cloudscraper_forwards_computed_ua_desktop():
    """Computed (randomized) UA must be forwarded end-to-end for desktop document."""
    for is_server in (False, True):
        client = await _make_client(is_server=is_server)
        try:
            known_ua = CHROME_133
            known_headers = {
                "User-Agent": known_ua,
                "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="133", "Google Chrome";v="133"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "Referer": "https://example.com/",
            }
            if is_server:
                scraper_headers = client._build_scraper_headers_server(
                    known_headers, {"headers": {}}, False, "document"
                )
            else:
                scraper_headers = client._build_scraper_headers_local(
                    known_headers, {"headers": {}}, False
                )
            assert scraper_headers.get("User-Agent") == known_ua, (
                f"server={is_server} computed UA dropped: {scraper_headers!r}"
            )
            # sec-ch hints must also be forwarded consistently
            assert scraper_headers.get("sec-ch-ua-mobile") == "?0"
            assert "133" in scraper_headers.get("sec-ch-ua", ""), (
                f"server={is_server} sec-ch-ua not forwarded/consistent: {scraper_headers!r}"
            )
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_403_log_matches_wire_ua_cloudscraper():
    """Acceptance (3): 403 log UA must equal wire UA (cloudscraper desktop)."""
    for is_server in (False, True):
        client = await _make_client(is_server=is_server)
        try:
            captured = {}
            fake = _FakeScraper(captured, status=403)
            with patch.object(client, "_get_scraper", return_value=fake):
                with patch("app.services.http_client.logger") as mock_logger:
                    resp = await client.get(
                        "https://example.com/page",
                        use_cloudscraper=True,
                        raise_for_status=False,
                        attempts=1,
                        req_type="document",
                        log_failures=True,
                    )
                    assert resp is not None and resp.status_code == 403
                    wire_ua = captured.get("User-Agent", "")
                    assert wire_ua, f"server={is_server} wire UA must be non-empty, got {captured!r}"
                    assert mock_logger.warning.called, "403 must emit warning log"
                    log_text = str(mock_logger.warning.call_args)
                    assert wire_ua[:60] in log_text, (
                        f"server={is_server} log must contain wire UA {wire_ua[:60]!r}, log={log_text!r}"
                    )
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_403_log_matches_wire_ua_httpx():
    """Acceptance (3) httpx path: 403 log UA must equal wire UA."""
    client = await _make_client(is_server=False)
    try:
        captured = {}

        async def fake_get(url, headers=None, **kw):
            captured.clear()
            captured.update(headers or {})
            return httpx.Response(
                403, content=b"forbidden", request=httpx.Request("GET", url)
            )

        with patch.object(client.client, "get", side_effect=fake_get):
            with patch("app.services.http_client.logger") as mock_logger:
                resp = await client.get(
                    "https://example.com/page",
                    headers={"User-Agent": CUSTOM_UA},
                    raise_for_status=False,
                    attempts=1,
                    log_failures=True,
                )
                assert resp is not None and resp.status_code == 403
                wire_ua = captured.get("User-Agent", "")
                assert wire_ua == CUSTOM_UA
                log_text = str(mock_logger.warning.call_args)
                assert CUSTOM_UA[:60] in log_text, f"log {log_text!r} must contain wire UA"
    finally:
        await client.close()


def test_sec_ch_ua_matches_major_and_forwarded_local():
    """Guard: sec-ch-ua major must match UA major and be forwarded to cloudscraper."""
    import asyncio as _aio

    async def _run():
        client = AsyncHTTPClient()
        client._is_server = False
        client._apply_human_like_delay = AsyncMock(return_value=None)
        try:
            headers = client._get_headers_local(
                urlparse("https://example.com/"), {"User-Agent": CHROME_142}, "document"
            )
            sec = headers.get("sec-ch-ua", "")
            assert "142" in sec, f"sec-ch-ua {sec!r} must contain major 142 for {CHROME_142!r}"
            scraper_headers = client._build_scraper_headers_local(
                headers, {"headers": {"User-Agent": CHROME_142}}, False
            )
            assert scraper_headers.get("User-Agent") == CHROME_142
            assert scraper_headers.get("sec-ch-ua") == sec, (
                f"cloudscraper must forward sec-ch-ua {sec!r}, got {scraper_headers!r}"
            )
        finally:
            await client.close()

    _aio.get_event_loop().run_until_complete(_run()) if False else None
    # run synchronously via new loop to avoid pytest-asyncio dependency here
    _aio.run(_run())


def test_ua_pinned_per_host_for_run():
    """Guard: same host+req_type must pin same UA (no per-request flips)."""
    import asyncio as _aio

    async def _run():
        client = AsyncHTTPClient()
        client._is_server = False
        client._apply_human_like_delay = AsyncMock(return_value=None)
        try:
            ua1 = CHROME_133
            ua2 = CHROME_142
            with patch(
                "app.services.http_client.random.choice", side_effect=[ua1, ua2, ua1, ua2]
            ):
                h1 = client._get_headers_local(urlparse("https://example.com/a"), None, "document")
                h2 = client._get_headers_local(urlparse("https://example.com/b"), None, "document")
                assert h1.get("User-Agent") == h2.get("User-Agent"), (
                    f"pinned UA per host failed: {h1.get('User-Agent')!r} != {h2.get('User-Agent')!r}"
                )
                assert h1.get("User-Agent") == ua1
        finally:
            await client.close()

    _aio.run(_run())


def test_no_signature_change():
    """Acceptance (4): public signatures unchanged."""
    import inspect

    from app.services.http_client import AsyncHTTPClient as C

    assert "url" in inspect.signature(C.get).parameters
    assert "url" in inspect.signature(C.post).parameters
    assert list(inspect.signature(C._build_scraper_headers_local).parameters) == [
        "self",
        "headers",
        "kwargs",
        "is_mobile_request",
    ]
    assert list(inspect.signature(C._build_scraper_headers_server).parameters) == [
        "self",
        "headers",
        "kwargs",
        "is_mobile_request",
        "req_type",
    ]
    assert list(inspect.signature(C._get_headers_local).parameters) == [
        "self",
        "parsed_url",
        "custom_headers",
        "req_type",
    ]
