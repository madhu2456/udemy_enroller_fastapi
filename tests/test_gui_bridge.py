"""Unit tests for AsyncioBridge and headless GUI logic."""

import collections
import os
import time
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.gui.bridge import AsyncioBridge
from app.models.database import EnrollmentRun
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


def _free_gui_course(title: str, slug: str) -> Course:
    course = Course(
        title=title,
        url=f"https://www.udemy.com/course/{slug}/?couponCode=FREE100",
    )
    course.price = Decimal("0.00")
    course.list_price = Decimal("19.99")
    course.is_free = True
    course.is_coupon_valid = True
    course.is_expired = False
    course.is_already_enrolled = False
    return course


def _gui_enroll_client(checkout_side_effect=None, checkout_return=True):
    mock_client = MagicMock()
    mock_client.is_authenticated = True
    mock_client.display_name = "Jane Developer"
    mock_client.udemy_user_id = "98765"
    mock_client.currency = "USD"
    mock_client.enrolled_courses = {}
    mock_client.successfully_enrolled_c = 0
    mock_client.already_enrolled_c = 0
    mock_client.expired_c = 0
    mock_client.excluded_c = 0
    mock_client.unknown_c = 0
    mock_client.amount_saved_c = Decimal(0)
    mock_client.cookie_login = MagicMock()
    mock_client.get_session_info = AsyncMock(return_value=True)
    mock_client.get_enrolled_courses = AsyncMock(return_value={})
    mock_client.check_course = AsyncMock()
    mock_client.is_course_excluded = MagicMock(return_value=False)
    mock_client.close = AsyncMock()
    if checkout_side_effect is not None:
        mock_client.checkout_single = AsyncMock(side_effect=checkout_side_effect)
    else:
        mock_client.checkout_single = AsyncMock(return_value=checkout_return)
    return mock_client


@pytest.mark.asyncio
async def test_bridge_live_enroll_respects_limit():
    """_handle_start_enroll with filters.limit=2 stops after two live enrollments."""
    bridge = AsyncioBridge()
    c1 = _free_gui_course("GUI Python One", "gui-python-one")
    c2 = _free_gui_course("GUI Python Two", "gui-python-two")
    c3 = _free_gui_course("GUI Python Three", "gui-python-three")

    mock_client = _gui_enroll_client(checkout_return=True)
    mock_scraper = MagicMock()
    mock_scraper.courses = [c1, c2, c3]
    mock_scraper.site_name = "FreeCourseSites"

    async def mock_stream():
        yield mock_scraper, "completed"

    with patch("app.gui.bridge.UdemyClient", return_value=mock_client), \
         patch("app.gui.bridge.ScraperService.stream_results", side_effect=mock_stream), \
         patch("app.gui.bridge.save_persistent_session"):
        await bridge._handle_start_enroll(
            {
                "access_token": "dummy_access_token",
                "client_id": "dummy_client_id",
                "csrf_token": "dummy_csrf_token",
                "sites": ["FreeCourseSites"],
                "filters": {"limit": 2},
            }
        )

    assert mock_client.checkout_single.await_count == 2
    assert mock_client.successfully_enrolled_c == 2
    assert isinstance(mock_client.successfully_enrolled_c, int)


@pytest.mark.asyncio
async def test_bridge_paid_path_does_not_increment_expired_c():
    """GUI paid / not-100% path must not increment expired_c and must skip checkout."""
    bridge = AsyncioBridge()
    paid = Course(
        title="Paid Course 40% Off",
        url="https://www.udemy.com/course/paid-gui/?couponCode=DISCOUNT40",
    )
    paid.price = Decimal("479.00")
    paid.is_free = False
    paid.is_coupon_valid = False
    paid.is_expired = False

    mock_client = _gui_enroll_client()
    mock_scraper = MagicMock()
    mock_scraper.courses = [paid]
    mock_scraper.site_name = "FreeCourseSites"

    async def mock_stream():
        yield mock_scraper, "completed"

    with patch("app.gui.bridge.UdemyClient", return_value=mock_client), \
         patch("app.gui.bridge.ScraperService.stream_results", side_effect=mock_stream), \
         patch("app.gui.bridge.save_persistent_session"):
        await bridge._handle_start_enroll(
            {
                "access_token": "dummy_access_token",
                "client_id": "dummy_client_id",
                "csrf_token": "dummy_csrf_token",
                "sites": ["FreeCourseSites"],
            }
        )

    mock_client.checkout_single.assert_not_called()
    assert mock_client.expired_c == 0
    assert isinstance(mock_client.expired_c, int)
    events = bridge.poll_events(max_count=200)
    processed = [e for e in events if e.get("event") == "COURSE_PROCESSED"]
    assert len(processed) == 1
    assert processed[0]["data"]["status"] == "PAID"


@pytest.mark.asyncio
async def test_bridge_false_none_checkout_increments_unknown_c():
    """GUI False/None checkout results increment unknown_c and mark FAILED."""
    bridge = AsyncioBridge()
    c1 = _free_gui_course("GUI Fail One", "gui-fail-one")
    c2 = _free_gui_course("GUI Fail Two", "gui-fail-two")

    mock_client = _gui_enroll_client(checkout_side_effect=[False, None])
    mock_scraper = MagicMock()
    mock_scraper.courses = [c1, c2]
    mock_scraper.site_name = "FreeCourseSites"

    async def mock_stream():
        yield mock_scraper, "completed"

    with patch("app.gui.bridge.UdemyClient", return_value=mock_client), \
         patch("app.gui.bridge.ScraperService.stream_results", side_effect=mock_stream), \
         patch("app.gui.bridge.save_persistent_session"):
        await bridge._handle_start_enroll(
            {
                "access_token": "dummy_access_token",
                "client_id": "dummy_client_id",
                "csrf_token": "dummy_csrf_token",
                "sites": ["FreeCourseSites"],
            }
        )

    assert mock_client.unknown_c == 2
    assert isinstance(mock_client.unknown_c, int)
    assert mock_client.successfully_enrolled_c == 0
    assert isinstance(mock_client.successfully_enrolled_c, int)
    events = bridge.poll_events(max_count=200)
    processed = [e for e in events if e.get("event") == "COURSE_PROCESSED"]
    assert len(processed) == 2
    assert [e["data"]["status"] for e in processed] == ["FAILED", "FAILED"]


@pytest.mark.asyncio
async def test_bridge_fetch_stats_uses_successfully_enrolled():
    """Verify _handle_fetch_stats uses successfully_enrolled attribute without raising AttributeError."""
    bridge = AsyncioBridge()
    run = EnrollmentRun(
        id=1,
        status="completed",
        successfully_enrolled=5,
        amount_saved=29.99,
        started_at=datetime(2026, 9, 26, 12, 0),
    )

    mock_db = MagicMock()
    mock_db.__enter__.return_value = mock_db
    mock_db.__exit__.return_value = None
    mock_db.query.return_value.order_by.return_value.limit.return_value.all.return_value = [run]

    with patch("app.gui.bridge.SessionLocal", return_value=mock_db):
        await bridge._handle_fetch_stats()

    events = bridge.poll_events()
    error_logs = [e for e in events if e.get("event") == "LOG" and e.get("data", {}).get("level") == "ERROR"]
    assert len(error_logs) == 0, f"Encountered unexpected error log: {error_logs}"

    stats_event = next((e for e in events if e.get("event") == "STATS_LOADED"), None)
    assert stats_event is not None
    data = stats_event["data"]
    assert data["total_runs"] == 1
    assert data["total_enrolled"] == 5
    assert data["total_saved"] == pytest.approx(29.99)
    assert len(data["runs"]) == 1
    assert data["runs"][0]["enrolled"] == 5
    assert data["runs"][0]["saved"] == pytest.approx(29.99)


@pytest.mark.asyncio
async def test_bridge_fetch_stats_empty_runs():
    """Verify _handle_fetch_stats handles empty run list cleanly."""
    bridge = AsyncioBridge()
    mock_db = MagicMock()
    mock_db.__enter__.return_value = mock_db
    mock_db.__exit__.return_value = None
    mock_db.query.return_value.order_by.return_value.limit.return_value.all.return_value = []

    with patch("app.gui.bridge.SessionLocal", return_value=mock_db):
        await bridge._handle_fetch_stats()

    events = bridge.poll_events()
    stats_event = next((e for e in events if e.get("event") == "STATS_LOADED"), None)
    assert stats_event is not None
    data = stats_event["data"]
    assert data["total_runs"] == 0
    assert data["total_enrolled"] == 0
    assert data["total_saved"] == 0.0
    assert data["runs"] == []


def test_gui_poll_teardown_error_absorbed():
    """Verify that when self.after raises during window destruction, _poll_bridge_events absorbs it cleanly."""
    from app.gui.app import UdemyEnrollerApp

    mock_app = MagicMock()
    mock_app.bridge = MagicMock()
    mock_app.bridge.poll_events.return_value = []
    # Simulate TclError when after is invoked on destroyed window
    mock_app.after.side_effect = Exception("application has been destroyed")

    # Should not raise exception
    UdemyEnrollerApp._poll_bridge_events(mock_app)
    assert mock_app.after.called

