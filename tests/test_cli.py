"""Unit tests for Unified Rich CLI application."""

import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from app.cli.main import app
from app.services.browser_cookies import UdemyBrowserCookies
from app.services.course import Course

runner = CliRunner()


def test_cli_version():
    """Test the --version flag."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "Udemy Enroller" in result.output
    assert "v2.2.0" in result.output


def test_cli_help():
    """Test the top-level --help command."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "enroll" in result.output
    assert "scrape" in result.output
    assert "check" in result.output
    assert "stats" in result.output
    assert "server" in result.output


def test_enroll_missing_cookies():
    """Test enroll fails gracefully when no cookies/tokens are available."""
    with patch("app.cli.commands.enroll.load_persistent_session", return_value=None), \
         patch("app.cli.commands.enroll.get_udemy_cookies") as mock_get_cookies:
        mock_get_cookies.return_value = UdemyBrowserCookies(
            is_valid=False,
            error="No supported browser with active Udemy session found",
        )
        result = runner.invoke(app, ["enroll"])
        assert result.exit_code == 1
        assert "Failed to extract" in result.output or "No supported browser" in result.output


def test_enroll_dry_run_success(tmp_path):
    """Test enroll with --dry-run and mocked UdemyClient and ScraperService."""
    json_out = tmp_path / "results.json"

    dummy_course = Course(
        title="Python Mastery 2026",
        url="https://www.udemy.com/course/python-mastery/?couponCode=FREE100",
    )
    dummy_course.price = Decimal("84.99")
    dummy_course.rating = 4.8
    dummy_course.language = "English"
    dummy_course.category = "Development"
    dummy_course.is_free = True
    dummy_course.is_already_enrolled = False
    dummy_course.is_expired = False

    async def mock_stream(self):
        scraper_mock = MagicMock()
        scraper_mock.site_name = "Real Discount"
        scraper_mock.courses = [dummy_course]
        yield scraper_mock, "completed"

    with patch("app.cli.commands.enroll.get_udemy_cookies") as mock_get_cookies, \
         patch("app.cli.commands.enroll.UdemyClient") as mock_client_cls, \
         patch("app.cli.commands.enroll.ScraperService.stream_results", new=mock_stream):

        mock_get_cookies.return_value = UdemyBrowserCookies(
            is_valid=True,
            access_token="mock_valid_access_token",
            client_id="mock_cid",
            csrf_token="mock_csrf",
            browser_name="chrome",
        )

        mock_client = MagicMock()
        mock_client.get_session_info = AsyncMock(return_value=True)
        mock_client.get_enrolled_courses = AsyncMock(return_value={})
        mock_client.check_course = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client.display_name = "Test Learner"
        mock_client.currency = "USD"
        mock_client.enrolled_courses = {}
        mock_client.successfully_enrolled_c = 0
        mock_client.already_enrolled_c = 0
        mock_client.expired_c = 0
        mock_client.excluded_c = 0
        mock_client.amount_saved_c = Decimal(0)
        mock_client.is_course_excluded = MagicMock(return_value=False)

        mock_client_cls.return_value = mock_client

        result = runner.invoke(
            app,
            [
                "enroll",
                "--token",
                "manual_token_123",
                "--dry-run",
                "--output",
                str(json_out),
            ],
        )

        assert result.exit_code == 0
        assert "Authenticated as" in result.output
        assert "DRY RUN" in result.output
        assert json_out.exists()


def test_scrape_json_format(tmp_path):
    """Test scrape subcommand with JSON output format."""
    dummy_course = Course(
        title="Learn FastAPI",
        url="https://www.udemy.com/course/fastapi/?couponCode=FREEFAST",
    )
    dummy_course.rating = 4.9
    dummy_course.language = "English"
    dummy_course.category = "Development"

    async def mock_stream(self):
        scraper_mock = MagicMock()
        scraper_mock.site_name = "TutorialBar"
        scraper_mock.courses = [dummy_course]
        yield scraper_mock, "completed"

    with patch("app.cli.commands.scrape.ScraperService.stream_results", new=mock_stream):
        out_file = tmp_path / "scraped.json"
        result = runner.invoke(
            app,
            ["scrape", "--format", "json", "--output", str(out_file)],
        )

        assert result.exit_code == 0
        assert out_file.exists()
        with open(out_file) as f:
            data = json.load(f)
            assert len(data) == 1
            assert data[0]["title"] == "Learn FastAPI"


def test_scrape_csv_format(tmp_path):
    """Test scrape subcommand with CSV output format."""
    dummy_course = Course(
        title="Learn Docker",
        url="https://www.udemy.com/course/docker/?couponCode=FREEDOCKER",
    )
    dummy_course.rating = 4.7
    dummy_course.language = "English"
    dummy_course.category = "DevOps"

    async def mock_stream(self):
        scraper_mock = MagicMock()
        scraper_mock.site_name = "E-next"
        scraper_mock.courses = [dummy_course]
        yield scraper_mock, "completed"

    with patch("app.cli.commands.scrape.ScraperService.stream_results", new=mock_stream):
        out_file = tmp_path / "scraped.csv"
        result = runner.invoke(
            app,
            ["scrape", "--format", "csv", "--output", str(out_file)],
        )

        assert result.exit_code == 0
        assert out_file.exists()
        content = out_file.read_text()
        assert "Learn Docker" in content


def test_check_valid_session():
    """Test check command with valid session."""
    with patch("app.cli.commands.check.UdemyClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.get_session_info = AsyncMock(return_value=True)
        mock_client.get_enrolled_courses = AsyncMock(return_value={})
        mock_client.close = AsyncMock()
        mock_client.display_name = "Alice Student"
        mock_client.currency = "USD"
        mock_client.udemy_user_id = "123456"
        mock_client_cls.return_value = mock_client

        result = runner.invoke(app, ["check", "--token", "test_valid_token"])
        assert result.exit_code == 0
        assert "AUTHENTICATED" in result.output
        assert "Alice Student" in result.output


def test_check_single_url():
    """Test check command with specific course URL."""
    with patch("app.cli.commands.check.UdemyClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.check_course = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client_cls.return_value = mock_client

        result = runner.invoke(
            app,
            ["check", "--url", "https://www.udemy.com/course/sample-course/?couponCode=FREE100"],
        )
        assert result.exit_code == 0
        assert "Checking Udemy Coupon URL" in result.output


def test_stats_command(tmp_path):
    """Test stats command output and JSON export."""
    out_file = tmp_path / "stats.json"
    result = runner.invoke(app, ["stats", "--output", str(out_file)])
    assert result.exit_code == 0
    assert "Lifetime Account Statistics" in result.output
    assert out_file.exists()


def test_server_command():
    """Test server command invoking uvicorn.run."""
    with patch("uvicorn.run") as mock_uvicorn_run:
        result = runner.invoke(app, ["server", "--host", "127.0.0.1", "--port", "9000"])
        assert result.exit_code == 0
        assert mock_uvicorn_run.called
        call_kwargs = mock_uvicorn_run.call_args[1]
        assert call_kwargs["host"] == "127.0.0.1"
        assert call_kwargs["port"] == 9000


def test_login_command_success():
    """Test login command authenticating and persisting session."""
    with patch("app.cli.commands.login.UdemyClient") as mock_client_cls, \
         patch("app.cli.commands.login.save_persistent_session") as mock_save:
        mock_client = MagicMock()
        mock_client.cookie_login = MagicMock()
        mock_client.get_session_info = AsyncMock(return_value=True)
        mock_client.get_enrolled_courses = AsyncMock(return_value={"c1": "1"})
        mock_client.display_name = "Madhu Dadi"
        mock_client.udemy_user_id = "40960386"
        mock_client.currency = "INR"
        mock_client.enrolled_courses = {"c1": "1"}
        mock_client.close = AsyncMock()
        mock_client_cls.return_value = mock_client

        result = runner.invoke(app, ["login", "--token", "test_valid_tok", "--client-id", "cid123", "--csrf", "csrf123"])
        assert result.exit_code == 0
        assert "Madhu Dadi" in result.output
        assert "SAVED" in result.output
        assert mock_save.called


def test_login_command_auth_failure():
    """Test login command failing when credentials are invalid."""
    with patch("app.cli.commands.login.UdemyClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.cookie_login = MagicMock()
        mock_client.get_session_info = AsyncMock(return_value=False)
        mock_client.close = AsyncMock()
        mock_client_cls.return_value = mock_client

        result = runner.invoke(app, ["login", "--token", "bad_token"])
        assert result.exit_code == 1
        assert "Failed to authenticate" in result.output


def test_logout_command():
    """Test logout command wiping persistent session."""
    with patch("app.cli.commands.logout.clear_persistent_session") as mock_clear:
        result = runner.invoke(app, ["logout"])
        assert result.exit_code == 0
        assert "cleared" in result.output.lower()
        assert mock_clear.called

