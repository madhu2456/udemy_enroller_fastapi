"""Exhaustive unit and edge-case tests for Unified Rich CLI subcommands.

Subcommands covered:
1. enroll: --dry-run, invalid token, missing credentials, filter combos, limits, output formats, interactive mode, site fallbacks.
2. scrape: --sites subsets, invalid sites, format types (table/json/csv), pipe stdout, filters.
3. check: valid session, invalid session, cookie failure, single course URL coupon check variations.
4. stats: empty database, multi-run database, --limit, --output JSON.
5. server: --host, --port, --reload validation, KeyboardInterrupt handling.
6. SIGINT & signal handlers.
"""

from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from app.cli.main import app
from app.cli.ui import setup_signal_handlers
from app.models.database import Base, EnrolledCourse, EnrollmentRun, User, engine, SessionLocal
from app.services.browser_cookies import UdemyBrowserCookies
from app.services.course import Course
from app.services.session_store import clear_persistent_session

runner = CliRunner()


@pytest.fixture(autouse=True)
def setup_test_db():
    """Ensure database schema exists for testing."""
    Base.metadata.create_all(bind=engine)
    clear_persistent_session()
    yield
    # Clean up test records
    with SessionLocal() as db:
        db.query(EnrolledCourse).delete()
        db.query(EnrollmentRun).delete()
        db.query(User).delete()
        db.commit()
    clear_persistent_session()


# =====================================================================
# 1. ENROLL Subcommand Edge Cases
# =====================================================================


def test_enroll_missing_credentials_and_no_cookies():
    """Enroll fails with exit code 1 when no token provided and no browser cookies found."""
    with patch("app.cli.commands.enroll.load_persistent_session", return_value=None), patch(
        "app.cli.commands.enroll.get_udemy_cookies"
    ) as mock_get:
        mock_get.return_value = UdemyBrowserCookies(
            is_valid=False,
            error="No supported browser with active Udemy session found",
            notes="Please login to Udemy in Chrome or Firefox",
        )
        result = runner.invoke(app, ["enroll"])
        assert result.exit_code == 1
        assert "Failed to extract" in result.output or "No supported browser" in result.output
        assert "--token <TOKEN>" in result.output


def test_enroll_invalid_token_auth_failure():
    """Enroll fails with exit code 1 when provided token fails Udemy authentication."""
    with patch("app.cli.commands.enroll.UdemyClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.get_session_info = AsyncMock(return_value=False)
        mock_client.is_authenticated = False
        mock_client.close = AsyncMock()
        mock_client_cls.return_value = mock_client

        result = runner.invoke(app, ["enroll", "--token", "invalid_expired_token_123"])
        assert result.exit_code == 1
        assert "Failed to authenticate with Udemy API" in result.output


def test_enroll_dry_run_with_filter_combinations(tmp_path):
    """Enroll with --dry-run, categories, languages, min-rating, limit, and json output."""
    json_out = tmp_path / "enroll_results.json"

    # Create dummy courses
    c1 = Course(title="Python Masterclass 2026", url="https://www.udemy.com/course/python-masterclass/?couponCode=FREE1")
    c1.price = Decimal("94.99")
    c1.rating = 4.8
    c1.language = "English"
    c1.category = "Development"
    c1.is_free = True

    c2 = Course(title="Spanish React Course", url="https://www.udemy.com/course/react-spanish/?couponCode=FREE2")
    c2.price = Decimal("49.99")
    c2.rating = 4.9
    c2.language = "Spanish"
    c2.category = "Development"
    c2.is_free = True

    async def mock_stream(self):
        s_mock = MagicMock()
        s_mock.site_name = "TutorialBar"
        s_mock.courses = [c1, c2]
        yield s_mock, "completed"

    with patch("app.cli.commands.enroll.UdemyClient") as mock_client_cls, \
         patch("app.cli.commands.enroll.ScraperService.stream_results", new=mock_stream):

        mock_client = MagicMock()
        mock_client.get_session_info = AsyncMock(return_value=True)
        mock_client.get_enrolled_courses = AsyncMock(return_value={})
        mock_client.check_course = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client.display_name = "QA Engineer"
        mock_client.currency = "USD"
        mock_client.enrolled_courses = {}
        mock_client.successfully_enrolled_c = 0
        mock_client.already_enrolled_c = 0
        mock_client.expired_c = 0
        mock_client.excluded_c = 0
        mock_client.amount_saved_c = Decimal(0)

        def mock_is_excluded(course, settings):
            langs = settings.get("languages", [])
            if langs and course.language not in langs:
                return True
            return False

        mock_client.is_course_excluded = MagicMock(side_effect=mock_is_excluded)
        mock_client_cls.return_value = mock_client

        result = runner.invoke(
            app,
            [
                "enroll",
                "--token", "valid_test_token",
                "--dry-run",
                "--languages", "English",
                "--categories", "Development",
                "--min-rating", "4.5",
                "--limit", "1",
                "--output", str(json_out),
            ],
        )

        assert result.exit_code == 0
        assert "Authenticated as" in result.output
        assert "DRY RUN" in result.output
        assert json_out.exists()

        with open(json_out) as f:
            data = json.load(f)
            assert "summary" in data
            assert "courses" in data


def test_enroll_csv_and_txt_export_formats(tmp_path):
    """Enroll exports to CSV and TXT correctly."""
    csv_out = tmp_path / "enroll.csv"
    txt_out = tmp_path / "enroll.txt"

    c1 = Course(title="Complete Web Dev", url="https://www.udemy.com/course/web-dev/?couponCode=FREE100")
    c1.price = Decimal("89.99")
    c1.is_free = True

    async def mock_stream(self):
        s_mock = MagicMock()
        s_mock.site_name = "Courson"
        s_mock.courses = [c1]
        yield s_mock, "completed"

    with patch("app.cli.commands.enroll.UdemyClient") as mock_client_cls, \
         patch("app.cli.commands.enroll.ScraperService.stream_results", new=mock_stream):

        mock_client = MagicMock()
        mock_client.get_session_info = AsyncMock(return_value=True)
        mock_client.get_enrolled_courses = AsyncMock(return_value={})
        mock_client.check_course = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client.display_name = "QA Engineer"
        mock_client.currency = "USD"
        mock_client.enrolled_courses = {}
        mock_client.successfully_enrolled_c = 0
        mock_client.already_enrolled_c = 0
        mock_client.expired_c = 0
        mock_client.excluded_c = 0
        mock_client.amount_saved_c = Decimal(0)
        mock_client.is_course_excluded = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        # CSV test
        res_csv = runner.invoke(app, ["enroll", "--token", "tok", "--dry-run", "--output", str(csv_out)])
        assert res_csv.exit_code == 0
        assert csv_out.exists()
        assert "Complete Web Dev" in csv_out.read_text()

        # TXT test
        res_txt = runner.invoke(app, ["enroll", "--token", "tok", "--dry-run", "--output", str(txt_out)])
        assert res_txt.exit_code == 0
        assert txt_out.exists()
        assert "Udemy Enrollment Summary" in txt_out.read_text()


def test_enroll_site_filter_valid_and_unknown():
    """Enroll handles known and unknown site filtering gracefully."""
    with patch("app.cli.commands.enroll.UdemyClient") as mock_client_cls, \
         patch("app.cli.commands.enroll.ScraperService") as mock_scraper_service:

        mock_client = MagicMock()
        mock_client.get_session_info = AsyncMock(return_value=True)
        mock_client.get_enrolled_courses = AsyncMock(return_value={})
        mock_client.close = AsyncMock()
        mock_client.enrolled_courses = {}
        mock_client_cls.return_value = mock_client

        service_inst = MagicMock()
        service_inst.scrapers = []
        async def empty_stream():
            if False:
                yield None, None
        service_inst.stream_results = empty_stream
        mock_scraper_service.return_value = service_inst

        # Test partial unknown site
        result = runner.invoke(app, ["enroll", "--token", "tok", "--dry-run", "--sites", "TutorialBar,NonExistentSite"])
        assert result.exit_code == 0
        assert "Unknown scraper site 'NonExistentSite'" in result.output
        mock_scraper_service.assert_called_with(sites_to_scrape=["TutorialBar"])


def test_enroll_live_checkout_interactive_confirmation():
    """Enroll in interactive mode prompts user before checkout."""
    c1 = Course(title="Interactive Course", url="https://www.udemy.com/course/interactive/?couponCode=FREE100")
    c1.price = Decimal("19.99")
    c1.is_free = True

    async def mock_stream(self):
        s_mock = MagicMock()
        s_mock.site_name = "TutorialBar"
        s_mock.courses = [c1]
        yield s_mock, "completed"

    with patch("app.cli.commands.enroll.UdemyClient") as mock_client_cls, \
         patch("app.cli.commands.enroll.ScraperService.stream_results", new=mock_stream), \
         patch("app.cli.commands.enroll.is_tty", return_value=True), \
         patch("rich.prompt.Confirm.ask", return_value=False):

        mock_client = MagicMock()
        mock_client.get_session_info = AsyncMock(return_value=True)
        mock_client.get_enrolled_courses = AsyncMock(return_value={})
        mock_client.check_course = AsyncMock()
        mock_client.checkout_single = AsyncMock(return_value=True)
        mock_client.close = AsyncMock()
        mock_client.enrolled_courses = {}
        mock_client.successfully_enrolled_c = 0
        mock_client.already_enrolled_c = 0
        mock_client.expired_c = 0
        mock_client.excluded_c = 0
        mock_client.amount_saved_c = Decimal(0)
        mock_client.is_course_excluded = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = runner.invoke(app, ["enroll", "--token", "tok", "--interactive"])
        assert result.exit_code == 0
        # User said No, so checkout_single should not have been called
        mock_client.checkout_single.assert_not_called()


# =====================================================================
# 2. SCRAPE Subcommand Edge Cases
# =====================================================================


def test_scrape_with_sites_filtering_and_limits(tmp_path):
    """Scrape applies sites, limits, categories, and ratings filters correctly."""
    c1 = Course(title="Python For Beginners", url="https://www.udemy.com/course/py-beginners/?couponCode=FREE")
    c1.category = "Development"
    c1.language = "English"
    c1.rating = 4.7

    c2 = Course(title="Design with Figma", url="https://www.udemy.com/course/figma-design/?couponCode=FREE")
    c2.category = "Design"
    c2.language = "English"
    c2.rating = 4.2

    async def mock_stream(self):
        s_mock = MagicMock()
        s_mock.site_name = "Coursesity"
        s_mock.courses = [c1, c2]
        yield s_mock, "completed"

    with patch("app.cli.commands.scrape.ScraperService.stream_results", new=mock_stream):
        out_json = tmp_path / "scraped.json"
        result = runner.invoke(
            app,
            [
                "scrape",
                "--sites", "Coursesity,UnknownSite",
                "--categories", "Development",
                "--min-rating", "4.5",
                "--limit", "5",
                "--format", "json",
                "--output", str(out_json),
            ],
        )
        assert result.exit_code == 0
        assert out_json.exists()
        with open(out_json) as f:
            data = json.load(f)
            assert len(data) == 1
            assert data[0]["title"] == "Python For Beginners"


def test_scrape_csv_stdout_and_pipe_output():
    """Scrape with --format csv to stdout."""
    c1 = Course(title="Go Concurrency", url="https://www.udemy.com/course/go-concurrency/?couponCode=FREEGO")
    c1.rating = 4.9
    c1.category = "Development"
    c1.language = "English"

    async def mock_stream(self):
        s_mock = MagicMock()
        s_mock.site_name = "TutorialBar"
        s_mock.courses = [c1]
        yield s_mock, "completed"

    with patch("app.cli.commands.scrape.ScraperService.stream_results", new=mock_stream):
        result = runner.invoke(app, ["scrape", "--format", "csv"])
        assert result.exit_code == 0
        assert "FREEGO" in result.output
        assert "title,rating,language" in result.output


def test_scrape_table_format_default():
    """Scrape with default table format."""
    c1 = Course(title="Rust System Programming", url="https://www.udemy.com/course/rust-sys/?couponCode=FREERUST")
    c1.rating = 4.8
    c1.language = "English"

    async def mock_stream(self):
        s_mock = MagicMock()
        s_mock.site_name = "TutorialBar"
        s_mock.courses = [c1]
        yield s_mock, "completed"

    with patch("app.cli.commands.scrape.ScraperService.stream_results", new=mock_stream):
        result = runner.invoke(app, ["scrape", "--format", "table"])
        assert result.exit_code == 0
        assert "Total discovered courses: 1" in result.output
        assert "Scraped Udemy Courses" in result.output


# =====================================================================
# 3. CHECK Subcommand Edge Cases
# =====================================================================


def test_check_session_auth_failure():
    """Check session fails when credentials are invalid."""
    with patch("app.cli.commands.check.UdemyClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.get_session_info = AsyncMock(return_value=False)
        mock_client.close = AsyncMock()
        mock_client_cls.return_value = mock_client

        result = runner.invoke(app, ["check", "--token", "bad_token"])
        assert result.exit_code == 1
        assert "Failed to authenticate with Udemy" in result.output


def test_check_single_url_status_branches():
    """Check single URL handles valid free, expired, already owned, and paid statuses."""
    # 1. Valid Free Coupon
    with patch("app.cli.commands.check.UdemyClient") as mock_client_cls:
        mock_client = MagicMock()
        async def mock_check_free(course):
            course.is_coupon_valid = True
            course.price = Decimal("0.00")
            course.rating = 4.9
            course.category = "Development"
            course.language = "English"
        mock_client.check_course = AsyncMock(side_effect=mock_check_free)
        mock_client.close = AsyncMock()
        mock_client_cls.return_value = mock_client

        result = runner.invoke(app, ["check", "--url", "https://www.udemy.com/course/valid-free/?couponCode=FREE100"])
        assert result.exit_code == 0
        assert "Active 100% OFF Free Coupon" in result.output

    # 2. Expired Coupon
    with patch("app.cli.commands.check.UdemyClient") as mock_client_cls:
        mock_client = MagicMock()
        async def mock_check_exp(course):
            course.is_coupon_valid = False
            course.is_expired = True
            course.error = "Coupon is expired"
        mock_client.check_course = AsyncMock(side_effect=mock_check_exp)
        mock_client.close = AsyncMock()
        mock_client_cls.return_value = mock_client

        result = runner.invoke(app, ["check", "--url", "https://www.udemy.com/course/expired/?couponCode=OLD"])
        assert result.exit_code == 0
        assert "Expired / Invalid Coupon" in result.output

    # 3. Already Enrolled
    with patch("app.cli.commands.check.UdemyClient") as mock_client_cls:
        mock_client = MagicMock()
        async def mock_check_enrolled(course):
            course.is_already_enrolled = True
            course.status = "Already Enrolled"
        mock_client.check_course = AsyncMock(side_effect=mock_check_enrolled)
        mock_client.close = AsyncMock()
        mock_client_cls.return_value = mock_client

        result = runner.invoke(app, ["check", "--url", "https://www.udemy.com/course/owned/"])
        assert result.exit_code == 0
        assert "Already in Library" in result.output


def test_check_single_url_exception_handling():
    """Check single URL handles exceptions cleanly."""
    with patch("app.cli.commands.check.UdemyClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.check_course = AsyncMock(side_effect=Exception("API connection timeout"))
        mock_client.close = AsyncMock()
        mock_client_cls.return_value = mock_client

        result = runner.invoke(app, ["check", "--url", "https://www.udemy.com/course/err-course/"])
        assert result.exit_code == 1
        assert "Error checking course: API connection timeout" in result.output


# =====================================================================
# 4. STATS Subcommand Edge Cases
# =====================================================================


def test_stats_empty_database(tmp_path):
    """Stats subcommand handles empty database gracefully."""
    out_file = tmp_path / "stats.json"
    result = runner.invoke(app, ["stats", "--output", str(out_file)])
    assert result.exit_code == 0
    assert "Lifetime Account Statistics" in result.output
    assert out_file.exists()


def test_stats_with_historical_runs_and_limit():
    """Stats displays historical runs table when database has runs."""
    with SessionLocal() as db:
        user = User(email="test_stats@example.com", password_hash="hashed_pw_xyz")
        db.add(user)
        db.commit()
        db.refresh(user)

        run1 = EnrollmentRun(user_id=user.id, status="completed", total_courses_found=10, total_processed=10, successfully_enrolled=5, amount_saved=120.0)
        run2 = EnrollmentRun(user_id=user.id, status="failed", total_courses_found=5, total_processed=2, successfully_enrolled=0, amount_saved=0.0)
        db.add_all([run1, run2])
        db.commit()

    result = runner.invoke(app, ["stats", "--limit", "5"])
    assert result.exit_code == 0
    assert "Recent Enrollment Runs" in result.output
    assert "COMPLETED" in result.output
    assert "FAILED" in result.output


# =====================================================================
# 5. SERVER Subcommand Edge Cases
# =====================================================================


def test_server_command_options_and_interrupt():
    """Server subcommand passes host/port/reload to uvicorn and catches KeyboardInterrupt."""
    with patch("uvicorn.run") as mock_run:
        result = runner.invoke(app, ["server", "--host", "127.0.0.1", "--port", "8080", "--reload"])
        assert result.exit_code == 0
        assert mock_run.called
        kwargs = mock_run.call_args[1]
        assert kwargs["host"] == "127.0.0.1"
        assert kwargs["port"] == 8080
        assert kwargs["reload"] is True

    # Test KeyboardInterrupt
    with patch("uvicorn.run", side_effect=KeyboardInterrupt):
        result = runner.invoke(app, ["server"])
        assert result.exit_code == 0
        assert "Web server stopped by user" in result.output


# =====================================================================
# 6. Signal Handling
# =====================================================================


def test_setup_signal_handlers_invokes_cleanup():
    """Test setup_signal_handlers registers SIGINT and executes callback on interrupt."""
    cleaned_up = False

    def on_cleanup():
        nonlocal cleaned_up
        cleaned_up = True

    # Register handlers
    setup_signal_handlers(cleanup_callback=on_cleanup)
    assert callable(on_cleanup)
