"""Unit tests for UdemyClient Checkout Circuit Breaker (Wave 1 & Wave 3)."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.course import Course
from app.services.udemy_client import UdemyClient


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

        client._cs_post = AsyncMock()
        client._cs_get = AsyncMock()
        client.free_checkout = AsyncMock()

        result = await client.checkout_single(course)

        assert result is False
        assert course.status is False
        assert course.error == "checkout_circuit_open"
        assert client._cs_post.await_count == 0
        assert client._cs_get.await_count == 0
        assert client.free_checkout.await_count == 0

    @pytest.mark.asyncio
    async def test_double_checked_locking_prevents_queued_worker_execution(self):
        """Worker 2 queued on semaphore exits immediately when Worker 1 trips the breaker."""
        client = UdemyClient()
        client.cs = MagicMock()

        course1 = Course(title="Course 1", url="https://www.udemy.com/course/c1/")
        course1.course_id = "101"
        course1.price = 0.0

        course2 = Course(title="Course 2", url="https://www.udemy.com/course/c2/")
        course2.course_id = "102"
        course2.price = 0.0

        post_calls = []

        async def mock_cs_post(url, **kwargs):
            post_calls.append(url)
            # Course 1 simulates a 403 HTML challenge and trips breaker
            resp = MagicMock(status_code=403, text="<title>Just a moment...</title>", headers={"content-type": "text/html"})
            return resp

        client._cs_post = AsyncMock(side_effect=mock_cs_post)
        client._cs_get = AsyncMock(return_value=MagicMock(status_code=200, text=""))

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
    async def test_soft_tier_retry_refreshes_csrf_on_first_403(self):
        """First 403 triggers soft retry with CSRF refresh and succeeds on attempt 2."""
        client = UdemyClient()
        client.cs = MagicMock()

        course = Course(title="Soft Retry Course", url="https://www.udemy.com/course/soft/")
        course.course_id = "201"
        course.price = 0.0

        r1 = MagicMock(status_code=403, text="<title>Just a moment...</title>", headers={"content-type": "text/html"})
        r2 = MagicMock(status_code=200, text='{"status": "succeeded"}', headers={"content-type": "application/json"})
        r2.json = MagicMock(return_value={"status": "succeeded"})

        client._cs_post = AsyncMock(side_effect=[r1, r2])
        client._cs_get = AsyncMock(return_value=MagicMock(status_code=200, text='<input name="csrfmiddlewaretoken" value="fresh_token">'))

        with patch("asyncio.sleep", AsyncMock()):
            await client._du_checkout(course)

        assert course.status is True
        assert client._checkout_consecutive_403s == 0
        assert client._checkout_trip_count == 0
        assert client.is_checkout_circuit_open() is False
        assert client._cs_post.await_count == 2
        # CSRF refresh GET was invoked on soft retry
        assert client._cs_get.await_count >= 2

    @pytest.mark.asyncio
    async def test_hard_tier_trips_breaker_on_second_consecutive_403(self):
        """Second consecutive 403 trips breaker with exponential backoff."""
        client = UdemyClient()
        client.cs = MagicMock()

        course = Course(title="Hard 403 Course", url="https://www.udemy.com/course/hard/")
        course.course_id = "301"
        course.price = 0.0

        r_cf = MagicMock(status_code=403, text="<title>Just a moment...</title>", headers={"content-type": "text/html"})
        client._cs_post = AsyncMock(return_value=r_cf)
        client._cs_get = AsyncMock(return_value=MagicMock(status_code=200, text=""))

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
        client.cs = MagicMock()
        client._checkout_consecutive_403s = 1

        course = Course(title="Expired Course", url="https://www.udemy.com/course/exp/")
        course.course_id = "401"
        course.price = 0.0

        r_expired = MagicMock(
            status_code=400,
            text='{"message": "Coupon expired"}',
            headers={"content-type": "application/json"},
        )
        r_expired.json = MagicMock(return_value={"message": "Coupon expired"})

        client._cs_post = AsyncMock(return_value=r_expired)
        client._cs_get = AsyncMock(return_value=MagicMock(status_code=200, text=""))

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
        client.cs = MagicMock()
        client._checkout_consecutive_403s = 1

        course = Course(title="Trip Fallback Test", url="https://www.udemy.com/course/fb/")
        course.course_id = "501"
        course.price = 0.0
        course.coupon_code = "FREEBIE"

        r_cf = MagicMock(status_code=403, text="<title>Just a moment...</title>", headers={"content-type": "text/html"})
        client._cs_post = AsyncMock(return_value=r_cf)
        client._cs_get = AsyncMock(return_value=MagicMock(status_code=200, text=""))
        client.free_checkout = AsyncMock()

        with patch("asyncio.sleep", AsyncMock()):
            res = await client.checkout_single(course)

        assert res is False
        assert course.error == "checkout_circuit_open"
        # Breaker tripped -> free_checkout MUST NOT be called
        assert client.free_checkout.await_count == 0
