"""Session expiry cleanup helpers.

When an app session expires we remove the session row and, if the user has no
other non-expired sessions, wipe encrypted Udemy cookies from the user row.

Also enforces a max concurrent sessions-per-user cap (oldest revoked first).
"""

from __future__ import annotations

from typing import Any, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.models.database import User, UserSession, _utcnow_naive


def pop_session_client(app_state: Any, token: str) -> Optional[Any]:
    """Remove an in-memory Udemy client for a session token, if present."""
    if app_state is None or not token:
        return None

    cache = getattr(app_state, "session_cache", None)
    client = None
    if cache is not None:
        client = cache.pop(token, None)

    if client is None and hasattr(app_state, "udemy_clients"):
        clients = app_state.udemy_clients
        if clients is not cache and clients is not None and hasattr(clients, "pop"):
            client = clients.pop(token, None)

    return client


def _active_sessions_query(db: Session, user_id: int):
    now = _utcnow_naive()
    return (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id)
        .filter(
            (UserSession.expires_at.is_(None)) | (UserSession.expires_at > now)
        )
    )


def purge_expired_sessions_for_user(
    db: Session,
    user_id: int,
    app_state: Any = None,
) -> int:
    """Delete expired session rows for a user. Returns count removed."""
    now = _utcnow_naive()
    expired = (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id)
        .filter(UserSession.expires_at.isnot(None))
        .filter(UserSession.expires_at <= now)
        .all()
    )
    for session in expired:
        token = session.token
        db.delete(session)
        pop_session_client(app_state, token)
    if expired:
        db.flush()
    return len(expired)


def enforce_session_limit(
    db: Session,
    user_id: int,
    *,
    max_sessions: int,
    app_state: Any = None,
    keep_token: Optional[str] = None,
) -> list[str]:
    """Ensure the user has at most ``max_sessions`` non-expired sessions.

    Revokes the oldest sessions first (by ``created_at``, then ``id``).
    ``keep_token`` is never deleted (the session just created).

    Returns list of revoked tokens. Does not wipe udemy_cookies (other sessions
    remain). Caller should ``db.commit()`` if needed; this function commits.
    """
    if max_sessions is None or max_sessions <= 0:
        return []

    purged = purge_expired_sessions_for_user(db, user_id, app_state)

    active = (
        _active_sessions_query(db, user_id)
        .order_by(UserSession.created_at.asc(), UserSession.id.asc())
        .all()
    )

    revoked: list[str] = []
    while len(active) > max_sessions:
        victim = None
        for candidate in active:
            if keep_token and candidate.token == keep_token:
                continue
            victim = candidate
            break
        if victim is None:
            # Only the keep_token sessions remain (or empty) — stop
            break
        active = [s for s in active if s.id != victim.id]
        token = victim.token
        db.delete(victim)
        pop_session_client(app_state, token)
        revoked.append(token)
        logger.info(f"Revoked oldest session for user {user_id} (max concurrent sessions={max_sessions})")

    if purged or revoked:
        db.commit()
    else:
        db.flush()
    return revoked


def cleanup_expired_session(
    db: Session,
    session: UserSession,
    app_state: Any = None,
) -> Optional[Any]:
    """Delete an expired session and wipe Udemy cookies if no active sessions remain.

    Returns any in-memory client that was associated with the token (caller may close it).
    """
    user_id = session.user_id
    token = session.token

    db.delete(session)
    db.flush()

    active_count = _active_sessions_query(db, user_id).count()

    if active_count == 0:
        user = db.query(User).filter(User.id == user_id).first()
        if user is not None and user.udemy_cookies is not None:
            user.udemy_cookies = None
            logger.info(
                f"Wiped stored Udemy cookies for user {user_id} after last session expired"
            )

    db.commit()
    return pop_session_client(app_state, token)
