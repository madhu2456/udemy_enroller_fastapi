"""F-ENRL-C08: logout wipes stored Udemy cookies only after the last session.

Mirrors the transactional logout tests (test_logout_transaction.py) but with
two concurrent sessions: logging out of one session must keep the stored
cookies AND the per-session cookies_salt intact so the other device keeps
working; the final logout wipes both.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database import Base, User, UserSession
from app.routers.auth import logout
from app.services.enrollment_manager import EnrollmentManager


@pytest.fixture
def multi_session_state(tmp_path):
    """User with two active sessions in an isolated SQLite file."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'multi_session.db'}",
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
        email="multi-session@example.com",
        udemy_cookies="stored-cookie-data",
        cookies_salt="per-session-salt",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token_a = "a" * 64
    token_b = "b" * 64
    db.add(UserSession(token=token_a, user_id=user.id))
    db.add(UserSession(token=token_b, user_id=user.id))
    db.commit()

    try:
        yield SimpleNamespace(
            db=db,
            engine=engine,
            session_factory=session_factory,
            token_a=token_a,
            token_b=token_b,
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


def _snapshot(state):
    """Return (user, session_a_row, session_b_row) from a fresh connection."""
    db = state.session_factory()
    try:
        user = db.query(User).filter(User.id == state.user_id).first()
        session_a = (
            db.query(UserSession).filter(UserSession.token == state.token_a).first()
        )
        session_b = (
            db.query(UserSession).filter(UserSession.token == state.token_b).first()
        )
        return user, session_a, session_b
    finally:
        db.close()


@pytest.mark.asyncio
async def test_logout_keeps_cookies_and_salt_while_other_session_active(
    multi_session_state, monkeypatch
):
    """One of two sessions logs out: cookies + salt must survive (F-ENRL-C08)."""
    monkeypatch.setattr(
        EnrollmentManager,
        "get_active_run",
        staticmethod(lambda _db, _user_id: None),
    )
    cache = MagicMock()

    messages = []
    from loguru import logger

    sink_id = logger.add(messages.append, format="{message}")
    try:
        response = await logout(
            _request(multi_session_state.token_a, cache),
            multi_session_state.db,
            None,
        )
    finally:
        logger.remove(sink_id)

    assert response.status_code == 200
    assert json.loads(response.body)["success"] is True
    user, session_a, session_b = _snapshot(multi_session_state)
    assert session_a is None  # this session revoked
    assert session_b is not None  # other session untouched
    assert user.udemy_cookies == "stored-cookie-data"
    assert user.cookies_salt == "per-session-salt"
    assert "Wiped stored Udemy cookies" not in "".join(messages)
    cache.pop.assert_called_once_with(multi_session_state.token_a, None)


@pytest.mark.asyncio
async def test_final_logout_wipes_cookies_and_salt(multi_session_state, monkeypatch):
    """Last remaining session logs out: stored cookies + salt are wiped."""
    monkeypatch.setattr(
        EnrollmentManager,
        "get_active_run",
        staticmethod(lambda _db, _user_id: None),
    )
    cache_a = MagicMock()
    cache_b = MagicMock()

    response_a = await logout(
        _request(multi_session_state.token_a, cache_a),
        multi_session_state.db,
        None,
    )
    assert response_a.status_code == 200
    user, session_a, session_b = _snapshot(multi_session_state)
    assert session_a is None and session_b is not None
    assert user.udemy_cookies == "stored-cookie-data"

    response_b = await logout(
        _request(multi_session_state.token_b, cache_b),
        multi_session_state.db,
        None,
    )
    assert response_b.status_code == 200
    user, session_a, session_b = _snapshot(multi_session_state)
    assert session_a is None and session_b is None
    assert user.udemy_cookies is None
    assert user.cookies_salt is None


@pytest.mark.asyncio
async def test_expired_session_does_not_block_cookie_wipe(multi_session_state, monkeypatch):
    """Only non-expired sessions keep cookies; an expired one does not."""
    from datetime import timedelta

    from app.models.database import _utcnow_naive

    # Expire token_b: it is no longer an "active" session, so logging out of
    # token_a is a last-session logout even though the row still exists.
    db = multi_session_state.session_factory()
    try:
        session_b = (
            db.query(UserSession).filter(UserSession.token == multi_session_state.token_b).first()
        )
        session_b.expires_at = _utcnow_naive() - timedelta(hours=1)
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(
        EnrollmentManager,
        "get_active_run",
        staticmethod(lambda _db, _user_id: None),
    )
    response = await logout(
        _request(multi_session_state.token_a, multi_session_state.db),
        multi_session_state.db,
        None,
    )
    assert response.status_code == 200
    user, session_a, _session_b = _snapshot(multi_session_state)
    assert session_a is None
    assert user.udemy_cookies is None
    assert user.cookies_salt is None
