"""F-ENRL-C14 / F-ENRL-O02: bounded 429 retry loop and honest 504/503 handling.

- C14: _du_checkout rate-limit retries are iterative (max 3), never recursive,
  and a non-numeric Retry-After header falls back to 60s instead of crashing.
- O02: 504 (checkout) and 503 (free checkout) never confirm enrollment —
  the course is marked unknown (status None, error marker), not enrolled.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.udemy_client import UdemyClient
from app.services.course import Course


@pytest.fixture
def udemy_client():
    client = UdemyClient()
    client.cs = MagicMock()
    return client


def _course():
    return Course("Test", "https://www.udemy.com/course/test/")


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
