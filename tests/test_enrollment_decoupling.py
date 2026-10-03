"""Integration tests for Wave 3 Dual-Stage Enrollment Decoupling & Sleep De-stacking."""

import asyncio
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, EnrollmentRun, EnrolledCourse, User
from app.services import enrollment_manager as em_module
from app.services.course import Course
from app.services.enrollment_manager import EnrollmentManager, PRE_CHECKOUT_TTL_SECONDS
from app.services.enrollment_queue import EnrollmentPriorityQueue, PrioritizedCourse

# Temporary test DB
_test_database_dir = tempfile.TemporaryDirectory(prefix="udemy-enroller-decoupling-tests-")
_test_database_path = Path(_test_database_dir.name) / "test_decoupling.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{_test_database_path}"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def isolate_side_effects_and_cleanup_db(monkeypatch):
    """Prevent public exports and clean database state between tests."""
    monkeypatch.setattr("app.services.public_deals_export.merge_deals_into_public_catalog", lambda *a, **kw: 0)
    monkeypatch.setattr("app.services.public_deals_export.export_public_deals_json", lambda *a, **kw: 0)
    monkeypatch.setattr("app.services.public_deals_export.load_public_deals", lambda *a, **kw: [])
    yield
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())
    EnrollmentManager.active_tasks.clear()


@pytest.fixture(scope="module", autouse=True)
def setup_module_db():
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
    client.display_name = "Decoupling Tester"
    client.is_authenticated = True
    client.successfully_enrolled_c = 0
    client.already_enrolled_c = 0
    client.expired_c = 0
    client.excluded_c = 0
    client.amount_saved_c = 0.0
    client.close = AsyncMock()
    client.get_course_id = AsyncMock()
    client.check_course = AsyncMock()
    client.checkout_single = AsyncMock(return_value=True)
    client.populate_course_metadata = AsyncMock()
    client.is_course_excluded = MagicMock()
    client.is_already_enrolled = AsyncMock(return_value=False)
    client.check_already_enrolled_live = AsyncMock(return_value=False)
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


def _make_mock_scraper(courses: list[Course]):
    mock_svc = MagicMock()

    async def _stream():
        scraper = MagicMock(data=courses)
        yield scraper, "completed"

    mock_svc.stream_results = _stream
    mock_svc.get_progress = MagicMock(return_value=[])
    mock_svc.http = MagicMock()
    mock_svc.http.close = AsyncMock()
    return mock_svc


@pytest.mark.asyncio
async def test_freshness_priority_queue_ordering():
    """EnrollmentPriorityQueue pops freshest (newest timestamp) courses first (FM-002)."""
    queue = EnrollmentPriorityQueue()

    c_old = Course("Old Course", "https://udemy.com/course/old/")
    c_new = Course("New Course", "https://udemy.com/course/new/")
    c_newest = Course("Newest Course", "https://udemy.com/course/newest/")

    # Put with explicit timestamps
    await queue.put(c_old, discovered_at=100.0)
    await queue.put(c_newest, discovered_at=300.0)
    await queue.put(c_new, discovered_at=200.0)

    # Min-heap on priority=-discovered_at yields 300.0, 200.0, 100.0
    item1 = await queue.get()
    item2 = await queue.get()
    item3 = await queue.get()

    assert isinstance(item1, PrioritizedCourse)
    assert item1.course.title == "Newest Course"
    assert item1.discovered_at == 300.0
    assert item2.course.title == "New Course"
    assert item2.discovered_at == 200.0
    assert item3.course.title == "Old Course"
    assert item3.discovered_at == 100.0

    # Sentinel put(None) always has lowest priority (popped last)
    await queue.put(c_old, discovered_at=50.0)
    await queue.put(None)
    item_course = await queue.get()
    assert item_course.course.title == "Old Course"
    item_sentinel = await queue.get()
    assert item_sentinel.course is None


@pytest.mark.asyncio
async def test_validation_culls_expired_before_checkout(
    db_session, mock_udemy_client, default_settings
):
    """Stage 1 validation pool filters expired coupons without pushing to Stage 2 checkout."""
    user = User(email="cull@example.com", udemy_display_name="Culler")
    db_session.add(user)
    db_session.commit()

    run = EnrollmentRun(user_id=user.id, status="pending", currency="USD")
    db_session.add(run)
    db_session.commit()

    c_valid1 = Course("Valid Course 1", "https://udemy.com/course/v1/")
    c_valid1.slug = "v1"
    c_expired = Course("Expired Course", "https://udemy.com/course/exp/")
    c_expired.slug = "exp"
    c_valid2 = Course("Valid Course 2", "https://udemy.com/course/v2/")
    c_valid2.slug = "v2"

    async def _mock_check(c):
        if c.slug == "exp":
            c.is_coupon_valid = False
            c.error = "Coupon expired"
        else:
            c.is_coupon_valid = True

    mock_udemy_client.check_course = AsyncMock(side_effect=_mock_check)

    checkout_order = []

    async def _mock_checkout(c):
        c.status = "enrolled"
        checkout_order.append(c.title)
        return True

    mock_udemy_client.checkout_single = AsyncMock(side_effect=_mock_checkout)

    mock_scraper = _make_mock_scraper([c_valid1, c_expired, c_valid2])
    manager = EnrollmentManager(user.id, run.id, mock_udemy_client, default_settings)

    with patch("app.services.enrollment_manager.ScraperService", return_value=mock_scraper), \
         patch("asyncio.sleep", AsyncMock()):
        await manager.run_pipeline()

    db_session.refresh(run)
    assert run.status == "completed"
    assert run.successfully_enrolled == 2
    assert run.expired == 1

    # checkout_single must ONLY be invoked for valid courses (newest first per freshness bias)
    assert checkout_order == ["Valid Course 2", "Valid Course 1"]
    assert mock_udemy_client.checkout_single.await_count == 2

    # Expired course was persisted in DB with expired status
    expired_entry = db_session.query(EnrolledCourse).filter_by(slug="exp").first()
    assert expired_entry is not None
    assert expired_entry.status == "expired"
    assert "expired" in (expired_entry.error_message or "").lower()


@pytest.mark.asyncio
async def test_pre_checkout_ttl_probe_skips_expired_course(
    db_session, mock_udemy_client, default_settings
):
    """Items dwelling > 240s in queue trigger fast price probe; expired items skip checkout POST (FM-002)."""
    user = User(email="ttl@example.com", udemy_display_name="TTL User")
    db_session.add(user)
    db_session.commit()

    run = EnrollmentRun(user_id=user.id, status="pending", currency="USD")
    db_session.add(run)
    db_session.commit()

    manager = EnrollmentManager(user.id, run.id, mock_udemy_client, default_settings)

    # Stale course discovered 300s ago (> PRE_CHECKOUT_TTL_SECONDS = 240s)
    stale_course = Course("Stale Coupon Course", "https://udemy.com/course/stale/")
    stale_course.slug = "stale"
    stale_course.coupon_code = "OLD_PROMO"

    # Fresh course discovered 10s ago (< 240s)
    fresh_course = Course("Fresh Coupon Course", "https://udemy.com/course/fresh/")
    fresh_course.slug = "fresh"
    fresh_course.coupon_code = "NEW_PROMO"

    check_calls = []

    async def _mock_check(c):
        check_calls.append(c.title)
        if c.slug == "stale":
            c.is_coupon_valid = False
            c.error = "Claim code no longer valid"
        else:
            c.is_coupon_valid = True

    async def _mock_checkout(c):
        c.status = "enrolled"
        return True

    mock_udemy_client.check_course = AsyncMock(side_effect=_mock_check)
    mock_udemy_client.checkout_single = AsyncMock(side_effect=_mock_checkout)

    checkout_queue = EnrollmentPriorityQueue()
    now = time.time()
    # Put stale course with dwell > PRE_CHECKOUT_TTL_SECONDS = 240s
    await checkout_queue.put(stale_course, discovered_at=now - (PRE_CHECKOUT_TTL_SECONDS + 60.0))
    # Put fresh course with dwell = 10s
    await checkout_queue.put(fresh_course, discovered_at=now - 10.0)
    await checkout_queue.put(None)  # Sentinel to terminate

    source_stats = {"Unknown": {"enrolled": 0, "already_enrolled": 0, "expired": 0, "failed": 0, "excluded": 0, "invalid": 0, "unknown": 0}}
    abort_event = asyncio.Event()

    with patch("asyncio.sleep", AsyncMock()):
        await manager._checkout_consumer(db_session, run, checkout_queue, source_stats, abort_event)

    db_session.refresh(run)
    # Stale course had TTL probe executed and was marked expired without checkout POST
    assert mock_udemy_client.checkout_single.await_count == 1
    checked_out_course = mock_udemy_client.checkout_single.call_args[0][0]
    assert checked_out_course.title == "Fresh Coupon Course"

    # Verify DB recorded expired row
    stale_row = db_session.query(EnrolledCourse).filter_by(slug="stale").first()
    assert stale_row is not None
    assert stale_row.status == "expired"
    assert mock_udemy_client.expired_c == 1
