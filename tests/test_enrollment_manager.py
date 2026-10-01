"""Tests for EnrollmentManager pipeline logic with mocked dependencies."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, EnrollmentRun, User
from app.services import enrollment_manager as em_module
from app.services.course import Course
from app.services.enrollment_manager import EnrollmentManager

# File-based test DB so multiple SessionLocal() calls share the same DB
_test_database_dir = tempfile.TemporaryDirectory(
    prefix="udemy-enroller-manager-tests-"
)
_test_database_path = Path(_test_database_dir.name) / "test_manager.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{_test_database_path}"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

# Patch the module's SessionLocal so the pipeline uses our test DB


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def isolate_side_effects_and_cleanup_db(monkeypatch):
    """Prevent public exports and clean up database state after each test."""
    monkeypatch.setattr(
        "app.services.public_deals_export.merge_deals_into_public_catalog",
        lambda *args, **kwargs: 0,
    )
    monkeypatch.setattr(
        "app.services.public_deals_export.export_public_deals_json",
        lambda *args, **kwargs: 0,
    )
    monkeypatch.setattr(
        "app.services.public_deals_export.load_public_deals",
        lambda *args, **kwargs: [],
    )
    yield
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())
    EnrollmentManager.active_tasks.clear()


@pytest.fixture(autouse=True)
def guard_memory_ceiling():
    """Module-level override for host memory ceiling check."""
    yield


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_database():
    """Re-bind the patched session factory at module start and restore it
    afterward. Import order cannot be relied on: modules that import later
    (e.g. test_stale_run_sweeper) swap em_module.SessionLocal at import time,
    which would silently point pipeline calls at another module's test DB."""
    original_session_local = em_module.SessionLocal
    em_module.SessionLocal = TestingSessionLocal
    try:
        yield
    finally:
        em_module.SessionLocal = original_session_local
        engine.dispose()
        _test_database_dir.cleanup()


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
    client.populate_course_metadata = AsyncMock()
    client.is_course_excluded = MagicMock()
    client.is_checkout_circuit_open = MagicMock(return_value=False)
    client.has_exceeded_max_circuit_trips = MagicMock(return_value=False)
    client.get_checkout_circuit_cooldown_remaining = MagicMock(return_value=0.0)
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
    """Factory for a mock ScraperService that returns given courses via stream_results."""
    mock_svc = MagicMock()
    mock_svc.scrape_all = AsyncMock(return_value=courses)
    mock_svc.get_progress = MagicMock(return_value=[])
    mock_svc.http = MagicMock()
    mock_svc.http.close = AsyncMock()

    # Create a mock scraper with the courses in its .data attribute
    mock_scraper = MagicMock()
    mock_scraper.data = courses
    mock_scraper.site_name = "Mock Scraper"

    # Build an async generator that yields (scraper, state) tuples
    async def _stream():
        if courses:
            yield mock_scraper, "completed"

    mock_svc.stream_results = _stream
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
    async def test_pipeline_with_no_courses(
        self, db_session, mock_udemy_client, default_settings
    ):
        """Pipeline should mark run as failed when no scrapers succeed and no courses are found."""
        user = User(email="empty@example.com", udemy_display_name="Empty")
        db_session.add(user)
        db_session.commit()

        run = EnrollmentRun(user_id=user.id, status="pending", currency="USD")
        db_session.add(run)
        db_session.commit()

        manager = EnrollmentManager(
            user.id, run.id, mock_udemy_client, default_settings
        )

        with patch("app.services.enrollment_manager.ScraperService") as MockScraper:
            MockScraper.return_value = _make_mock_scraper_service([])
            await manager.run_pipeline()

        db_session.refresh(run)
        # When all scrapers fail and no courses are found, the pipeline marks the run as "failed"
        assert run.status == "failed"

    @pytest.mark.asyncio
    async def test_pipeline_saves_enrolled_course(
        self, db_session, mock_udemy_client, default_settings
    ):
        """Pipeline should save successfully enrolled courses to DB."""
        user = User(email="enroll@example.com", udemy_display_name="Enroll")
        db_session.add(user)
        db_session.commit()

        run = EnrollmentRun(user_id=user.id, status="pending", currency="USD")
        db_session.add(run)
        db_session.commit()

        course = Course(
            "Python Course", "https://udemy.com/course/python/", site="Test"
        )
        course.slug = "python"
        course.is_valid = True
        course.is_coupon_valid = True

        manager = EnrollmentManager(
            user.id, run.id, mock_udemy_client, default_settings
        )

        with patch("app.services.enrollment_manager.ScraperService") as MockScraper:
            MockScraper.return_value = _make_mock_scraper_service([course])
            await manager.run_pipeline()

        db_session.refresh(run)
        assert run.status == "completed"
        assert run.successfully_enrolled >= 0

    @pytest.mark.asyncio
    async def test_pipeline_handles_already_enrolled(
        self, db_session, mock_udemy_client, default_settings
    ):
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

        manager = EnrollmentManager(
            user.id, run.id, mock_udemy_client, default_settings
        )

        with patch("app.services.enrollment_manager.ScraperService") as MockScraper:
            MockScraper.return_value = _make_mock_scraper_service([course])
            await manager.run_pipeline()

        db_session.refresh(run)
        assert run.status == "completed"
        assert run.already_enrolled >= 1

    @pytest.mark.asyncio
    async def test_pipeline_cancellation_updates_run(
        self, db_session, mock_udemy_client, default_settings
    ):
        """Cancelled pipeline should update run status to cancelled."""
        user = User(email="cancel@example.com", udemy_display_name="Cancel")
        db_session.add(user)
        db_session.commit()

        run = EnrollmentRun(user_id=user.id, status="pending", currency="USD")
        db_session.add(run)
        db_session.commit()

        manager = EnrollmentManager(
            user.id, run.id, mock_udemy_client, default_settings
        )

        # Mock scraper to sleep so we can cancel mid-flight
        with patch("app.services.enrollment_manager.ScraperService") as MockScraper:
            mock_svc = MagicMock()

            async def slow_stream():
                await asyncio.sleep(10)
                yield MagicMock(data=[]), "completed"

            mock_svc.stream_results = slow_stream
            mock_svc.scrape_all = AsyncMock(return_value=[])
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

        course = Course(
            "Live Check Course", "https://udemy.com/course/live-check/", site="Test"
        )
        course.slug = "live-check"

        # DB cache misses, but live API hits
        mock_udemy_client.is_already_enrolled = AsyncMock(return_value=False)
        mock_udemy_client.check_already_enrolled_live = AsyncMock(return_value=True)

        manager = EnrollmentManager(
            user.id, run.id, mock_udemy_client, default_settings
        )

        with patch("app.services.enrollment_manager.ScraperService") as MockScraper:
            MockScraper.return_value = _make_mock_scraper_service([course])
            await manager.run_pipeline()

        db_session.refresh(run)
        assert run.status == "completed"
        assert run.already_enrolled == 1
        # Ensure we never attempted enrollment
        mock_udemy_client.checkout_single.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pipeline_invalid_course_is_excluded(
        self, db_session, mock_udemy_client, default_settings
    ):
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

        manager = EnrollmentManager(
            user.id, run.id, mock_udemy_client, default_settings
        )

        with patch("app.services.enrollment_manager.ScraperService") as MockScraper:
            MockScraper.return_value = _make_mock_scraper_service([course])
            await manager.run_pipeline()

        db_session.refresh(run)
        assert run.status == "completed"
        assert run.excluded >= 1

    @pytest.mark.asyncio
    async def test_start_run_prevents_duplicate_tasks(
        self, db_session, mock_udemy_client, default_settings
    ):
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

    @pytest.mark.asyncio
    async def test_pipeline_gates_user_proxy_before_scraper_service(
        self, db_session, mock_udemy_client, default_settings
    ):
        """User proxy must pass through resolve_user_proxy before ScraperService
        is constructed (F-ENRL-C05): server mode ignores user proxies here too."""
        user = User(email="proxygate@example.com", udemy_display_name="Proxy")
        db_session.add(user)
        db_session.commit()

        run = EnrollmentRun(user_id=user.id, status="pending", currency="USD")
        db_session.add(run)
        db_session.commit()

        settings = {
            **default_settings,
            "proxy_url": "http://user:pass@proxy.example:8080",
        }
        manager = EnrollmentManager(
            user.id, run.id, mock_udemy_client, settings
        )

        resolved_proxy = "http://resolved.example:3128"
        with patch("app.services.enrollment_manager.ScraperService") as MockScraper:
            MockScraper.return_value = _make_mock_scraper_service([])
            with patch(
                "app.services.enrollment_manager.resolve_user_proxy",
                return_value=resolved_proxy,
            ) as mock_resolve:
                await manager.run_pipeline()

        mock_resolve.assert_called_once_with("http://user:pass@proxy.example:8080")
        assert MockScraper.call_args.kwargs["proxy"] == resolved_proxy

    @pytest.mark.asyncio
    async def test_pipeline_user_proxy_ignored_when_gate_disabled(
        self, db_session, mock_udemy_client, default_settings
    ):
        """With the gate returning None (server mode), ScraperService gets no
        user proxy (F-ENRL-C05)."""
        user = User(email="proxygate2@example.com", udemy_display_name="Proxy")
        db_session.add(user)
        db_session.commit()

        run = EnrollmentRun(user_id=user.id, status="pending", currency="USD")
        db_session.add(run)
        db_session.commit()

        settings = {
            **default_settings,
            "proxy_url": "http://user:pass@proxy.example:8080",
        }
        manager = EnrollmentManager(
            user.id, run.id, mock_udemy_client, settings
        )

        with patch("app.services.enrollment_manager.ScraperService") as MockScraper:
            MockScraper.return_value = _make_mock_scraper_service([])
            with patch(
                "app.services.enrollment_manager.resolve_user_proxy",
                return_value=None,
            ):
                await manager.run_pipeline()

        assert MockScraper.call_args.kwargs["proxy"] is None

    @pytest.mark.asyncio
    async def test_pipeline_seeds_from_public_deals(
        self, db_session, mock_udemy_client, default_settings
    ):
        """Pipeline seeds from verified public deals before streaming scraper results."""
        user = User(email="seeduser@example.com", udemy_display_name="Seeder")
        db_session.add(user)
        db_session.commit()

        run = EnrollmentRun(user_id=user.id, status="pending", currency="USD")
        db_session.add(run)
        db_session.commit()

        manager = EnrollmentManager(
            user.id, run.id, mock_udemy_client, default_settings
        )

        deals = [
            {
                "title": "Seed Deal 1",
                "url": "https://www.udemy.com/course/seed-deal-1/?couponCode=FREE1",
                "coupon_code": "FREE1",
                "is_coupon_valid": True,
                "price": 29.99,
            },
            {
                "title": "Seed Deal Free",
                "url": "https://www.udemy.com/course/seed-deal-free/",
                "is_free": True,
                "is_coupon_valid": True,
                "price": 0.0,
            },
        ]

        captured_courses = []

        async def _mock_checkout(c):
            c.status = "success"
            captured_courses.append(c)
            return True

        mock_udemy_client.checkout_single.side_effect = _mock_checkout

        with patch(
            "app.services.public_deals_export.load_public_deals",
            return_value=deals,
        ):
            with patch("app.services.enrollment_manager.ScraperService") as MockScraper:
                MockScraper.return_value = _make_mock_scraper_service([])
                await manager.run_pipeline()

        db_session.refresh(run)
        assert run.status == "completed"
        assert run.total_courses_found == 2
        assert run.successfully_enrolled == 2

        # Assert that get_course_id is called when course_id is not present in deal
        assert mock_udemy_client.get_course_id.await_count == 2

        # Assert that when deal has is_free: True, the generated course has c.is_free is True
        free_course = next((c for c in captured_courses if c.title == "Seed Deal Free"), None)
        assert free_course is not None
        assert free_course.is_free is True

        from app.models.database import EnrolledCourse

        saved = (
            db_session.query(EnrolledCourse)
            .filter_by(enrollment_run_id=run.id)
            .all()
        )
        assert len(saved) == 2
        for s in saved:
            assert s.site_source == "Verified Deals"
            assert s.status == "enrolled"

    @pytest.mark.parametrize(
        "error_str,expected_status,increments_expired",
        [
            ("Coupon expired", "expired", True),
            ("Price mismatch: 19.99 is not free", "expired", True),
            ("Discount no longer valid", "expired", True),
            ("HTTP 503: Service Unavailable", "failed", False),
            ("Cloudflare challenge encountered", "failed", False),
            ("Connection reset by peer", "failed", False),
            ("HTTP 429: Too Many Requests", "failed", False),
            ("HTTP 403 Forbidden", "failed", False),
        ],
    )
    def test_error_classification_positive_allowlist(
        self, error_str, expected_status, increments_expired
    ):
        """Positive allowlisting correctly categorizes coupon expiration vs infrastructure failures."""
        from app.services.enrollment_manager import COUPON_EXPIRY_SIGNATURES

        err_lower = error_str.lower()
        is_expired = any(sig in err_lower for sig in COUPON_EXPIRY_SIGNATURES)

        if is_expired:
            status = "expired"
        else:
            status = "failed"

        assert status == expected_status
        assert is_expired == increments_expired

    @pytest.mark.asyncio
    async def test_enrollment_manager_pauses_on_circuit_cooldown_with_heartbeat(
        self, db_session, mock_udemy_client, default_settings
    ):
        """EnrollmentManager._wait_for_circuit_breaker pauses queue consumption and updates heartbeat."""
        user = User(email="cooldown@example.com", udemy_display_name="Cooldown User")
        db_session.add(user)
        db_session.commit()

        run = EnrollmentRun(user_id=user.id, status="enrolling")
        db_session.add(run)
        db_session.commit()

        manager = EnrollmentManager(user.id, run.id, mock_udemy_client, default_settings)

        # 1st check for if condition, 2nd & 3rd for 2 while ticks, 4th exits while loop
        mock_udemy_client.is_checkout_circuit_open.side_effect = [True, True, True, False]
        mock_udemy_client.get_checkout_circuit_cooldown_remaining.side_effect = [4.0, 4.0, 2.0, 0.0]
        mock_udemy_client.has_exceeded_max_circuit_trips.return_value = False

        initial_heartbeat = run.last_heartbeat
        with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
            can_continue = await manager._wait_for_circuit_breaker(db_session, run)

        assert can_continue is True
        assert mock_sleep.await_count == 2
        assert run.last_heartbeat is not None
        if initial_heartbeat:
            assert run.last_heartbeat >= initial_heartbeat

    @pytest.mark.asyncio
    async def test_enrollment_manager_halts_fast_on_max_circuit_trips(
        self, db_session, mock_udemy_client, default_settings
    ):
        """EnrollmentManager halts fast when circuit trip ceiling is reached."""
        user = User(email="trips@example.com", udemy_display_name="Trips User")
        db_session.add(user)
        db_session.commit()

        run = EnrollmentRun(user_id=user.id, status="enrolling")
        db_session.add(run)
        db_session.commit()

        manager = EnrollmentManager(user.id, run.id, mock_udemy_client, default_settings)

        mock_udemy_client.is_checkout_circuit_open.return_value = True
        mock_udemy_client.has_exceeded_max_circuit_trips.return_value = True

        can_continue = await manager._wait_for_circuit_breaker(db_session, run)
        assert can_continue is False

    @pytest.mark.asyncio
    async def test_enrollment_manager_circuit_wait_cancelled_cleanly(
        self, db_session, mock_udemy_client, default_settings
    ):
        """asyncio.CancelledError during circuit wait is propagated without swallowing."""
        user = User(email="cancel@example.com", udemy_display_name="Cancel User")
        db_session.add(user)
        db_session.commit()

        run = EnrollmentRun(user_id=user.id, status="enrolling")
        db_session.add(run)
        db_session.commit()

        manager = EnrollmentManager(user.id, run.id, mock_udemy_client, default_settings)

        mock_udemy_client.is_checkout_circuit_open.return_value = True
        mock_udemy_client.get_checkout_circuit_cooldown_remaining.return_value = 10.0
        mock_udemy_client.has_exceeded_max_circuit_trips.return_value = False

        with patch("asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError())):
            with pytest.raises(asyncio.CancelledError):
                await manager._wait_for_circuit_breaker(db_session, run)

    @pytest.mark.asyncio
    async def test_pipeline_halts_and_fails_on_circuit_trip_exhaustion(
        self, db_session, mock_udemy_client, default_settings
    ):
        """Pipeline halts immediately with checkout_circuit_exhausted when circuit ceiling is hit."""
        user = User(email="exhaust@example.com", udemy_display_name="Exhaust User")
        db_session.add(user)
        db_session.commit()

        run = EnrollmentRun(user_id=user.id, status="pending")
        db_session.add(run)
        db_session.commit()

        mock_udemy_client.is_checkout_circuit_open.return_value = True
        mock_udemy_client.has_exceeded_max_circuit_trips.return_value = True

        async def _mock_check(c):
            c.is_coupon_valid = True
            c.is_free = False
        mock_udemy_client.check_course = AsyncMock(side_effect=_mock_check)

        courses = [
            Course(title="Exhaust Course 1", url="https://www.udemy.com/course/ex1/"),
            Course(title="Exhaust Course 2", url="https://www.udemy.com/course/ex2/"),
        ]
        mock_scraper_svc = _make_mock_scraper_service(courses)

        manager = EnrollmentManager(user.id, run.id, mock_udemy_client, default_settings)
        manager.scraper_service = mock_scraper_svc

        with patch("app.services.enrollment_manager.ScraperService", return_value=mock_scraper_svc), \
             patch("app.services.public_deals_export.load_public_deals", return_value=[]), \
             patch("asyncio.sleep", AsyncMock()):
            await manager._run_pipeline_impl()

        db_session.refresh(run)
        assert run.status == "failed"
        assert run.error_message == "checkout_circuit_exhausted"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
