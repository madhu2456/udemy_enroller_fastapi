"""Regression tests for application startup and shutdown state."""

import asyncio

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Response

import main as app_main
from app.core.constants import shutdown_event


class _EmptyDatabaseSession:
    """Minimal context manager for the lifespan's stale-run check."""

    bind = object()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class _FailingDatabaseSession:
    """Raise a marked database error without opening a real connection."""

    EXCEPTION_DETAIL = "PRIVATE_DATABASE_OPERATION_DETAIL"

    def __enter__(self):
        raise RuntimeError(self.EXCEPTION_DETAIL)

    def __exit__(self, exc_type, exc, traceback):
        return False


class _FailingDatabaseEngine:
    """Raise a marked health-probe error without opening a real connection."""

    EXCEPTION_DETAIL = "PRIVATE_DATABASE_HEALTH_DETAIL"

    def connect(self):
        raise RuntimeError(self.EXCEPTION_DETAIL)


class _HealthyDatabaseConnection:
    """Record the health probe without opening a real database connection."""

    def __init__(self):
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement):
        self.statements.append(str(statement))


class _HealthyDatabaseEngine:
    def __init__(self):
        self.connection = _HealthyDatabaseConnection()
        self.connect_calls = 0

    def connect(self):
        self.connect_calls += 1
        return self.connection


class _RecoveringDatabaseEngine(_HealthyDatabaseEngine):
    def connect(self):
        self.connect_calls += 1
        if self.connect_calls == 1:
            raise RuntimeError("PRIVATE_TRANSIENT_DATABASE_DETAIL")
        return self.connection


class _NoopSessionCache:
    """Avoid background tasks while preserving lifespan state initialization."""

    def __init__(self, *, max_size, default_ttl_seconds):
        self.max_size = max_size
        self.default_ttl_seconds = default_ttl_seconds

    def start_cleanup_task(self):
        return None

    def items(self):
        return []

    async def stop_cleanup_task(self):
        return None


class _EmptyTrackedSessionCache:
    last_instance = None

    def __init__(self, *, max_size, default_ttl_seconds):
        self.max_size = max_size
        self.default_ttl_seconds = default_ttl_seconds
        self.cleanup_started = False
        self.cleanup_stopped = False
        type(self).last_instance = self

    def __len__(self):
        return 0

    def start_cleanup_task(self):
        self.cleanup_started = True

    def items(self):
        return []

    async def stop_cleanup_task(self):
        self.cleanup_stopped = True


class _TrackedCloseClient:
    def __init__(self, *, failure_detail=None):
        self.failure_detail = failure_detail
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1
        if self.failure_detail is not None:
            raise RuntimeError(self.failure_detail)


class _TrackedClientSessionCache(_EmptyTrackedSessionCache):
    last_instance = None

    def __init__(self, *, max_size, default_ttl_seconds):
        super().__init__(max_size=max_size, default_ttl_seconds=default_ttl_seconds)
        self.client = _TrackedCloseClient()

    def items(self):
        return [("PRIVATE_TRACKED_SESSION_TOKEN", self.client)]


class _FailingSessionCache:
    SESSION_TOKEN = "PRIVATE_FULL_SESSION_TOKEN"
    EXCEPTION_DETAIL = "PRIVATE_SHUTDOWN_DETAIL"
    last_instance = None

    def __init__(self, *, max_size, default_ttl_seconds):
        self.max_size = max_size
        self.default_ttl_seconds = default_ttl_seconds
        self.failing_client = _TrackedCloseClient(failure_detail=self.EXCEPTION_DETAIL)
        self.followup_client = _TrackedCloseClient()
        self.cleanup_stopped = False
        type(self).last_instance = self

    def start_cleanup_task(self):
        return None

    def items(self):
        return [
            (self.SESSION_TOKEN, self.failing_client),
            ("PRIVATE_FOLLOWUP_SESSION_TOKEN", self.followup_client),
        ]

    async def stop_cleanup_task(self):
        self.cleanup_stopped = True


class _ItemsFailingSessionCache(_EmptyTrackedSessionCache):
    EXCEPTION_DETAIL = "PRIVATE_CACHE_ITEMS_DETAIL"
    last_instance = None

    def items(self):
        raise RuntimeError(self.EXCEPTION_DETAIL)


class _CancelledCloseClient:
    def __init__(self):
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1
        raise asyncio.CancelledError


class _TrackedCancellationTask:
    EXCEPTION_DETAIL = "PRIVATE_TASK_CANCELLATION_DETAIL"

    def __init__(self):
        self.cancel_calls = 0

    def cancel(self):
        self.cancel_calls += 1


class _CancelledClientSessionCache(_EmptyTrackedSessionCache):
    last_instance = None

    def __init__(self, *, max_size, default_ttl_seconds):
        super().__init__(max_size=max_size, default_ttl_seconds=default_ttl_seconds)
        self.client = _CancelledCloseClient()

    def items(self):
        return [("PRIVATE_CANCELLED_SESSION_TOKEN", self.client)]


class _StopFailingSessionCache(_EmptyTrackedSessionCache):
    EXCEPTION_DETAIL = "PRIVATE_CACHE_STOP_DETAIL"
    last_instance = None

    async def stop_cleanup_task(self):
        self.cleanup_stop_attempted = True
        raise RuntimeError(self.EXCEPTION_DETAIL)


def _configure_shutdown_test(monkeypatch, cache_type):
    settings = SimpleNamespace(
        AUTO_CREATE_TABLES=False,
        LOG_FORMAT="text",
        GOOGLE_SITE_VERIFICATION="",
        BING_SITE_VERIFICATION="",
        GTM_CONTAINER_ID="",
        GA4_MEASUREMENT_ID="",
        DEPLOYMENT_ENV="test",
    )

    monkeypatch.setattr(app_main.os, "makedirs", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_main, "get_settings", lambda: settings)
    monkeypatch.setattr("app.models.database.SessionLocal", _EmptyDatabaseSession)
    monkeypatch.setattr(
        "sqlalchemy.inspect",
        lambda bind: SimpleNamespace(has_table=lambda table_name: False),
    )
    monkeypatch.setattr("app.core.cache.SessionCache", cache_type)

    from app.services.enrollment_manager import EnrollmentManager

    monkeypatch.setattr(EnrollmentManager, "active_tasks", {})
    cache_type.last_instance = None


async def _run_lifespan_once():
    test_app = FastAPI()
    was_set = shutdown_event.is_set()
    try:
        async with app_main.lifespan(test_app):
            pass
    finally:
        if was_set:
            shutdown_event.set()
        else:
            shutdown_event.clear()


async def _cancel_lifespan_during_enrollment_wait(monkeypatch, cache_type):
    _configure_shutdown_test(monkeypatch, cache_type)
    enrollment_started = asyncio.Event()
    first_cancel_seen = asyncio.Event()

    async def delayed_enrollment_task():
        enrollment_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            first_cancel_seen.set()
            await asyncio.Event().wait()

    enrollment_task = asyncio.create_task(delayed_enrollment_task())
    await asyncio.wait_for(enrollment_started.wait(), timeout=1)

    from app.services.enrollment_manager import EnrollmentManager

    monkeypatch.setattr(EnrollmentManager, "active_tasks", {1: enrollment_task})
    lifespan_runner = asyncio.create_task(_run_lifespan_once())

    try:
        await asyncio.wait_for(first_cancel_seen.wait(), timeout=1)
        lifespan_runner.cancel()

        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(lifespan_runner, timeout=1)
    finally:
        if not lifespan_runner.done():
            lifespan_runner.cancel()
        if not enrollment_task.done():
            enrollment_task.cancel()
        await asyncio.gather(
            lifespan_runner,
            enrollment_task,
            return_exceptions=True,
        )

    return enrollment_task


@pytest.mark.asyncio
async def test_lifespan_clears_shutdown_event_on_every_startup(monkeypatch):
    """A new lifespan must not inherit the previous shutdown signal."""
    settings = SimpleNamespace(
        AUTO_CREATE_TABLES=False,
        LOG_FORMAT="text",
        GOOGLE_SITE_VERIFICATION="",
        BING_SITE_VERIFICATION="",
        GTM_CONTAINER_ID="",
        GA4_MEASUREMENT_ID="",
        DEPLOYMENT_ENV="test",
    )

    monkeypatch.setattr(app_main.os, "makedirs", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_main, "get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.models.database.SessionLocal", _EmptyDatabaseSession
    )
    monkeypatch.setattr(
        "sqlalchemy.inspect",
        lambda bind: SimpleNamespace(has_table=lambda table_name: False),
    )
    monkeypatch.setattr("app.core.cache.SessionCache", _NoopSessionCache)

    test_app = FastAPI()
    was_set = shutdown_event.is_set()
    shutdown_event.set()

    try:
        async with app_main.lifespan(test_app):
            assert not shutdown_event.is_set()
        assert shutdown_event.is_set()

        async with app_main.lifespan(test_app):
            assert not shutdown_event.is_set()
        assert shutdown_event.is_set()
    finally:
        if was_set:
            shutdown_event.set()
        else:
            shutdown_event.clear()


@pytest.mark.asyncio
async def test_stale_run_cleanup_log_excludes_database_details(monkeypatch):
    warning_messages = []
    _configure_shutdown_test(monkeypatch, _EmptyTrackedSessionCache)
    monkeypatch.setattr(
        "app.models.database.SessionLocal",
        _FailingDatabaseSession,
    )
    monkeypatch.setattr(app_main.logger, "warning", warning_messages.append)

    await _run_lifespan_once()

    cache = _EmptyTrackedSessionCache.last_instance
    assert cache is not None
    assert cache.cleanup_started is True
    assert cache.cleanup_stopped is True
    assert warning_messages == ["Skipped stale run cleanup (RuntimeError)"]
    assert _FailingDatabaseSession.EXCEPTION_DETAIL not in "\n".join(str(message) for message in warning_messages)


@pytest.mark.asyncio
async def test_health_check_log_excludes_database_details(monkeypatch):
    warning_messages = []
    monkeypatch.setattr(app_main, "engine", _FailingDatabaseEngine())
    monkeypatch.setattr(app_main.logger, "warning", warning_messages.append)
    http_response = Response()

    response = await app_main.health_check(None, http_response)

    assert http_response.status_code == 503
    assert response == {
        "status": "degraded",
        "database": "unhealthy",
        "version": app_main.app_settings.APP_VERSION,
    }
    assert warning_messages == ["Health check database probe failed (RuntimeError)"]
    assert _FailingDatabaseEngine.EXCEPTION_DETAIL not in "\n".join(str(message) for message in warning_messages)


@pytest.mark.asyncio
async def test_health_check_returns_200_when_database_probe_succeeds(monkeypatch):
    database_engine = _HealthyDatabaseEngine()
    monkeypatch.setattr(app_main, "engine", database_engine)
    http_response = Response()

    response = await app_main.health_check(None, http_response)

    assert http_response.status_code == 200
    assert response == {
        "status": "healthy",
        "database": "healthy",
        "version": app_main.app_settings.APP_VERSION,
    }
    assert database_engine.connect_calls == 1
    assert database_engine.connection.statements == ["SELECT 1"]


@pytest.mark.asyncio
async def test_health_check_recovers_to_200_after_database_recovers(monkeypatch):
    warning_messages = []
    database_engine = _RecoveringDatabaseEngine()
    monkeypatch.setattr(app_main, "engine", database_engine)
    monkeypatch.setattr(app_main.logger, "warning", warning_messages.append)
    degraded_response = Response()
    recovered_response = Response()

    degraded_body = await app_main.health_check(None, degraded_response)
    recovered_body = await app_main.health_check(None, recovered_response)

    assert degraded_response.status_code == 503
    assert degraded_body["status"] == "degraded"
    assert recovered_response.status_code == 200
    assert recovered_body["status"] == "healthy"
    assert database_engine.connect_calls == 2
    assert database_engine.connection.statements == ["SELECT 1"]
    assert warning_messages == ["Health check database probe failed (RuntimeError)"]


def test_health_check_openapi_documents_service_unavailable():
    previous_schema = app_main.app.openapi_schema
    try:
        app_main.app.openapi_schema = None
        responses = app_main.app.openapi()["paths"]["/api/health"]["get"]["responses"]
    finally:
        app_main.app.openapi_schema = previous_schema

    assert responses["503"]["description"] == "Database dependency unavailable"


@pytest.mark.asyncio
async def test_shutdown_client_error_logs_exclude_session_secrets(monkeypatch):
    settings = SimpleNamespace(
        AUTO_CREATE_TABLES=False,
        LOG_FORMAT="text",
        GOOGLE_SITE_VERIFICATION="",
        BING_SITE_VERIFICATION="",
        GTM_CONTAINER_ID="",
        GA4_MEASUREMENT_ID="",
        DEPLOYMENT_ENV="test",
    )
    error_messages = []
    info_messages = []

    monkeypatch.setattr(app_main.os, "makedirs", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_main, "get_settings", lambda: settings)
    monkeypatch.setattr("app.models.database.SessionLocal", _EmptyDatabaseSession)
    monkeypatch.setattr(
        "sqlalchemy.inspect",
        lambda bind: SimpleNamespace(has_table=lambda table_name: False),
    )
    monkeypatch.setattr("app.core.cache.SessionCache", _FailingSessionCache)
    monkeypatch.setattr(app_main.logger, "error", error_messages.append)
    monkeypatch.setattr(app_main.logger, "info", info_messages.append)

    from app.services.enrollment_manager import EnrollmentManager

    monkeypatch.setattr(EnrollmentManager, "active_tasks", {})
    _FailingSessionCache.last_instance = None

    test_app = FastAPI()
    was_set = shutdown_event.is_set()
    try:
        async with app_main.lifespan(test_app):
            pass
    finally:
        if was_set:
            shutdown_event.set()
        else:
            shutdown_event.clear()

    cache = _FailingSessionCache.last_instance
    assert cache is not None
    assert cache.failing_client.close_calls == 1
    assert cache.followup_client.close_calls == 1
    assert cache.cleanup_stopped is True

    errors = "\n".join(str(message) for message in error_messages)
    assert _FailingSessionCache.SESSION_TOKEN not in errors
    assert _FailingSessionCache.EXCEPTION_DETAIL not in errors
    assert "Failed to close Udemy client session" in errors
    assert "RuntimeError" in errors
    assert "All Udemy client sessions closed." not in info_messages
    assert "Finished Udemy client session shutdown." in info_messages


@pytest.mark.asyncio
async def test_shutdown_stops_cleanup_task_for_empty_session_cache(monkeypatch):
    settings = SimpleNamespace(
        AUTO_CREATE_TABLES=False,
        LOG_FORMAT="text",
        GOOGLE_SITE_VERIFICATION="",
        BING_SITE_VERIFICATION="",
        GTM_CONTAINER_ID="",
        GA4_MEASUREMENT_ID="",
        DEPLOYMENT_ENV="test",
    )

    monkeypatch.setattr(app_main.os, "makedirs", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_main, "get_settings", lambda: settings)
    monkeypatch.setattr("app.models.database.SessionLocal", _EmptyDatabaseSession)
    monkeypatch.setattr(
        "sqlalchemy.inspect",
        lambda bind: SimpleNamespace(has_table=lambda table_name: False),
    )
    monkeypatch.setattr("app.core.cache.SessionCache", _EmptyTrackedSessionCache)

    from app.services.enrollment_manager import EnrollmentManager

    monkeypatch.setattr(EnrollmentManager, "active_tasks", {})
    _EmptyTrackedSessionCache.last_instance = None

    test_app = FastAPI()
    was_set = shutdown_event.is_set()
    try:
        async with app_main.lifespan(test_app):
            pass
    finally:
        if was_set:
            shutdown_event.set()
        else:
            shutdown_event.clear()

    cache = _EmptyTrackedSessionCache.last_instance
    assert cache is not None
    assert len(cache) == 0
    assert cache.cleanup_started is True
    assert cache.cleanup_stopped is True


@pytest.mark.asyncio
async def test_shutdown_task_cancellation_error_excludes_private_details(monkeypatch):
    error_messages = []
    _configure_shutdown_test(monkeypatch, _EmptyTrackedSessionCache)
    monkeypatch.setattr(app_main.logger, "error", error_messages.append)

    from app.services.enrollment_manager import EnrollmentManager

    task = _TrackedCancellationTask()
    monkeypatch.setattr(EnrollmentManager, "active_tasks", {1: task})

    def fail_gather(*tasks, **kwargs):
        assert tasks == (task,)
        assert kwargs == {"return_exceptions": True}
        raise RuntimeError(_TrackedCancellationTask.EXCEPTION_DETAIL)

    monkeypatch.setattr(app_main.asyncio, "gather", fail_gather)

    await _run_lifespan_once()

    cache = _EmptyTrackedSessionCache.last_instance
    assert task.cancel_calls == 1
    assert cache is not None
    assert cache.cleanup_started is True
    assert cache.cleanup_stopped is True
    assert error_messages == ["Enrollment-task cancellation failed (RuntimeError)"]
    assert _TrackedCancellationTask.EXCEPTION_DETAIL not in "\n".join(str(message) for message in error_messages)


@pytest.mark.asyncio
async def test_shutdown_stops_cleanup_when_cache_enumeration_fails(monkeypatch):
    error_messages = []
    _configure_shutdown_test(monkeypatch, _ItemsFailingSessionCache)
    monkeypatch.setattr(app_main.logger, "error", error_messages.append)

    await _run_lifespan_once()

    cache = _ItemsFailingSessionCache.last_instance
    assert cache is not None
    assert cache.cleanup_started is True
    assert cache.cleanup_stopped is True
    assert error_messages == ["Unexpected error during shutdown (RuntimeError)"]
    assert _ItemsFailingSessionCache.EXCEPTION_DETAIL not in "\n".join(str(message) for message in error_messages)


@pytest.mark.asyncio
async def test_shutdown_stops_cleanup_before_propagating_cancellation(monkeypatch):
    _configure_shutdown_test(monkeypatch, _CancelledClientSessionCache)

    with pytest.raises(asyncio.CancelledError):
        await _run_lifespan_once()

    cache = _CancelledClientSessionCache.last_instance
    assert cache is not None
    assert cache.client.close_calls == 1
    assert cache.cleanup_stopped is True


@pytest.mark.asyncio
async def test_shutdown_cleanup_stop_error_excludes_private_details(monkeypatch):
    error_messages = []
    _configure_shutdown_test(monkeypatch, _StopFailingSessionCache)
    monkeypatch.setattr(app_main.logger, "error", error_messages.append)

    await _run_lifespan_once()

    cache = _StopFailingSessionCache.last_instance
    assert cache is not None
    assert cache.cleanup_stop_attempted is True

    errors = "\n".join(str(message) for message in error_messages)
    assert "Failed to stop session-cache cleanup task" in errors
    assert "RuntimeError" in errors
    assert _StopFailingSessionCache.EXCEPTION_DETAIL not in errors


@pytest.mark.asyncio
async def test_shutdown_cancellation_during_task_wait_still_cleans_sessions(monkeypatch):
    enrollment_task = await _cancel_lifespan_during_enrollment_wait(
        monkeypatch,
        _TrackedClientSessionCache,
    )

    cache = _TrackedClientSessionCache.last_instance
    assert enrollment_task.cancelled()
    assert cache is not None
    assert cache.client.close_calls == 1
    assert cache.cleanup_started is True
    assert cache.cleanup_stopped is True


@pytest.mark.asyncio
async def test_shutdown_cleanup_error_does_not_mask_task_wait_cancellation(monkeypatch):
    error_messages = []
    monkeypatch.setattr(app_main.logger, "error", error_messages.append)

    enrollment_task = await _cancel_lifespan_during_enrollment_wait(
        monkeypatch,
        _ItemsFailingSessionCache,
    )

    cache = _ItemsFailingSessionCache.last_instance
    assert enrollment_task.cancelled()
    assert cache is not None
    assert cache.cleanup_started is True
    assert cache.cleanup_stopped is True

    errors = "\n".join(str(message) for message in error_messages)
    assert errors == "Unexpected error during shutdown (RuntimeError)"
    assert _ItemsFailingSessionCache.EXCEPTION_DETAIL not in errors
