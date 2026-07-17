import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.udemy_client import UdemyClient
from app.services.course import Course
from app.services.scraper import IDownloadCouponScraper
from app.services.enrollment_manager import EnrollmentManager

@pytest.mark.asyncio
async def test_udemy_client_locale_fallback():
    """Test that simple_english_title is properly extracted from locale objects."""
    client = UdemyClient()
    course = Course(title="Test Course", url="https://udemy.com/course/test", site="FreeWebCart")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_json = {
        "id": 12345,
        "locale": {
            "locale": "en_US",
            "simple_english_title": "English",
            "english_title": "English"
        }
    }

    with patch.object(client.http, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response
        with patch.object(client.http, "safe_json", new_callable=AsyncMock) as mock_safe_json:
            mock_safe_json.return_value = mock_json

            await client.get_course_id(course)

            assert course.language == "English"
            assert course.course_id == "12345"

    await client.close()



@pytest.mark.asyncio
async def test_idownloadcoupon_semaphore_enforcement():
    """Test that iDownloadCoupon uses a local detail semaphore."""
    scraper = IDownloadCouponScraper(http=AsyncMock())

    with patch("app.services.scraper.asyncio.Semaphore") as mock_sem:
        # Mock the local semaphore instance
        mock_sem_instance = AsyncMock()
        mock_sem_instance.__aenter__ = AsyncMock()
        mock_sem_instance.__aexit__ = AsyncMock()
        mock_sem.return_value = mock_sem_instance

        # Override listing fetch
        with patch.object(scraper.http, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = MagicMock(status_code=200, text="")

            # Prevent detail tasks from actually running
            with patch.object(scraper, "_run_detail_task", new_callable=AsyncMock):
                global_sem = asyncio.Semaphore(50)
                await scraper.scrape(global_sem)

                # Should have instantiated Semaphore(8) locally inside scrape()
                mock_sem.assert_any_call(8)

@pytest.mark.asyncio
async def test_telemetry_status_assignment(monkeypatch):
    """Test that EnrollmentManager correctly maps and passes status telemetry."""
    mock_export = MagicMock(return_value=0)
    monkeypatch.setattr(
        "app.services.public_deals_export.export_public_deals_json", mock_export
    )

    udemy_mock = MagicMock()
    udemy_mock.currency = "usd"
    udemy_mock.is_authenticated = True
    udemy_mock.enrolled_courses = {}
    # Mock checkout to succeed for the first course, and fail for the second
    udemy_mock.checkout_single = AsyncMock(side_effect=[True, False])
    udemy_mock.get_session_health_report = MagicMock(return_value={})
    udemy_mock.get_enrolled_courses = AsyncMock()
    udemy_mock.is_already_enrolled = AsyncMock(return_value=False)
    udemy_mock.get_course_id = AsyncMock()
    udemy_mock.check_already_enrolled_live = AsyncMock(return_value=False)
    udemy_mock.populate_course_metadata = AsyncMock()
    udemy_mock.check_course = AsyncMock()
    udemy_mock.is_course_excluded = MagicMock()

    manager = EnrollmentManager(user_id=1, run_id=1, udemy_client=udemy_mock, settings={"sites": {"FreeWebCart": True}})

    course1 = Course("Title 1", "https://udemy.com/course/1/", "FreeWebCart")
    course1.course_id = "1"
    course1.is_valid = True
    course1.is_coupon_valid = True
    course1.is_free = False

    course2 = Course("Title 2", "https://udemy.com/course/2/", "FreeWebCart")
    course2.course_id = "2"
    course2.is_valid = True
    course2.is_coupon_valid = True
    course2.is_free = False
    course2.error = "price mismatch"

    # Mock scraper service with async generator
    mock_scraper = MagicMock()
    mock_scraper.data = [course1, course2]

    async def mock_stream_results():
        yield mock_scraper, "completed"

    mock_scraper_service = MagicMock()
    mock_scraper_service.stream_results = mock_stream_results
    mock_scraper_service.get_progress = MagicMock(return_value=[])

    manager._save_course = AsyncMock()
    manager._update_run_stats = AsyncMock()

    mock_db = MagicMock()
    mock_run = MagicMock()
    mock_run.progress_data = {}
    mock_run.status = "scraping"
    mock_db.get.return_value = mock_run
    mock_db.execute.return_value = []

    with patch("app.services.enrollment_manager.SessionLocal") as mock_session:
        mock_session.return_value = mock_db
        with patch("app.services.enrollment_manager.ScraperService", return_value=mock_scraper_service):
            with patch("app.services.enrollment_manager._utcnow_naive"):
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    await manager._run_pipeline_impl()

                    # Verify that _save_course was called for both courses
                    assert manager._save_course.call_count == 2
                    mock_export.assert_called_once_with(mock_db)
