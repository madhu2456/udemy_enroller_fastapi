"""Unit tests for UdemyClient Checkout Circuit Breaker (Wave 1 & Wave 3)."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.course import Course
from app.services.udemy_client import UdemyClient


@pytest.fixture(autouse=True)
def guard_memory_ceiling():
    """Module-level override for host memory ceiling check."""
    yield


class TestCheckoutCircuitBreaker:
    """Test two-tier checkout circuit breaker with double-checked locking."""

    @pytest.mark.asyncio
    async def test_fast_fail_when_circuit_open_makes_zero_network_calls(self):
        """When circuit is open, _du_checkout and checkout_single immediately fast-fail."""
        client = UdemyClient()
        client._checkout_circuit_open_until = time.monotonic() + 60.0

        course = Course(title="Blocked Course", url="https://www.udemy.com/course/blocked-course/")
        course.course_id = "12345"
        course.price = 0.0
        course.is_free = True

        client.http = MagicMock()
        client.http.post = AsyncMock()
        client.http.get = AsyncMock()
        client.free_checkout = AsyncMock()

        result = await client.checkout_single(course)

        assert result is False
        assert course.status is False
        assert course.error == "checkout_circuit_open"
        assert client.http.post.await_count == 0
        assert client.http.get.await_count == 0
        assert client.free_checkout.await_count == 0

    @pytest.mark.asyncio
    async def test_double_checked_locking_prevents_queued_worker_execution(self):
        """Worker 2 queued on semaphore exits immediately when Worker 1 trips the breaker."""
        client = UdemyClient()
        client.http = MagicMock()

        course1 = Course(title="Course 1", url="https://www.udemy.com/course/c1/")
        course1.course_id = "101"
        course1.price = 0.0

        course2 = Course(title="Course 2", url="https://www.udemy.com/course/c2/")
        course2.course_id = "102"
        course2.price = 0.0

        post_calls = []

        async def mock_http_post(url, **kwargs):
            post_calls.append(url)
            # Course 1 simulates a 403 HTML challenge and trips breaker
            resp = MagicMock(status_code=403, text="<title>Just a moment...</title>", headers={"content-type": "text/html"}, cookies={})
            return resp

        client.http.post = AsyncMock(side_effect=mock_http_post)
        client.http.get = AsyncMock(return_value=MagicMock(status_code=302, text="", cookies={}))

        # Pre-set consecutive 403s to 1 so Course 1's 403 trips the breaker (>= 2)
        client._checkout_consecutive_403s = 1

        # Launch both workers concurrently
        task1 = asyncio.create_task(client._du_checkout(course1))
        task2 = asyncio.create_task(client._du_checkout(course2))

        await asyncio.gather(task1, task2)

        # Worker 1 tripped the breaker
        assert course1.error == "checkout_circuit_open"
        assert client.is_checkout_circuit_open() is True

        # Worker 2 was waiting on semaphore, acquired it, saw breaker open, and exited without POST
        assert course2.error == "checkout_circuit_open"
        assert len(post_calls) == 1

    @pytest.mark.asyncio
    async def test_preflight_skipped_when_csrf_token_cached(self):
        """Desktop payment/checkout/ is never queried; mobile preflight to sub_url executes to seed cookies."""
        client = UdemyClient()
        client.http = MagicMock()
        client.cookie_dict["csrftoken"] = "valid_csrf_token"

        course = Course(title="Preflight Skip Course", url="https://www.udemy.com/course/skip/")
        course.course_id = "202"
        course.price = 0.0
        course.coupon_code = "DISCOUNT100"

        resp = MagicMock(status_code=200, text='{"status": "succeeded"}', headers={"content-type": "application/json"}, cookies={})
        resp.json = MagicMock(return_value={"status": "succeeded"})

        client.http.post = AsyncMock(return_value=resp)
        client.http.get = AsyncMock(return_value=MagicMock(status_code=302, text="", cookies={"dj_session_id": "sess_123"}))

        await client._du_checkout(course)

        assert course.status is True
        for call_args in client.http.get.call_args_list:
            url_called = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
            assert "payment/checkout" not in str(url_called)
        assert client.http.get.await_count >= 1
        first_get_url = client.http.get.call_args_list[0][0][0]
        assert "course/subscribe" in first_get_url
        assert "courseId=202" in first_get_url
        assert "couponCode=DISCOUNT100" in first_get_url

    @pytest.mark.asyncio
    async def test_soft_tier_retry_does_not_re_get_checkout_on_cloudflare_challenge(self):
        """First 403 triggers soft retry with jittered backoff without re-fetching checkout page."""
        client = UdemyClient()
        client.http = MagicMock()
        client.cookie_dict["csrftoken"] = "cached_csrf"

        course = Course(title="Soft Retry Course", url="https://www.udemy.com/course/soft/")
        course.course_id = "201"
        course.price = 0.0

        r1 = MagicMock(status_code=403, text="<title>Just a moment...</title>", headers={"content-type": "text/html"}, cookies={})
        r2 = MagicMock(status_code=200, text='{"status": "succeeded"}', headers={"content-type": "application/json"}, cookies={})
        r2.json = MagicMock(return_value={"status": "succeeded"})

        client.http.post = AsyncMock(side_effect=[r1, r2])
        client.http.get = AsyncMock(return_value=MagicMock(status_code=302, text="", cookies={}))

        with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
            await client._du_checkout(course)

        assert course.status is True
        assert client._checkout_consecutive_403s == 0
        assert client._checkout_trip_count == 0
        assert client.is_checkout_circuit_open() is False
        assert client.http.post.await_count == 2
        # Zero GET calls to checkout page when CSRF is cached and on soft 403
        for call_args in client.http.get.call_args_list:
            assert "payment/checkout" not in str(call_args)
        assert mock_sleep.await_count >= 1

    @pytest.mark.asyncio
    async def test_hard_tier_trips_breaker_on_second_consecutive_403(self):
        """Second consecutive 403 trips breaker with exponential backoff."""
        client = UdemyClient()
        client.http = MagicMock()

        course = Course(title="Hard 403 Course", url="https://www.udemy.com/course/hard/")
        course.course_id = "301"
        course.price = 0.0

        r_cf = MagicMock(status_code=403, text="<title>Just a moment...</title>", headers={"content-type": "text/html"}, cookies={})
        client.http.post = AsyncMock(return_value=r_cf)
        client.http.get = AsyncMock(return_value=MagicMock(status_code=302, text="", cookies={}))

        start_time = time.monotonic()
        with patch("asyncio.sleep", AsyncMock()):
            await client._du_checkout(course)

        assert course.status is False
        assert course.error == "checkout_circuit_open"
        assert client._checkout_consecutive_403s == 2
        assert client._checkout_trip_count == 1
        assert client.is_checkout_circuit_open() is True
        # Trip 1: 45 * 2^0 = 45s cooldown
        remaining = client._checkout_circuit_open_until - start_time
        assert 44.0 <= remaining <= 46.0

    @pytest.mark.asyncio
    async def test_non_403_application_response_resets_streak(self):
        """Non-403 responses (200, 400 expired) reset consecutive 403 count to 0."""
        client = UdemyClient()
        client.http = MagicMock()
        client._checkout_consecutive_403s = 1

        course = Course(title="Expired Course", url="https://www.udemy.com/course/exp/")
        course.course_id = "401"
        course.price = 0.0

        r_expired = MagicMock(
            status_code=400,
            text='{"message": "Coupon expired"}',
            headers={"content-type": "application/json"},
            cookies={},
        )
        r_expired.json = MagicMock(return_value={"message": "Coupon expired"})

        client.http.post = AsyncMock(return_value=r_expired)
        client.http.get = AsyncMock(return_value=MagicMock(status_code=302, text="", cookies={}))

        await client._du_checkout(course)

        assert course.status is False
        assert "expired" in course.error.lower()
        # Streak was reset by application response
        assert client._checkout_consecutive_403s == 0
        assert client.is_checkout_circuit_open() is False

    @pytest.mark.asyncio
    async def test_checkout_single_suppresses_fallback_when_circuit_open(self):
        """checkout_single never falls back to free_checkout when breaker is open."""
        client = UdemyClient()
        client.http = MagicMock()
        client._checkout_consecutive_403s = 1

        course = Course(title="Trip Fallback Test", url="https://www.udemy.com/course/fb/")
        course.course_id = "501"
        course.price = 0.0
        course.coupon_code = "FREEBIE"

        r_cf = MagicMock(status_code=403, text="<title>Just a moment...</title>", headers={"content-type": "text/html"}, cookies={})
        client.http.post = AsyncMock(return_value=r_cf)
        client.http.get = AsyncMock(return_value=MagicMock(status_code=302, text="", cookies={}))
        client.free_checkout = AsyncMock()

        with patch("asyncio.sleep", AsyncMock()):
            res = await client.checkout_single(course)

        assert res is False
        assert course.error == "checkout_circuit_open"
        # Breaker tripped -> free_checkout MUST NOT be called
        assert client.free_checkout.await_count == 0

    @pytest.mark.parametrize(
        "symbol,expected_iso",
        [
            ("₹", "INR"),
            ("$", "USD"),
            ("€", "EUR"),
            ("£", "GBP"),
            ("¥", "JPY"),
            ("₩", "KRW"),
            ("₺", "TRY"),
            ("₽", "RUB"),
            ("R$", "BRL"),
            ("zł", "PLN"),
            ("₱", "PHP"),
            ("₫", "VND"),
            ("₪", "ILS"),
            ("A$", "AUD"),
            ("C$", "CAD"),
            ("S$", "SGD"),
            ("HK$", "HKD"),
            ("NZ$", "NZD"),
            ("NT$", "TWD"),
            ("MEX$", "MXN"),
            ("RM$", "MYR"),
            ("฿", "THB"),
            ("CHF", "CHF"),
            ("kr", "SEK"),
            ("EUR", "EUR"),
            ("usd", "USD"),
            ("invalid", "USD"),
            (None, "USD"),
            ("", "USD"),
        ],
    )
    def test_currency_normalization_symbols_to_iso(self, symbol, expected_iso):
        from app.core.constants import normalize_currency

        assert normalize_currency(symbol) == expected_iso

    def test_circuit_cooldown_remaining_and_trip_ceiling(self):
        """Test get_checkout_circuit_cooldown_remaining, expiry transition, and trip ceiling."""
        client = UdemyClient()
        assert client.get_checkout_circuit_cooldown_remaining() == 0.0
        assert client.is_checkout_circuit_open() is False
        assert client.has_exceeded_max_circuit_trips() is False

        # Set cooldown 10s into future
        now = time.monotonic()
        client._checkout_circuit_open_until = now + 10.0
        rem = client.get_checkout_circuit_cooldown_remaining()
        assert 9.0 <= rem <= 10.0
        assert client.is_checkout_circuit_open() is True

        # Cooldown in past transitions to 0.0 and HALF-OPEN
        client._checkout_circuit_open_until = now - 1.0
        assert client.get_checkout_circuit_cooldown_remaining() == 0.0
        assert client.is_checkout_circuit_open() is False
        assert client._checkout_circuit_open_until == 0.0

        # Trip ceiling enforcement
        client._checkout_trip_count = 2
        assert client.has_exceeded_max_circuit_trips() is False
        client._checkout_trip_count = 3
        assert client.has_exceeded_max_circuit_trips() is True
        client._checkout_trip_count = 4
        assert client.has_exceeded_max_circuit_trips() is True

    @pytest.mark.asyncio
    async def test_checkout_halts_when_trip_ceiling_exceeded(self):
        """_du_checkout aborts with checkout_circuit_exhausted when MAX_CIRCUIT_TRIPS exceeded."""
        client = UdemyClient()
        client.http = MagicMock()
        client._checkout_trip_count = UdemyClient.MAX_CIRCUIT_TRIPS

        course = Course(title="Exhausted Course", url="https://www.udemy.com/course/ex/")
        course.course_id = "999"
        course.price = 0.0

        client.http.post = AsyncMock()
        client.http.get = AsyncMock()

        await client._du_checkout(course)

        assert course.status is False
        assert course.error == "checkout_circuit_exhausted"
        assert client.http.post.await_count == 0
        assert client.http.get.await_count == 0

    @pytest.mark.asyncio
    async def test_du_checkout_mobile_contract_headers(self):
        """_du_checkout dispatches to http.post with mobile contract and stripped browser headers,

        omitting Authorization, Referer, Origin, and XMLHttpRequest headers.
        """
        client = UdemyClient()
        client.http = MagicMock()
        client.cookie_dict["csrftoken"] = "valid_csrf_token"
        client.cookie_dict["access_token"] = "fake_access_token_123"

        course = Course(title="No Bearer Course", url="https://www.udemy.com/course/no-bearer/")
        course.course_id = "54321"
        course.price = 0.0

        resp = MagicMock(
            status_code=200,
            text='{"status": "succeeded"}',
            headers={"content-type": "application/json"},
            cookies={},
        )
        resp.json = MagicMock(return_value={"status": "succeeded"})

        client.http.post = AsyncMock(return_value=resp)
        client.http.get = AsyncMock(return_value=MagicMock(status_code=302, text="", cookies={}))

        await client._du_checkout(course)

        assert course.status is True
        assert client.http.post.await_count == 1
        _call_args, call_kwargs = client.http.post.call_args
        headers = call_kwargs.get("headers", {})

        # Assert mobile contract parameters
        assert call_kwargs.get("req_type") == "mobile"
        assert call_kwargs.get("use_cloudscraper") is False
        assert call_kwargs.get("raise_for_status") is False
        assert call_kwargs.get("attempts") == 1

        # Assert Authorization header is strictly absent
        assert "Authorization" not in headers
        assert "authorization" not in {k.lower() for k in headers.keys()}

        # Assert browser headers are strictly absent
        assert "X-Requested-With" not in headers
        assert "x-requested-with" not in {k.lower() for k in headers.keys()}
        assert "Referer" not in headers
        assert "referer" not in {k.lower() for k in headers.keys()}
        assert "Origin" not in headers
        assert "origin" not in {k.lower() for k in headers.keys()}

        # Assert required payload headers remain present
        assert headers.get("X-CSRF-Token") == "valid_csrf_token"
        assert headers.get("Content-Type") == "application/json"

    # Alias for backward compatibility
    test_du_checkout_omits_authorization_header_when_access_token_present = test_du_checkout_mobile_contract_headers

    @pytest.mark.asyncio
    async def test_preflight_401_fails_fast_with_auth_error(self):
        """HTTP 401 on preflight GET halts immediately with Auth error (401)."""
        client = UdemyClient()
        client.http = MagicMock()
        client.http.get = AsyncMock(return_value=MagicMock(status_code=401, text="Unauthorized", cookies={}))
        client.http.post = AsyncMock()

        course = Course(title="Auth Error Course", url="https://www.udemy.com/course/auth/")
        course.course_id = "601"
        course.price = 0.0

        await client._du_checkout(course)

        assert course.status is False
        assert course.error == "Auth error (401)"
        assert client.http.post.await_count == 0

    @pytest.mark.asyncio
    async def test_preflight_403_increments_circuit_breaker_streak(self):
        """HTTP 403 on preflight GET increments consecutive 403 streak."""
        client = UdemyClient()
        client.http = MagicMock()
        client.http.get = AsyncMock(return_value=MagicMock(status_code=403, text="Forbidden", cookies={}))
        resp = MagicMock(
            status_code=200,
            text='{"status": "succeeded"}',
            headers={"content-type": "application/json"},
            cookies={},
        )
        resp.json = MagicMock(return_value={"status": "succeeded"})
        client.http.post = AsyncMock(return_value=resp)

        course = Course(title="Preflight 403 Course", url="https://www.udemy.com/course/pf403/")
        course.course_id = "602"
        course.price = 0.0

        with patch("asyncio.sleep", AsyncMock()):
            await client._du_checkout(course)

        assert client._checkout_consecutive_403s == 0  # 403 incremented then reset by 200 post
        # Now verify two consecutive preflight 403s trip breaker
        client.http.post.reset_mock()
        course2 = Course(title="Trip Breaker Course", url="https://www.udemy.com/course/trip/")
        course2.course_id = "603"
        course2.price = 0.0
        client._checkout_consecutive_403s = 1

        with patch("asyncio.sleep", AsyncMock()):
            await client._du_checkout(course2)

        assert course2.status is False
        assert course2.error == "checkout_circuit_open"
        assert client.is_checkout_circuit_open() is True
        assert client.http.post.await_count == 0

    @pytest.mark.asyncio
    async def test_preflight_400_rejects_expired_coupon(self):
        """HTTP 400 on preflight GET rejects invalid/expired coupon."""
        client = UdemyClient()
        client.http = MagicMock()
        client.http.get = AsyncMock(return_value=MagicMock(status_code=400, text="Bad Request", cookies={}))
        client.http.post = AsyncMock()

        course = Course(title="Bad Coupon Course", url="https://www.udemy.com/course/bad/")
        course.course_id = "604"
        course.price = 0.0

        await client._du_checkout(course)

        assert course.status is False
        assert "Invalid or expired coupon" in course.error
        assert client.http.post.await_count == 0

    @pytest.mark.asyncio
    async def test_preflight_302_normal_redirect_proceeds_to_checkout(self):
        """HTTP 302 on preflight GET seeds cookies and proceeds to checkout submission."""
        client = UdemyClient()
        client.http = MagicMock()
        client.cookie_dict = {}
        client.http.get = AsyncMock(return_value=MagicMock(status_code=302, cookies={"csrftoken": "pre_csrf", "__cf_bm": "bm123"}))
        resp = MagicMock(status_code=200, text='{"status": "succeeded"}', headers={"content-type": "application/json"}, cookies={})
        resp.json = MagicMock(return_value={"status": "succeeded"})
        client.http.post = AsyncMock(return_value=resp)

        course = Course(title="Normal 302 Course", url="https://www.udemy.com/course/norm/")
        course.course_id = "605"
        course.price = 0.0

        await client._du_checkout(course)

        assert course.status is True
        assert client.cookie_dict.get("csrftoken") == "pre_csrf"
        assert client.http.post.await_count == 1
