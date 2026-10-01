"""Unit tests for mobile User-Agent sanitization and Cloudflare Turnstile 403 remediation.

Validates:
1. req_type="mobile" isolates mobile UA pool and selects OkHttp/UdemyAndroid UA.
2. Mobile / OkHttp requests strictly omit Chromium Client Hints and W3C Fetch Metadata.
3. Desktop API / XHR requests preserve Client Hints, CORS fetch metadata, and XMLHttpRequest header.
4. Custom User-Agent sovereignty (verbatim forwarding, no leak into _ua_pins).
5. CloudScraper builders strip hints for mobile requests.
6. Local scraper builder preserves desktop hints when is_mobile_request=False.
7. Safe mobile UA fallback prevents IndexError on empty pools.
8. free_checkout dispatches with "X-Requested-With": "com.udemy.android".
"""
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse

import pytest

from app.services.course import Course
from app.services.http_client import AsyncHTTPClient
from app.services.udemy_client import UdemyClient


class TestMobileHeaders:
    """Test suite for mobile header generation, sanitization, and protocol compliance."""

    def test_mobile_req_type_selects_okhttp_ua(self):
        """Verify req_type='mobile' selects authentic OkHttp/UdemyAndroid UA and pins it."""
        client_local = AsyncHTTPClient()
        client_local._is_server = False
        parsed = urlparse("https://www.udemy.com/api-2.0/course-landing-components/")

        h_local = client_local._get_headers_local(parsed, None, "mobile")
        ua_local = h_local.get("User-Agent", "")
        assert "UdemyAndroid" in ua_local or "okhttp" in ua_local
        assert "Chrome/" not in ua_local
        pin_key = f"{parsed.netloc}::mobile"
        assert client_local._ua_pins.get(pin_key) == ua_local

        # Pinning consistency: second call returns identical UA
        h_local_2 = client_local._get_headers_local(parsed, None, "mobile")
        assert h_local_2.get("User-Agent") == ua_local

        client_server = AsyncHTTPClient()
        client_server._is_server = True
        h_server = client_server._get_headers_server(parsed, None, "mobile")
        ua_server = h_server.get("User-Agent", "")
        assert "UdemyAndroid" in ua_server or "okhttp" in ua_server
        assert "Chrome/" not in ua_server
        assert client_server._ua_pins.get(pin_key) == ua_server

        h_server_2 = client_server._get_headers_server(parsed, None, "mobile")
        assert h_server_2.get("User-Agent") == ua_server

    def test_mobile_headers_omit_client_hints_and_fetch_metadata(self):
        """Assert req_type='mobile' strictly omits sec-ch-ua* and Sec-Fetch-* headers."""
        client_local = AsyncHTTPClient()
        client_local._is_server = False
        parsed = urlparse("https://www.udemy.com/api-2.0/course-landing-components/")

        h_local = client_local._get_headers_local(parsed, None, "mobile")
        for hint in ("sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform"):
            assert hint not in h_local
        for fetch in ("Sec-Fetch-Site", "Sec-Fetch-Mode", "Sec-Fetch-Dest", "Sec-Fetch-User"):
            assert fetch not in h_local
        assert h_local.get("X-Requested-With") == "com.udemy.android"
        assert h_local.get("x-checkout-is-mobile-app") == "false"
        assert h_local.get("Accept-Language") == "en-US"

        client_server = AsyncHTTPClient()
        client_server._is_server = True
        h_server = client_server._get_headers_server(parsed, None, "mobile")
        for hint in ("sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform"):
            assert hint not in h_server
        for fetch in ("Sec-Fetch-Site", "Sec-Fetch-Mode", "Sec-Fetch-Dest", "Sec-Fetch-User"):
            assert fetch not in h_server
        assert h_server.get("X-Requested-With") == "com.udemy.android"
        assert h_server.get("x-checkout-is-mobile-app") == "false"
        assert h_server.get("x-udemy-client-language") == "en"
        assert h_server.get("Accept-Language") == "en-US"

    def test_desktop_api_preserves_client_hints_and_fetch_metadata(self):
        """Assert req_type='api' with desktop Chrome preserves Client Hints, Sec-Fetch, and XMLHttpRequest, while Firefox omits Client Hints."""
        client = AsyncHTTPClient()
        client._is_server = True
        parsed = urlparse("https://www.udemy.com/api-2.0/contexts/me/")
        desktop_chrome = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
        )

        h = client._get_headers_server(parsed, {"User-Agent": desktop_chrome}, "api")
        assert "sec-ch-ua" in h
        assert h.get("sec-ch-ua-mobile") == "?0"
        assert h.get("Sec-Fetch-Site") == "same-origin"
        assert h.get("Sec-Fetch-Mode") == "cors"
        assert h.get("Sec-Fetch-Dest") == "empty"
        assert h.get("X-Requested-With") == "XMLHttpRequest"
        assert h.get("Origin") == "https://www.udemy.com"

        # Also verify Firefox explicitly omits Client Hints while preserving API headers
        desktop_firefox = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0"
        h_ff = client._get_headers_server(parsed, {"User-Agent": desktop_firefox}, "api")
        assert "sec-ch-ua" not in h_ff
        assert h_ff.get("X-Requested-With") == "XMLHttpRequest"
        assert h_ff.get("Origin") == "https://www.udemy.com"

    def test_custom_ua_sovereignty(self):
        """Assert custom UA is passed verbatim, triggers is_okhttp when applicable, and is not pinned."""
        client = AsyncHTTPClient()
        client._is_server = True
        parsed = urlparse("https://www.udemy.com/test-endpoint")
        custom_ua = "okhttp/4.12.0 UdemyAndroid 9.116.0(2078) (phone)"

        h = client._get_headers_server(parsed, {"User-Agent": custom_ua}, "document")
        assert h.get("User-Agent") == custom_ua
        # is_okhttp is derived from custom_ua, so sec-ch-ua* must be omitted
        assert "sec-ch-ua" not in h
        assert "sec-ch-ua-mobile" not in h

        # Custom UA must NOT be pinned in _ua_pins
        pin_key = f"{parsed.netloc}::document"
        assert pin_key not in client._ua_pins

    def test_scraper_headers_strip_hints_for_mobile(self):
        """Assert CloudScraper builders strip Chromium hints and Fetch metadata for mobile requests."""
        client = AsyncHTTPClient()

        input_headers = {
            "User-Agent": "okhttp/4.12.0 UdemyAndroid 9.116.0(2078) (phone)",
            "Referer": "https://www.udemy.com/",
            "Authorization": "Bearer mytoken",
            "X-Requested-With": "com.udemy.android",
            "sec-ch-ua": '"Chromium";v="133"',
            "sec-ch-ua-mobile": "?1",
            "sec-ch-ua-platform": '"Android"',
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }

        # Server scraper builder
        server_res = client._build_scraper_headers_server(
            input_headers, {}, is_mobile_request=True, req_type="mobile"
        )
        for hint in (
            "sec-ch-ua",
            "sec-ch-ua-mobile",
            "sec-ch-ua-platform",
            "sec-fetch-site",
            "sec-fetch-mode",
            "sec-fetch-dest",
        ):
            assert hint not in server_res
            assert hint.title() not in server_res
        assert server_res.get("User-Agent") == input_headers["User-Agent"]
        assert server_res.get("Authorization") == "Bearer mytoken"
        assert server_res.get("Accept-Encoding") == "identity"

        # Local scraper builder
        local_res = client._build_scraper_headers_local(
            input_headers, {}, is_mobile_request=True
        )
        assert "sec-ch-ua" not in local_res
        assert "sec-ch-ua-mobile" not in local_res
        assert "sec-ch-ua-platform" not in local_res
        assert local_res.get("User-Agent") == input_headers["User-Agent"]
        assert local_res.get("Authorization") == "Bearer mytoken"
        assert local_res.get("Accept-Encoding") == "identity"

    def test_local_scraper_headers_preserves_expected_desktop_behavior(self):
        """Assert _build_scraper_headers_local maintains hint preservation when is_mobile_request=False."""
        client = AsyncHTTPClient()
        input_headers = {
            "Referer": "https://www.udemy.com/",
            "Authorization": "Bearer mytoken",
            "User-Agent": "okhttp/4.9.2",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.udemy.com",
            "Content-Type": "application/json",
            "sec-ch-ua": '"Chromium";v="133"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Linux"',
        }

        res = client._build_scraper_headers_local(input_headers, {}, is_mobile_request=False)
        assert res.get("sec-ch-ua") == '"Chromium";v="133"'
        assert res.get("sec-ch-ua-mobile") == "?0"
        assert res.get("sec-ch-ua-platform") == '"Linux"'
        assert res.get("User-Agent") == "okhttp/4.9.2"

    def test_safe_mobile_fallback(self):
        """Verify that if mobile UA pool is empty, choice fallback does not raise IndexError."""
        client = AsyncHTTPClient()
        client._is_server = False

        # Temporarily mock empty mobile pool
        with patch.object(client, "_USER_AGENTS_LOCAL", ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/133.0"]):
            parsed = urlparse("https://www.udemy.com/api-2.0/")
            # Should not raise IndexError
            headers = client._get_headers_local(parsed, None, "mobile")
            ua = headers.get("User-Agent", "")
            assert "UdemyAndroid" in ua or "okhttp" in ua

    @pytest.mark.asyncio
    async def test_free_checkout_uses_udemy_android_header(self):
        """Verify free_checkout dispatches with X-Requested-With: com.udemy.android and Bearer token."""
        client = UdemyClient()
        client.cookie_dict = {"access_token": "valid_access_token"}

        course = Course(title="Free Test Course", url="https://www.udemy.com/course/free-test/")
        course.course_id = "98765"
        course.price = 0.0

        r1 = MagicMock(status_code=200, headers={})
        r2 = MagicMock(status_code=200, headers={})
        client.http.get = AsyncMock(side_effect=[r1, r2])
        client.http.safe_json = AsyncMock(return_value={"_class": "course", "id": 98765})

        await client.free_checkout(course)

        assert client.http.get.await_count == 2
        calls = client.http.get.await_args_list
        r1_call = calls[0]
        sent_headers = r1_call.kwargs.get("headers", {})
        assert sent_headers.get("X-Requested-With") == "com.udemy.android"
        assert sent_headers.get("Authorization") == "Bearer valid_access_token"
        assert "okhttp" in sent_headers.get("User-Agent", "")
        assert r1_call.kwargs.get("req_type") == "mobile"
