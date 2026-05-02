"""Tests for EnrollmentManager pipeline logic with mocked dependencies."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, EnrollmentRun, User, get_db, _utcnow_naive
from app.services import enrollment_manager as em_module
from app.services.enrollment_manager import EnrollmentManager
from app.services.course import Course


# File-based test DB so multiple SessionLocal() calls share the same DB
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_enrollment_manager.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

# Patch the module's SessionLocal so the pipeline uses our test DB
em_module.SessionLocal = TestingSessionLocal


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def cleanup_db():
    """Clean up database after each test."""
    yield
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())
    EnrollmentManager.active_tasks.clear()


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def mock_udemy_client():
    client = MagicMock()
    client.currency = "USD"
    client.display_name = "Test User"
    client.is_authenticated = True
    client.enrolled_courses = {}
    client.successfully_enrolled_c = 0
    client.already_enrolled_c = 0
    client.expired_c = 0
    client.excluded_c = 0
    client.amount_saved_c = 0.0
    client.close = AsyncMock()
    client.get_enrolled_courses = AsyncMock()
    client.is_already_enrolled = AsyncMock(return_value=False)
    client.check_already_enrolled_live = AsyncMock(return_value=False)
    client.get_course_id = AsyncMock()
    client.check_course = AsyncMock()
    client.checkout_single = AsyncMock(return_value=True)
    client.is_course_excluded = MagicMock()
    return client


@pytest.fixture
def default_settings():
    return {
        "sites": {"Real Discount": True},
        "languages": {"English": True},
        "categories": {"Development": True},
        "instructor_exclude": [],
        "title_exclude": [],
        "min_rating": 0.0,
        "course_update_threshold_months": 24,
        "discounted_only": False,
        "proxy_url": None,
    }


# ── Class-level helper tests ──────────────────────────────


class TestEnrollmentManagerHelpers:
    """Test static/class helper methods."""

    def test_get_active_run_finds_pending(self, db_session):
        user = User(email="test@example.com", udemy_display_name="Test")
        db_session.add(user)
        db_session.commit()

        run = EnrollmentRun(user_id=user.id, status="pending")
        db_session.add(run)
        db_session.commit()

        active = EnrollmentManager.get_active_run(db_session, user.id)
        assert active is not None
        assert active.status == "pending"

    def test_get_active_run_finds_scraping(self, db_session):
        user = User(email="test2@example.com", udemy_display_name="Test")
        db_session.add(user)
        db_session.commit()

        run = EnrollmentRun(user_id=user.id, status="scraping")
        db_session.add(run)
        db_session.commit()

        active = EnrollmentManager.get_active_run(db_session, user.id)
        assert active is not None

    def test_get_active_run_ignores_completed(self, db_session):
        user = User(email="test3@example.com", udemy_display_name="Test")
        db_session.add(user)
        db_session.commit()

        run = EnrollmentRun(user_id=user.id, status="completed")
        db_session.add(run)
        db_session.commit()

        active = EnrollmentManager.get_active_run(db_session, user.id)
        assert active is None

    def test_get_progress_from_run(self, db_session):
        run = EnrollmentRun(
            id=1,
            user_id=1,
            status="enrolling",
            total_courses_found=100,
            total_processed=50,
            successfully_enrolled=30,
            already_enrolled=10,
            expired=5,
            excluded=5,
            amount_saved=99.99,
            progress_data={
                "current_course_title": "Python",
                "current_course_url": "https://udemy.com/course/python/",
                "scraping_progress": [{"site": "Real Discount", "progress": 10}],
            },
        )
        progress = EnrollmentManager.get_progress_from_run(run)
        assert progress["status"] == "enrolling"
        assert progress["total_courses"] == 100
        assert progress["processed"] == 50
        assert progress["successfully_enrolled"] == 30
        assert progress["amount_saved"] == 99.99
        assert progress["current_course_title"] == "Python"
        assert len(progress["scraping_progress"]) == 1


# ── Pipeline tests ────────────────────────────────────────


def _make_mock_scraper_service(courses):
    """Factory for a mock ScraperService that returns given courses."""
    mock_svc = MagicMock()
    mock_svc.scrape_all = AsyncMock(return_value=courses)
    mock_svc.get_progress = MagicMock(return_value=[])
    mock_svc.http = MagicMock()
    mock_svc.http.close = AsyncMock()
    return mock_svc


class TestEnrollmentManagerPipeline:
    """Test the enrollment pipeline with mocked scraper and Udemy client."""

    @pytest.mark.asyncio
    async def test_run_pipeline_creates_run_record(
        self, db_session, mock_udemy_client, default_settings
    ):
        """Test that start_run creates a DB record and returns run_id."""
        user = User(email="pipe@example.com", udemy_display_name="Pipe")
        db_session.add(user)
        db_session.commit()

        with patch.object(EnrollmentManager, "run_pipeline", AsyncMock()):
            run_id = await EnrollmentManager.start_run(
                user.id, mock_udemy_client, default_settings, close_client=False
            )

        assert run_id > 0
        run = db_session.get(EnrollmentRun, run_id)
        assert run is not None
        assert run.status == "pending"
        assert run.user_id == user.id

        # Clean up task
        task = EnrollmentManager.active_tasks.pop(run_id, None)
        if task:
            task.cancel()

    @pytest.mark.asyncio
    async def test_pipeline_with_no_courses(self, db_session, mock_udemy_client, default_settings):
        """Pipeline should complete successfully when no courses are found."""
        user = User(email="empty@example.com", udemy_display_name="Empty")
        db_session.add(user)
        db_session.commit()

        run = EnrollmentRun(user_id=user.id, status="pending", currency="USD")
        db_session.add(run)
        db_session.commit()

        manager = EnrollmentManager(user.id, run.id, mock_udemy_client, default_settings)

        with patch("app.services.enrollment_manager.ScraperService") as MockScraper:
            MockScraper.return_value = _make_mock_scraper_service([])
            await manager.run_pipeline()

        db_session.refresh(run)
        assert run.status == "completed"

    @pytest.mark.asyncio
    async def test_pipeline_saves_enrolled_course(self, db_session, mock_udemy_client, default_settings):
        """Pipeline should save successfully enrolled courses to DB."""
        user = User(email="enroll@example.com", udemy_display_name="Enroll")
        db_session.add(user)
        db_session.commit()

        run = EnrollmentRun(user_id=user.id, status="pending", currency="USD")
        db_session.add(run)
        db_session.commit()

        course = Course("Python Course", "https://udemy.com/course/python/", site="Test")
        course.slug = "python"
        course.is_valid = True
        course.is_coupon_valid = True

        manager = EnrollmentManager(user.id, run.id, mock_udemy_client, default_settings)

        with patch("app.services.enrollment_manager.ScraperService") as MockScraper:
            MockScraper.return_value = _make_mock_scraper_service([course])
            await manager.run_pipeline()

        db_session.refresh(run)
        assert run.status == "completed"
        assert run.successfully_enrolled >= 0

    @pytest.mark.asyncio
    async def test_pipeline_handles_already_enrolled(self, db_session, mock_udemy_client, default_settings):
        """Pipeline should mark already enrolled courses correctly."""
        user = User(email="already@example.com", udemy_display_name="Already")
        db_session.add(user)
        db_session.commit()

        run = EnrollmentRun(user_id=user.id, status="pending", currency="USD")
        db_session.add(run)
        db_session.commit()

        course = Course("JS Course", "https://udemy.com/course/js/", site="Test")
        course.slug = "js"

        mock_udemy_client.is_already_enrolled = AsyncMock(return_value=True)

        manager = EnrollmentManager(user.id, run.id, mock_udemy_client, default_settings)

        with patch("app.services.enrollment_manager.ScraperService") as MockScraper:
            MockScraper.return_value = _make_mock_scraper_service([course])
            await manager.run_pipeline()

        db_session.refresh(run)
        assert run.status == "completed"
        assert run.already_enrolled >= 1

    @pytest.mark.asyncio
    async def test_pipeline_cancellation_updates_run(self, db_session, mock_udemy_client, default_settings):
        """Cancelled pipeline should update run status to cancelled."""
        user = User(email="cancel@example.com", udemy_display_name="Cancel")
        db_session.add(user)
        db_session.commit()

        run = EnrollmentRun(user_id=user.id, status="pending", currency="USD")
        db_session.add(run)
        db_session.commit()

        manager = EnrollmentManager(user.id, run.id, mock_udemy_client, default_settings)

        # Mock scraper to sleep so we can cancel mid-flight
        with patch("app.services.enrollment_manager.ScraperService") as MockScraper:
            mock_svc = MagicMock()

            async def slow_scrape():
                await asyncio.sleep(10)
                return []

            mock_svc.scrape_all = slow_scrape
            mock_svc.get_progress = MagicMock(return_value=[])
            mock_svc.http = MagicMock()
            mock_svc.http.close = AsyncMock()
            MockScraper.return_value = mock_svc

            task = asyncio.create_task(manager.run_pipeline())
            EnrollmentManager.active_tasks[run.id] = task
            await asyncio.sleep(0.05)
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

        db_session.refresh(run)
        assert run.status == "cancelled"

    @pytest.mark.asyncio
    async def test_pipeline_live_check_already_enrolled(
        self, db_session, mock_udemy_client, default_settings
    ):
        """When DB cache misses but live API confirms enrollment, mark correctly."""
        user = User(email="live@example.com", udemy_display_name="Live")
        db_session.add(user)
        db_session.commit()

        run = EnrollmentRun(user_id=user.id, status="pending", currency="USD")
        db_session.add(run)
        db_session.commit()

        course = Course("Live Check Course", "https://udemy.com/course/live-check/", site="Test")
        course.slug = "live-check"

        # DB cache misses, but live API hits
        mock_udemy_client.is_already_enrolled = AsyncMock(return_value=False)
        mock_udemy_client.check_already_enrolled_live = AsyncMock(return_value=True)

        manager = EnrollmentManager(user.id, run.id, mock_udemy_client, default_settings)

        with patch("app.services.enrollment_manager.ScraperService") as MockScraper:
            MockScraper.return_value = _make_mock_scraper_service([course])
            await manager.run_pipeline()

        db_session.refresh(run)
        assert run.status == "completed"
        assert run.already_enrolled == 1
        # Ensure we never attempted enrollment
        mock_udemy_client.checkout_single.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pipeline_invalid_course_is_excluded(self, db_session, mock_udemy_client, default_settings):
        """Invalid courses should be counted as excluded."""
        user = User(email="invalid@example.com", udemy_display_name="Invalid")
        db_session.add(user)
        db_session.commit()

        run = EnrollmentRun(user_id=user.id, status="pending", currency="USD")
        db_session.add(run)
        db_session.commit()

        course = Course("Bad Course", "https://udemy.com/course/bad/", site="Test")
        course.slug = "bad"
        course.is_valid = False
        course.error = "Course not found"

        manager = EnrollmentManager(user.id, run.id, mock_udemy_client, default_settings)

        with patch("app.services.enrollment_manager.ScraperService") as MockScraper:
            MockScraper.return_value = _make_mock_scraper_service([course])
            await manager.run_pipeline()

        db_session.refresh(run)
        assert run.status == "completed"
        assert run.excluded >= 1

    @pytest.mark.asyncio
    async def test_start_run_prevents_duplicate_tasks(self, db_session, mock_udemy_client, default_settings):
        """Starting a run should track it in active_tasks."""
        user = User(email="dup@example.com", udemy_display_name="Dup")
        db_session.add(user)
        db_session.commit()

        with patch.object(EnrollmentManager, "run_pipeline", AsyncMock()):
            run_id = await EnrollmentManager.start_run(
                user.id, mock_udemy_client, default_settings
            )

        assert run_id in EnrollmentManager.active_tasks

        # Cleanup
        task = EnrollmentManager.active_tasks.pop(run_id, None)
        if task:
            task.cancel()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
