"""F-ENRL-C14 / F-ENRL-O02: bounded 429 retry loop and honest 504/503 handling.

- C14: _du_checkout rate-limit retries are iterative (max 3), never recursive,
  and a non-numeric Retry-After header falls back to 60s instead of crashing.
- O02: 504 (checkout) and 503 (free checkout) never confirm enrollment —
  the course is marked unknown (status None, error marker), not enrolled.
"""

import pytest
import requests
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.udemy_client import UdemyClient
from app.services.course import Course


@pytest.fixture
def udemy_client():
    client = UdemyClient()
    client.cs = MagicMock()
    return client


def _course():
    c = Course("Test", "https://www.udemy.com/course/test/")
    c.course_id = "123"
    return c


async def _run_du_checkout(client, course, responses):
    """Run _du_checkout with mocked session primitives and mocked sleeps."""
    client.cookie_dict = {}
    client._cs_get = AsyncMock(return_value=None)
    client._extract_csrf_from_html = AsyncMock(return_value=None)
    client._cs_post = AsyncMock(side_effect=responses)
    with patch("app.services.udemy_client.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        await client._du_checkout(course)
        return mock_sleep


class TestRateLimitRetryLoop:
    """F-ENRL-C14: capped iterative 429 retries."""

    @pytest.mark.asyncio
    async def test_429_gives_up_after_cap(self, udemy_client):
        course = _course()
        mock_sleep = await _run_du_checkout(
            udemy_client,
            course,
            [MagicMock(status_code=429, headers={"Retry-After": "5"})] * 10,
        )
        # Cap is 3: 4th 429 stops the run instead of recursing.
        assert course.status is False
        assert udemy_client._cs_post.await_count == 4
        assert len(mock_sleep.await_args_list) >= 4  # retry waits happened

    @pytest.mark.asyncio
    async def test_429_non_numeric_retry_after_falls_back_to_60(self, udemy_client):
        course = _course()
        mock_sleep = await _run_du_checkout(
            udemy_client,
            course,
            [MagicMock(status_code=429, headers={"Retry-After": "soon"})] * 10,
        )
        assert course.status is False
        waited = [call.args[0] for call in mock_sleep.await_args_list if call.args]
        assert 60 in waited  # non-numeric header -> 60s (F-ENRL-C14)

    @pytest.mark.asyncio
    async def test_429_numeric_retry_after_respected(self, udemy_client):
        course = _course()
        mock_sleep = await _run_du_checkout(
            udemy_client,
            course,
            [MagicMock(status_code=429, headers={"Retry-After": "7"})] * 10,
        )
        assert course.status is False
        waited = [call.args[0] for call in mock_sleep.await_args_list if call.args]
        assert 7 in waited

    @pytest.mark.asyncio
    async def test_success_after_rate_limit_retry(self, udemy_client):
        """429 then succeeded: enrollment still completes in-loop."""
        course = _course()
        course.course_id = "123"
        responses = [
            MagicMock(status_code=429, headers={"Retry-After": "2"}),
            MagicMock(status_code=200, json=lambda: {"status": "succeeded"}),
        ]
        await _run_du_checkout(udemy_client, course, responses)
        assert course.status is True


class TestIndeterminateResponses:
    """F-ENRL-O02: 504/503 are unknown, never enrolled."""

    @pytest.mark.asyncio
    async def test_du_checkout_504_is_unknown(self, udemy_client):
        course = _course()
        await _run_du_checkout(
            udemy_client, course, [MagicMock(status_code=504)]
        )
        assert course.status is None
        assert "unknown" in (course.error or "")
        assert udemy_client.unknown_c == 0  # counter is incremented by the pipeline

    @pytest.mark.asyncio
    async def test_free_checkout_503_is_unknown(self, udemy_client):
        course = _course()
        udemy_client.http.get = AsyncMock(
            return_value=MagicMock(status_code=503, headers={})
        )
        await udemy_client.free_checkout(course)
        assert course.status is None
        assert "unknown" in (course.error or "")

    @pytest.mark.asyncio
    async def test_free_checkout_503_not_counted_enrolled(self, udemy_client):
        """503 must not set status True anywhere in the free path."""
        course = _course()
        udemy_client.http.get = AsyncMock(
            return_value=MagicMock(status_code=503, headers={})
        )
        await udemy_client.free_checkout(course)
        assert course.status is not True



class TestFreeCheckoutStatusMatrix:
    """Task 3.2: free_checkout non-raising & status matrix."""

    @pytest.mark.asyncio
    async def test_free_checkout_auth_error_fails_fast(self, udemy_client):
        course = _course()
        course.course_id = "123"
        r1 = MagicMock(status_code=403, headers={})
        udemy_client.http.get = AsyncMock(return_value=r1)
        await udemy_client.free_checkout(course)
        assert course.status is False
        assert "Auth error (403)" in course.error
        assert udemy_client.http.get.await_count == 1

    @pytest.mark.asyncio
    async def test_free_checkout_404_not_enrolled(self, udemy_client):
        course = _course()
        course.course_id = "123"
        r1 = MagicMock(status_code=302, headers={})
        r2 = MagicMock(status_code=404, headers={})
        udemy_client.http.get = AsyncMock(side_effect=[r1, r2])
        await udemy_client.free_checkout(course)
        assert course.status is False
        assert udemy_client.http.get.await_count == 2
        calls = udemy_client.http.get.await_args_list
        assert calls[0].kwargs.get("raise_for_status") is False
        assert calls[1].kwargs.get("raise_for_status") is False

    @pytest.mark.asyncio
    async def test_free_checkout_200_enrolled(self, udemy_client):
        course = _course()
        course.course_id = "123"
        r1 = MagicMock(status_code=200, headers={})
        r2 = MagicMock(status_code=200, headers={})
        udemy_client.http.get = AsyncMock(side_effect=[r1, r2])
        udemy_client.http.safe_json = AsyncMock(return_value={"_class": "course", "id": 123})
        await udemy_client.free_checkout(course)
        assert course.status is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code", [301, 308])
    async def test_free_checkout_301_308_redirect_proceeds_to_verification(self, udemy_client, status_code):
        course = _course()
        course.course_id = "123"
        r1 = MagicMock(status_code=status_code, headers={"Location": "https://www.udemy.com/cart/subscribe/confirm/"})
        r2 = MagicMock(status_code=200, headers={})
        udemy_client.http.get = AsyncMock(side_effect=[r1, r2])
        udemy_client.http.safe_json = AsyncMock(return_value={"_class": "course", "id": 123})
        await udemy_client.free_checkout(course)
        assert course.status is True
        assert udemy_client.http.get.await_count == 2

    @pytest.mark.asyncio
    async def test_free_checkout_follow_redirects_and_bearer_token(self, udemy_client):
        course = _course()
        course.course_id = "123"
        udemy_client.cookie_dict = {"access_token": "test_token_123"}
        r1 = MagicMock(status_code=200, headers={})
        r2 = MagicMock(status_code=200, headers={})
        udemy_client.http.get = AsyncMock(side_effect=[r1, r2])
        udemy_client.http.safe_json = AsyncMock(return_value={"_class": "course", "id": 123})
        await udemy_client.free_checkout(course)
        assert udemy_client.http.get.await_count == 2
        calls = udemy_client.http.get.await_args_list
        r1_call = calls[0]
        assert r1_call.kwargs.get("follow_redirects") is True
        assert r1_call.kwargs.get("headers", {}).get("Authorization") == "Bearer test_token_123"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code,header_key", [(301, "Location"), (308, "location")])
    async def test_free_checkout_logs_location_for_3xx(self, udemy_client, status_code, header_key):
        course = _course()
        course.course_id = "123"
        target_url = f"https://www.udemy.com/target/{status_code}"
        r1 = MagicMock(status_code=status_code, headers={header_key: target_url})
        r2 = MagicMock(status_code=200, headers={})
        udemy_client.http.get = AsyncMock(side_effect=[r1, r2])
        udemy_client.http.safe_json = AsyncMock(return_value={"_class": "course", "id": 123})
        with patch("app.services.udemy_client.logger") as mock_logger:
            await udemy_client.free_checkout(course)
            logged_messages = [call.args[0] for call in mock_logger.info.call_args_list if call.args]
            assert any(target_url in msg for msg in logged_messages)

    @pytest.mark.asyncio
    async def test_free_checkout_unexpected_status_sets_error(self, udemy_client):
        course = _course()
        course.course_id = "123"
        r1 = MagicMock(status_code=418, headers={})
        udemy_client.http.get = AsyncMock(return_value=r1)
        await udemy_client.free_checkout(course)
        assert course.status is False
        assert course.error == "Unexpected subscribe status=418"

    @pytest.mark.asyncio
    async def test_checkout_single_does_not_fallback_on_unknown(self, udemy_client):
        course = _course()
        course.is_free = True
        course.coupon_code = None
        udemy_client.free_checkout = AsyncMock(side_effect=lambda c: setattr(c, "status", None))
        udemy_client._du_checkout = AsyncMock()

        res = await udemy_client.checkout_single(course)
        assert res is None
        assert course.status is None
        udemy_client._du_checkout.assert_not_called()

    @pytest.mark.asyncio
    async def test_checkout_single_falls_back_on_false(self, udemy_client):
        course = _course()
        course.is_free = True
        course.coupon_code = None
        udemy_client.free_checkout = AsyncMock(side_effect=lambda c: setattr(c, "status", False))
        udemy_client._du_checkout = AsyncMock()

        await udemy_client.checkout_single(course)
        udemy_client._du_checkout.assert_called_once_with(course)


class TestDuCheckoutFailFastAndStatusMatrix:
    """Task 4.3: _du_checkout fail-fast, 400 enrolled, and 500 retry control."""

    @pytest.mark.asyncio
    async def test_du_checkout_already_subscribed_400(self, udemy_client):
        course = _course()
        r = MagicMock(
            status_code=400,
            headers={"content-type": "application/json"},
            url="https://www.udemy.com/payment/checkout-submit/",
            text='{"message": "You are already subscribed to this course", "developer_message": "already_enrolled"}',
        )
        r.json = MagicMock(return_value={"message": "You are already subscribed to this course", "developer_message": "already_enrolled"})
        await _run_du_checkout(udemy_client, course, [r])
        assert course.status is True
        assert udemy_client._cs_post.await_count == 1

    @pytest.mark.asyncio
    async def test_du_checkout_fatal_400_fails_fast(self, udemy_client):
        course = _course()
        r = MagicMock(
            status_code=400,
            headers={"content-type": "application/json"},
            url="https://www.udemy.com/payment/checkout-submit/",
            text='{"message": "Coupon expired"}',
        )
        r.json = MagicMock(return_value={"message": "Coupon expired"})
        await _run_du_checkout(udemy_client, course, [r])
        assert course.status is False
        assert "Coupon expired" in course.error
        assert udemy_client._cs_post.await_count == 1

    @pytest.mark.asyncio
    async def test_du_checkout_html_redirect_fails_fast(self, udemy_client):
        course = _course()
        r = MagicMock(
            status_code=200,
            headers={"content-type": "text/html; charset=utf-8"},
            url="https://www.udemy.com/cart/",
            text="<html><head><title>Cart</title></head><body>Your cart</body></html>",
        )
        await _run_du_checkout(udemy_client, course, [r])
        assert course.status is False
        assert "HTML redirect" in course.error
        assert udemy_client._cs_post.await_count == 1

    @pytest.mark.asyncio
    async def test_du_checkout_server_error_500_max_one_retry(self, udemy_client):
        course = _course()
        r1 = MagicMock(
            status_code=500,
            headers={"content-type": "application/json"},
            url="https://www.udemy.com/payment/checkout-submit/",
        )
        r2 = MagicMock(
            status_code=500,
            headers={"content-type": "application/json"},
            url="https://www.udemy.com/payment/checkout-submit/",
        )
        await _run_du_checkout(udemy_client, course, [r1, r2, r2, r2])
        assert course.status is False
        assert "server error" in course.error
        assert udemy_client._cs_post.await_count == 2


class TestCloudScraperCookieJarSync:
    """Task 1: CloudScraper cookie jar sync and clearance protection."""

    def test_sync_cs_cookies_preserves_clearance_cookies(self, udemy_client):
        udemy_client.cs.cookies = requests.cookies.RequestsCookieJar()
        jar = udemy_client.cs.cookies
        jar.set("cf_clearance", "secret_cf_token", domain=".udemy.com")
        udemy_client.cookie_dict = {"client_id": "xyz"}
        udemy_client._sync_cs_cookies()
        assert jar.get("cf_clearance", domain=".udemy.com") == "secret_cf_token"
        assert jar.get("client_id", domain=".udemy.com") == "xyz"

    def test_sync_cs_cookies_handles_cookie_conflict(self, udemy_client):
        udemy_client.cs.cookies = requests.cookies.RequestsCookieJar()
        jar = udemy_client.cs.cookies
        jar.set("access_token", "old_token", domain="www.udemy.com")
        jar.set("access_token", "domain_token", domain=".udemy.com")
        udemy_client.cookie_dict = {"access_token": "new_token"}
        # Should not raise CookieConflictError
        udemy_client._sync_cs_cookies()
        assert jar.get("access_token", domain=".udemy.com") == "new_token"

    def test_sync_cs_cookies_updates_changed_cookie(self, udemy_client):
        udemy_client.cs.cookies = requests.cookies.RequestsCookieJar()
        jar = udemy_client.cs.cookies
        jar.set("session_id", "val1", domain=".udemy.com")
        udemy_client.cookie_dict = {"session_id": "val2"}
        udemy_client._sync_cs_cookies()
        assert jar.get("session_id", domain=".udemy.com") == "val2"

    def test_sync_cs_cookies_back_populates_dict(self, udemy_client):
        udemy_client.cs.cookies = requests.cookies.RequestsCookieJar()
        jar = udemy_client.cs.cookies
        jar.set("new_cookie", "from_scraper", domain=".udemy.com")
        udemy_client.cookie_dict = {}
        udemy_client._sync_cs_cookies_back()
        assert udemy_client.cookie_dict.get("new_cookie") == "from_scraper"

    def test_sync_cs_cookies_safe_when_cs_none(self):
        client = UdemyClient()
        client.cs = None
        client.cookie_dict = {"key": "val"}
        # Must not raise
        client._sync_cs_cookies()
        client._sync_cs_cookies_back()


class TestFreeCheckoutCouponSupport:
    """Task 2: free_checkout coupon handling & sanitization."""

    @pytest.mark.asyncio
    async def test_free_checkout_missing_course_id_fails_fast(self, udemy_client):
        course = _course()
        course.course_id = None
        await udemy_client.free_checkout(course)
        assert course.status is False
        assert course.error == "Missing course_id"

    @pytest.mark.asyncio
    async def test_free_checkout_url_encodes_coupon_code(self, udemy_client):
        course = _course()
        course.course_id = "123"
        course.coupon_code = "CODE 100%"
        udemy_client.http.get = AsyncMock(return_value=MagicMock(status_code=200, headers={}))
        udemy_client.http.safe_json = AsyncMock(return_value={"_class": "course", "id": 123})
        await udemy_client.free_checkout(course)
        sub_call = udemy_client.http.get.await_args_list[0]
        assert "couponCode=CODE%20100%25" in sub_call.args[0]

    @pytest.mark.asyncio
    async def test_free_checkout_sets_404_error_message(self, udemy_client):
        course = _course()
        course.course_id = "123"
        r1 = MagicMock(status_code=302, headers={})
        r2 = MagicMock(status_code=404, headers={})
        udemy_client.http.get = AsyncMock(side_effect=[r1, r2])
        await udemy_client.free_checkout(course)
        assert course.status is False
        assert course.error == "Course not enrolled or coupon invalid (404)"

    @pytest.mark.asyncio
    async def test_free_checkout_clears_error_on_success(self, udemy_client):
        course = _course()
        course.course_id = "123"
        course.error = "Previous error"
        r1 = MagicMock(status_code=200, headers={})
        r2 = MagicMock(status_code=200, headers={})
        udemy_client.http.get = AsyncMock(side_effect=[r1, r2])
        udemy_client.http.safe_json = AsyncMock(return_value={"_class": "course", "id": 123})
        await udemy_client.free_checkout(course)
        assert course.status is True
        assert course.error is None


class TestCheckoutSingleCouponFallback:
    """Task 3: checkout_single fallback for 100% off coupon courses."""

    @pytest.mark.asyncio
    async def test_checkout_single_falls_back_on_html_challenge(self, udemy_client):
        course = _course()
        course.is_free = False
        course.coupon_code = "FREE100"
        async def fake_du(c):
            c.status = False
            c.error = "HTML redirect (Cloudflare challenge or cart)"
        udemy_client._du_checkout = AsyncMock(side_effect=fake_du)
        udemy_client.free_checkout = AsyncMock()

        await udemy_client.checkout_single(course)
        udemy_client.free_checkout.assert_called_once_with(course)

    @pytest.mark.asyncio
    async def test_checkout_single_falls_back_on_no_response_challenge(self, udemy_client):
        course = _course()
        course.is_free = False
        course.coupon_code = "FREE100"
        async def fake_du(c):
            c.status = False
            c.error = "Checkout failed (no response / challenge)"
        udemy_client._du_checkout = AsyncMock(side_effect=fake_du)
        udemy_client.free_checkout = AsyncMock()

        await udemy_client.checkout_single(course)
        udemy_client.free_checkout.assert_called_once_with(course)

    @pytest.mark.asyncio
    async def test_checkout_single_no_fallback_on_expired_coupon(self, udemy_client):
        course = _course()
        course.is_free = False
        course.coupon_code = "EXPIRED100"
        async def fake_du(c):
            c.status = False
            c.error = "Coupon expired"
        udemy_client._du_checkout = AsyncMock(side_effect=fake_du)
        udemy_client.free_checkout = AsyncMock()

        await udemy_client.checkout_single(course)
        udemy_client.free_checkout.assert_not_called()

    @pytest.mark.asyncio
    async def test_checkout_single_no_fallback_on_unknown_504(self, udemy_client):
        course = _course()
        course.is_free = False
        course.coupon_code = "FREE100"
        async def fake_du(c):
            c.status = None
            c.error = "unknown: 504 server unavailable"
        udemy_client._du_checkout = AsyncMock(side_effect=fake_du)
        udemy_client.free_checkout = AsyncMock()

        await udemy_client.checkout_single(course)
        udemy_client.free_checkout.assert_not_called()
