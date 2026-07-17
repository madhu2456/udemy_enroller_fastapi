"""Transactional logout behavior without external network access."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, User, UserSession
from app.routers.auth import logout
from app.services.enrollment_manager import EnrollmentManager


@pytest.fixture
def logout_state(tmp_path):
    """Create an isolated persisted session for each logout test."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'logout.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    db = session_factory()

    user = User(
        email="logout-transaction@example.com",
        udemy_cookies="stored-cookie-data",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = "a" * 64
    db.add(UserSession(token=token, user_id=user.id))
    db.commit()

    try:
        yield SimpleNamespace(
            db=db,
            engine=engine,
            session_factory=session_factory,
            token=token,
            user_id=user.id,
        )
    finally:
        db.close()
        engine.dispose()


def _request(token, cache):
    state = SimpleNamespace(session_cache=cache, udemy_clients=cache)
    return SimpleNamespace(
        cookies={"session_id": token},
        app=SimpleNamespace(state=state),
    )


def _install_active_task(monkeypatch, task):
    active_run = SimpleNamespace(id=123)
    monkeypatch.setattr(
        EnrollmentManager,
        "get_active_run",
        staticmethod(lambda _db, _user_id: active_run),
    )
    monkeypatch.setattr(EnrollmentManager, "active_tasks", {active_run.id: task})


def _assert_session_state(state, *, session_exists, stored_cookies):
    verification_db = state.session_factory()
    try:
        session = verification_db.query(UserSession).filter(UserSession.token == state.token).first()
        user = verification_db.query(User).filter(User.id == state.user_id).first()
        assert (session is not None) is session_exists
        assert user.udemy_cookies == stored_cookies
    finally:
        verification_db.close()


@pytest.mark.asyncio
async def test_commit_failure_rolls_back_and_keeps_logout_retryable(logout_state, monkeypatch):
    """A failed revocation must not be presented as a successful logout."""
    task = MagicMock()
    _install_active_task(monkeypatch, task)

    cache = MagicMock()
    request = _request(logout_state.token, cache)
    rollback = MagicMock(wraps=logout_state.db.rollback)
    monkeypatch.setattr(logout_state.db, "rollback", rollback)
    monkeypatch.setattr(
        logout_state.db,
        "commit",
        MagicMock(side_effect=RuntimeError("sensitive database details")),
    )

    messages = []
    sink_id = logger.add(messages.append, format="{message}")
    try:
        response = await logout(request, logout_state.db, None)
    finally:
        logger.remove(sink_id)
    body = json.loads(response.body)

    assert response.status_code == 500
    assert body == {"success": False, "message": "Logout failed. Please try again."}
    assert "set-cookie" not in response.headers
    assert response.headers["cache-control"] == ("no-cache, no-store, must-revalidate, max-age=0")
    rollback.assert_called_once_with()
    task.cancel.assert_not_called()
    cache.pop.assert_not_called()
    assert "RuntimeError" in "".join(messages)
    assert "sensitive database details" not in "".join(messages)
    _assert_session_state(
        logout_state,
        session_exists=True,
        stored_cookies="stored-cookie-data",
    )


@pytest.mark.asyncio
async def test_success_commits_before_cleanup_and_revokes_all_session_state(logout_state, monkeypatch):
    """Durable revocation must happen before task and client cleanup."""
    events = []
    task = MagicMock()
    task.cancel.side_effect = lambda: events.append("cancel")
    _install_active_task(monkeypatch, task)

    original_commit = logout_state.db.commit

    def tracked_commit():
        events.append("commit")
        return original_commit()

    monkeypatch.setattr(logout_state.db, "commit", tracked_commit)

    cached_client = SimpleNamespace(close=AsyncMock())
    cache = MagicMock()
    cache.pop.return_value = cached_client

    response = await logout(
        _request(logout_state.token, cache),
        logout_state.db,
        None,
    )
    body = json.loads(response.body)
    set_cookie = "\n".join(response.headers.getlist("set-cookie"))

    assert response.status_code == 200
    assert body["success"] is True
    assert events[:2] == ["commit", "cancel"]
    cache.pop.assert_called_once_with(logout_state.token, None)
    cached_client.close.assert_awaited_once_with()
    assert "session_id=" in set_cookie
    assert "csrf_token=" in set_cookie
    assert set_cookie.count("Max-Age=0") == 2
    _assert_session_state(
        logout_state,
        session_exists=False,
        stored_cookies=None,
    )


@pytest.mark.asyncio
async def test_cache_cleanup_failure_does_not_reverse_committed_logout(logout_state, monkeypatch):
    """A revoked database session remains a successful logout if cache pop fails."""
    monkeypatch.setattr(
        EnrollmentManager,
        "get_active_run",
        staticmethod(lambda _db, _user_id: None),
    )
    cache = MagicMock()
    cache.pop.side_effect = RuntimeError("sensitive cache details")

    messages = []
    sink_id = logger.add(messages.append, format="{message}")
    try:
        response = await logout(
            _request(logout_state.token, cache),
            logout_state.db,
            None,
        )
    finally:
        logger.remove(sink_id)

    assert response.status_code == 200
    assert json.loads(response.body)["success"] is True
    assert "set-cookie" in response.headers
    assert "RuntimeError" in "".join(messages)
    assert "sensitive cache details" not in "".join(messages)
    _assert_session_state(
        logout_state,
        session_exists=False,
        stored_cookies=None,
    )


@pytest.mark.asyncio
async def test_client_close_failure_does_not_reverse_committed_logout(logout_state, monkeypatch):
    """A revoked database session remains successful if client closing fails."""
    monkeypatch.setattr(
        EnrollmentManager,
        "get_active_run",
        staticmethod(lambda _db, _user_id: None),
    )
    cached_client = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("sensitive client details")))
    cache = MagicMock()
    cache.pop.return_value = cached_client

    messages = []
    sink_id = logger.add(messages.append, format="{message}")
    try:
        response = await logout(
            _request(logout_state.token, cache),
            logout_state.db,
            None,
        )
    finally:
        logger.remove(sink_id)

    assert response.status_code == 200
    assert json.loads(response.body)["success"] is True
    assert "set-cookie" in response.headers
    cached_client.close.assert_awaited_once_with()
    assert "RuntimeError" in "".join(messages)
    assert "sensitive client details" not in "".join(messages)
    assert "Closed Udemy client session" not in "".join(messages)
    _assert_session_state(
        logout_state,
        session_exists=False,
        stored_cookies=None,
    )


@pytest.mark.asyncio
async def test_stale_session_token_logout_remains_idempotent(logout_state, monkeypatch):
    """A token already absent from the database can still be cleared safely."""
    logout_state.db.query(UserSession).delete()
    logout_state.db.commit()
    monkeypatch.setattr(
        EnrollmentManager,
        "get_active_run",
        staticmethod(lambda _db, _user_id: None),
    )
    cache = MagicMock()

    response = await logout(
        _request(logout_state.token, cache),
        logout_state.db,
        None,
    )

    assert response.status_code == 200
    assert json.loads(response.body)["success"] is True
    assert "set-cookie" in response.headers
    cache.pop.assert_called_once_with(logout_state.token, None)
