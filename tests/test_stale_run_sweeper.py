"""F-ENRL-O01: stale-run sweeper and stop-timeout force-marking.

Blocking ``asyncio.to_thread`` calls (cloudscraper/httpx) cannot be
interrupted by ``task.cancel()``, so liveness is tracked via
``EnrollmentRun.last_heartbeat``: the in-process sweeper marks runs failed
when the heartbeat is older than STALE_RUN_TIMEOUT_MINUTES, and the /stop
endpoint force-marks runs interrupted when cancellation cannot finish within
the wait budget.
"""

import asyncio
import tempfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, EnrollmentRun, User, _utcnow_naive
from app.routers import enrollment as enrollment_router
from app.services import enrollment_manager as em_module
from app.services.enrollment_manager import EnrollmentManager

# File-based test DB so every SessionLocal() (sweeper + pipeline) shares data.
_test_database_dir = tempfile.TemporaryDirectory(prefix="udemy-enroller-sweep-tests-")
_test_database_path = Path(_test_database_dir.name) / "test_sweep.db"
engine = create_engine(
    f"sqlite:///{_test_database_path}", connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

# Session factory binding is (re)asserted in cleanup_test_database below:
# modules that import earlier (e.g. test_enrollment_manager) swap
# em_module.SessionLocal at import time too, so import order must not decide
# which module's test DB the sweeper writes to.


class _HungScraperService:
    """Scraper service whose stream never yields — mimics a hung to_thread."""

    def __init__(self, sites=None, proxy=None):
        self.http = SimpleNamespace(close=AsyncMock(return_value=None))
        self.get_progress = MagicMock(return_value=[])

    async def stream_results(self):
        async def _never():
            await asyncio.Event().wait()
            yield MagicMock(data=[]), "completed"

        async for item in _never():
            yield item


async def _hung_task():
    """Swallow the first cancel, then keep sleeping (stuck-blocking-call shape)."""
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        await asyncio.sleep(3600)


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
    yield
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())
    EnrollmentManager.active_tasks.clear()


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_database():
    """Re-bind the patched session factory at module start and restore it
    afterward (import order cannot be relied on across test modules)."""
    original_session_local = em_module.SessionLocal
    em_module.SessionLocal = TestingSessionLocal
    try:
        yield
    finally:
        em_module.SessionLocal = original_session_local
        engine.dispose()
        _test_database_dir.cleanup()


@pytest.fixture
def user_with_run():
    db = TestingSessionLocal()
    user = User(email="sweep@example.com", udemy_display_name="Sweep")
    db.add(user)
    db.commit()
    db.refresh(user)
    run = EnrollmentRun(user_id=user.id, status="scraping", currency="USD")
    db.add(run)
    db.commit()
    db.refresh(run)
    try:
        yield db, user, run
    finally:
        db.close()


# ── Sweeper ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sweeper_marks_stale_run_failed(user_with_run):
    db, _user, run = user_with_run
    run.last_heartbeat = _utcnow_naive() - timedelta(hours=1)
    db.commit()

    recovered = await EnrollmentManager.sweep_stale_runs()

    assert recovered == 1
    db.refresh(run)
    assert run.status == "failed"
    assert "no heartbeat" in run.error_message.lower()
    assert run.completed_at is not None


@pytest.mark.asyncio
async def test_sweeper_marks_run_without_heartbeat_failed(user_with_run):
    """A NULL heartbeat (pre-migration rows) is treated as stale."""
    db, _user, run = user_with_run
    assert run.last_heartbeat is None

    recovered = await EnrollmentManager.sweep_stale_runs()

    assert recovered == 1
    db.refresh(run)
    assert run.status == "failed"


@pytest.mark.asyncio
async def test_sweeper_keeps_fresh_run_active(user_with_run):
    db, _user, run = user_with_run
    run.last_heartbeat = _utcnow_naive()
    db.commit()

    recovered = await EnrollmentManager.sweep_stale_runs()

    assert recovered == 0
    db.refresh(run)
    assert run.status == "scraping"


@pytest.mark.asyncio
async def test_sweeper_ignores_completed_runs(user_with_run):
    db, _user, run = user_with_run
    run.status = "completed"
    run.last_heartbeat = _utcnow_naive() - timedelta(hours=1)
    db.commit()

    recovered = await EnrollmentManager.sweep_stale_runs()

    assert recovered == 0
    db.refresh(run)
    assert run.status == "completed"


@pytest.mark.asyncio
async def test_sweeper_cancels_registered_task_for_stale_run(user_with_run, monkeypatch):
    db, _user, run = user_with_run
    run.last_heartbeat = _utcnow_naive() - timedelta(hours=1)
    db.commit()
    hung_task = MagicMock()
    hung_task.done.return_value = False
    monkeypatch.setattr(EnrollmentManager, "active_tasks", {run.id: hung_task})

    recovered = await EnrollmentManager.sweep_stale_runs()

    assert recovered == 1
    hung_task.cancel.assert_called_once_with()
    assert run.id not in EnrollmentManager.active_tasks


@pytest.mark.asyncio
async def test_late_cancellation_does_not_overwrite_sweeper_failure(
    user_with_run, monkeypatch
):
    """The sweeper's 'failed' verdict survives a late pipeline cancellation.

    Real sequence: pipeline hangs in a blocking call -> sweeper marks the run
    failed and cancels the task -> the CancelledError handler finally resumes
    and must NOT flip the status back to 'cancelled'.
    """
    db, _user, run = user_with_run
    monkeypatch.setattr(em_module, "ScraperService", _HungScraperService)

    manager = EnrollmentManager(
        run.user_id, run.id, MagicMock(), {"sites": {"Real Discount": True}}
    )
    task = asyncio.create_task(manager.run_pipeline())
    EnrollmentManager.active_tasks[run.id] = task

    # Wait until the pipeline is live (status scraping + heartbeat) and hung.
    for _ in range(100):
        db.expire_all()
        if db.get(EnrollmentRun, run.id).status == "scraping":
            break
        await asyncio.sleep(0.02)
    else:
        pytest.fail("pipeline never reached the scraping phase")

    recovered = await EnrollmentManager.sweep_stale_runs()
    assert recovered == 1

    await asyncio.gather(task, return_exceptions=True)

    db.expire_all()
    run = db.get(EnrollmentRun, run.id)
    assert run.status == "failed"
    assert "no heartbeat" in run.error_message.lower()


# ── /stop force-marking ────────────────────────────────────

@pytest.fixture
def active_run():
    db = TestingSessionLocal()
    user = User(email="stop@example.com", udemy_display_name="Stop")
    db.add(user)
    db.commit()
    db.refresh(user)
    run = EnrollmentRun(user_id=user.id, status="scraping", currency="USD")
    db.add(run)
    db.commit()
    db.refresh(run)
    try:
        yield db, user, run
    finally:
        db.close()


@pytest.mark.asyncio
async def test_stop_force_marks_run_when_cancellation_hangs(active_run, monkeypatch):
    """Cancellation that cannot finish within the wait budget force-marks
    the run interrupted instead of leaving it active forever."""
    db, user, run = active_run
    hung = asyncio.create_task(_hung_task())
    EnrollmentManager.active_tasks[run.id] = hung
    # Simulate the 10s wait budget elapsing while the task stays stuck.
    monkeypatch.setattr(
        enrollment_router.asyncio,
        "wait_for",
        AsyncMock(side_effect=asyncio.TimeoutError),
    )
    try:
        response = await enrollment_router.stop_enrollment(db, user.id, None)
    finally:
        hung.cancel()
        await asyncio.gather(hung, return_exceptions=True)

    assert response["success"] is True
    assert hung.cancelling() >= 1  # task.cancel() was issued
    db.refresh(run)
    assert run.status == "failed"
    assert run.error_message == "Interrupted by user (stop timed out)"
    assert run.completed_at is not None


@pytest.mark.asyncio
async def test_stop_without_in_memory_task_marks_cancelled(active_run):
    """Fallback path: no in-memory task (e.g. after restart) -> cancelled."""
    db, user, run = active_run
    assert not EnrollmentManager.active_tasks

    response = await enrollment_router.stop_enrollment(db, user.id, None)

    assert response["success"] is True
    assert response["message"] == "Enrollment run marked as cancelled"
    db.refresh(run)
    assert run.status == "cancelled"
    assert run.error_message == "Cancelled by user"


@pytest.mark.asyncio
async def test_stop_with_no_active_run_is_noop(active_run):
    db, user, run = active_run
    run.status = "completed"
    db.commit()

    response = await enrollment_router.stop_enrollment(db, user.id, None)

    assert response == {"success": False, "message": "No active enrollment run to stop"}
