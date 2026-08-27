"""Unit tests for persistent encrypted session storage and automatic session restoration."""

from unittest.mock import AsyncMock, patch
import pytest
from typer.testing import CliRunner

from app.cli.main import app as cli_app
from app.gui.bridge import AsyncioBridge
from app.services.session_store import (
    clear_persistent_session,
    load_persistent_session,
    save_persistent_session,
    verify_and_restore_session,
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_session():
    """Ensure session is clean before and after each test."""
    clear_persistent_session()
    yield
    clear_persistent_session()


def test_save_and_load_persistent_session_roundtrip():
    """Verify that credentials can be saved, encrypted, and loaded cleanly."""
    cookies = {
        "access_token": "test_access_token_12345",
        "client_id": "test_client_id_67890",
        "csrf_token": "test_csrf_token_abcde",
    }
    saved = save_persistent_session(cookies=cookies, display_name="Madhu Dadi", user_id="40960386", currency="INR")
    assert saved is True

    loaded = load_persistent_session()
    assert loaded is not None
    assert loaded["access_token"] == "test_access_token_12345"
    assert loaded["client_id"] == "test_client_id_67890"
    assert loaded["csrf_token"] == "test_csrf_token_abcde"
    assert loaded["display_name"] == "Madhu Dadi"
    assert loaded["currency"] == "INR"


def test_save_empty_token_returns_false():
    """Verify that saving empty token is rejected."""
    assert save_persistent_session(cookies={"access_token": ""}) is False


def test_clear_persistent_session():
    """Verify that clear_persistent_session wipes both DB and file backup."""
    cookies = {
        "access_token": "test_access_token_to_clear",
        "client_id": "test_cid",
        "csrf_token": "test_csrf",
    }
    save_persistent_session(cookies=cookies, display_name="To Clear")
    assert load_persistent_session() is not None

    clear_persistent_session()
    assert load_persistent_session() is None


@pytest.mark.asyncio
async def test_verify_and_restore_session_valid():
    """Verify verify_and_restore_session with valid active session."""
    cookies = {
        "access_token": "valid_token",
        "client_id": "valid_cid",
        "csrf_token": "valid_csrf",
    }
    save_persistent_session(cookies=cookies, display_name="Madhu Dadi")

    with patch("app.services.session_store.UdemyClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.is_authenticated = True
        mock_client.display_name = "Madhu Dadi"
        mock_client.udemy_user_id = "40960386"
        mock_client.currency = "INR"
        mock_client.enrolled_courses = {"course-1": "id1", "course-2": "id2"}
        mock_client.get_session_info = AsyncMock(return_value=True)
        mock_client.get_enrolled_courses = AsyncMock(return_value={"course-1": "id1"})
        mock_client.close = AsyncMock()

        is_valid, client, session_data, err = await verify_and_restore_session()
        assert is_valid is True
        assert session_data is not None
        assert session_data["display_name"] == "Madhu Dadi"
        assert session_data["library_count"] == 2
        assert session_data["is_saved"] is True
        assert err is None


@pytest.mark.asyncio
async def test_verify_and_restore_session_expired():
    """Verify verify_and_restore_session properly identifies expired session."""
    cookies = {
        "access_token": "expired_token",
        "client_id": "expired_cid",
        "csrf_token": "expired_csrf",
    }
    save_persistent_session(cookies=cookies, display_name="Madhu Dadi")

    with patch("app.services.session_store.UdemyClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.is_authenticated = False
        mock_client.get_session_info = AsyncMock(return_value=False)
        mock_client.close = AsyncMock()

        is_valid, client, session_data, err = await verify_and_restore_session()
        assert is_valid is False
        assert session_data is not None  # Retains expired payload for user notification
        assert "expired" in err.lower()


@pytest.mark.asyncio
async def test_verify_and_restore_session_no_saved():
    """Verify verify_and_restore_session when no session is saved."""
    clear_persistent_session()
    is_valid, client, session_data, err = await verify_and_restore_session()
    assert is_valid is False
    assert session_data is None
    assert "No saved session" in err


@pytest.mark.asyncio
async def test_bridge_restore_saved_session_lifecycle():
    """Test that AsyncioBridge correctly emits events on RESTORE_SAVED_SESSION."""
    cookies = {
        "access_token": "mock_token",
        "client_id": "mock_cid",
        "csrf_token": "mock_csrf",
    }
    save_persistent_session(cookies=cookies, display_name="Madhu Dadi")

    bridge = AsyncioBridge()
    with patch("app.gui.bridge.verify_and_restore_session") as mock_verify:
        mock_verify.return_value = (
            True,
            None,
            {
                "display_name": "Madhu Dadi",
                "library_count": 100,
                "currency": "INR",
                "access_token": "mock_token",
                "client_id": "mock_cid",
                "csrf_token": "mock_csrf",
                "is_saved": True,
            },
            None,
        )

        await bridge._handle_restore_saved_session({})
        events = bridge.poll_events()
        event_types = [e["event"] for e in events]
        assert "AUTH_SUCCESS" in event_types
        assert "LOG" in event_types


@pytest.mark.asyncio
async def test_bridge_clear_saved_session():
    """Test that AsyncioBridge correctly handles CLEAR_SAVED_SESSION."""
    save_persistent_session(cookies={"access_token": "token123"}, display_name="Test")
    assert load_persistent_session() is not None

    bridge = AsyncioBridge()
    await bridge._handle_clear_saved_session()
    assert load_persistent_session() is None
    events = bridge.poll_events()
    event_types = [e["event"] for e in events]
    assert "AUTH_FAILED" in event_types


def test_cli_enroll_with_saved_session():
    """Test that cli enroll automatically uses saved session when flags are absent."""
    save_persistent_session(
        cookies={"access_token": "saved_cli_token", "client_id": "saved_cid", "csrf_token": "saved_csrf"},
        display_name="Madhu Dadi",
    )

    with patch("app.cli.commands.enroll.UdemyClient") as mock_udemy_cls, patch(
        "app.cli.commands.enroll.ScraperService"
    ) as mock_scraper_cls:
        mock_instance = mock_udemy_cls.return_value
        mock_instance.get_session_info = AsyncMock(return_value=True)
        mock_instance.get_enrolled_courses = AsyncMock(return_value={"c1": "1"})
        mock_instance.display_name = "Madhu Dadi"
        mock_instance.currency = "inr"
        mock_instance.udemy_user_id = "40960386"
        mock_instance.close = AsyncMock()

        mock_scraper = mock_scraper_cls.return_value
        mock_scraper.scrape_all = AsyncMock(return_value={})
        mock_scraper.courses = []

        result = runner.invoke(cli_app, ["enroll", "--dry-run", "--limit", "1", "--sites", "FreeCourseSites"])
        assert result.exit_code == 0
        assert "Using saved session credentials" in result.output or "Authenticated as Madhu Dadi" in result.output
