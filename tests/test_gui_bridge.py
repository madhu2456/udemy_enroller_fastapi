"""Unit tests for AsyncioBridge and headless GUI logic."""

import collections
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.gui.bridge import AsyncioBridge
from app.services.browser_cookies import UdemyBrowserCookies
from app.services.course import Course


def test_asyncio_bridge_lifecycle():
    """Test start, stop, send_command, and emit_event on AsyncioBridge."""
    bridge = AsyncioBridge()
    bridge.start()
    assert bridge.running is True
    assert bridge.worker_thread is not None
    assert bridge.worker_thread.is_alive()

    # Test event emit and poll
    bridge.emit_event("TEST_EVENT", {"foo": "bar"})
    events = bridge.poll_events()
    assert len(events) == 1
    assert events[0]["event"] == "TEST_EVENT"
    assert events[0]["data"]["foo"] == "bar"

    # Stop bridge
    bridge.stop()
    assert bridge.running is False


def test_bridge_command_pause_resume():
    """Test PAUSE and RESUME command handling in bridge."""
    bridge = AsyncioBridge()
    bridge.start()

    try:
        bridge.send_command("PAUSE")
        time.sleep(0.15)
        events = bridge.poll_events()
        status_events = [e for e in events if e.get("event") == "STATUS_CHANGE"]
        assert any(e["data"].get("status") == "PAUSED" for e in status_events)

        bridge.send_command("RESUME")
        time.sleep(0.15)
        events = bridge.poll_events()
        status_events = [e for e in events if e.get("event") == "STATUS_CHANGE"]
        assert any(e["data"].get("status") == "RUNNING" for e in status_events)
    finally:
        bridge.stop()


def test_bridge_test_login_mock():
    """Test TEST_LOGIN command handling with mock UdemyClient."""
    bridge = AsyncioBridge()
    bridge.start()

    try:
        with patch("app.gui.bridge.UdemyClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get_session_info = AsyncMock(return_value=True)
            mock_client.get_enrolled_courses = AsyncMock(return_value={})
            mock_client.close = AsyncMock()
            mock_client.display_name = "Jane Developer"
            mock_client.currency = "EUR"
            mock_client.udemy_user_id = "98765"
            mock_client.enrolled_courses = {}
            mock_client_cls.return_value = mock_client

            bridge.send_command("TEST_LOGIN", {"access_token": "valid_token_xyz"})
            time.sleep(0.2)

            events = bridge.poll_events()
            auth_success = next((e for e in events if e.get("event") == "AUTH_SUCCESS"), None)
            assert auth_success is not None
            assert auth_success["data"]["display_name"] == "Jane Developer"
            assert auth_success["data"]["currency"] == "EUR"
    finally:
        bridge.stop()


def test_bridge_auto_extract_cookies_mock():
    """Test AUTO_EXTRACT_COOKIES command in bridge."""
    bridge = AsyncioBridge()
    bridge.start()

    try:
        with patch("app.gui.bridge.get_udemy_cookies") as mock_get:
            mock_get.return_value = UdemyBrowserCookies(
                access_token="tok_1234567890",
                client_id="cid_1234",
                csrf_token="csrf_1234",
                browser_name="firefox",
                is_valid=True,
            )

            bridge.send_command("AUTO_EXTRACT_COOKIES", {"browser": "firefox"})
            time.sleep(0.2)

            events = bridge.poll_events()
            extracted = next((e for e in events if e.get("event") == "COOKIES_EXTRACTED"), None)
            assert extracted is not None
            assert extracted["data"]["browser_name"] == "firefox"
            assert extracted["data"]["is_valid"] is True
    finally:
        bridge.stop()


def test_bridge_scrape_only_mock():
    """Test SCRAPE_ONLY command with mock ScraperService."""
    bridge = AsyncioBridge()
    bridge.start()

    try:
        dummy_course = Course(
            title="GUI Python Testing",
            url="https://www.udemy.com/course/gui-test/?couponCode=FREEGUI",
        )
        dummy_course.rating = 4.9

        async def mock_stream(self):
            s_mock = MagicMock()
            s_mock.site_name = "Real Discount"
            s_mock.courses = [dummy_course]
            yield s_mock, "completed"

        with patch("app.gui.bridge.ScraperService.stream_results", new=mock_stream):
            bridge.send_command("SCRAPE_ONLY", {"sites": ["Real Discount"]})
            time.sleep(0.25)

            events = bridge.poll_events()
            discovered = [e for e in events if e.get("event") == "COURSE_DISCOVERED"]
            assert len(discovered) == 1
            assert discovered[0]["data"]["title"] == "GUI Python Testing"
    finally:
        bridge.stop()


def test_log_ring_buffer_fifo_capacity():
    """Test FIFO 1,000-line circular ring buffer behavior."""
    buffer = collections.deque(maxlen=1000)

    for i in range(1200):
        buffer.append(f"Log line {i}")

    assert len(buffer) == 1000
    # Oldest 200 items (0-199) dropped
    assert buffer[0] == "Log line 200"
    assert buffer[-1] == "Log line 1199"


def test_gui_headless_guard():
    """Test gui.py headless display guard exits gracefully when no DISPLAY is set."""
    env = dict(os.environ)
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)

    with patch.dict(os.environ, env, clear=True), patch("sys.exit", side_effect=SystemExit(1)) as mock_exit:
        from gui import run_gui
        with pytest.raises(SystemExit):
            run_gui()
        assert mock_exit.called
