"""Shared FastAPI dependencies."""

import logging
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.models.database import get_db, UserSession, _utcnow_naive
from app.security import decrypt_cookies
from app.services.udemy_client import UdemyClient

logger = logging.getLogger(__name__)


def get_session(request: Request, db: Session = Depends(get_db)) -> UserSession:
    """Resolve the session and check expiration."""
    token = request.cookies.get("session_id")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = db.query(UserSession).filter(UserSession.token == token).first()
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    if session.expires_at and session.expires_at < _utcnow_naive():
        # Cleanup expired session
        db.delete(session)
        db.commit()
        cache = getattr(request.app.state, "session_cache", None)
        if cache:
            cache.pop(token)
        elif hasattr(request.app.state, "udemy_clients"):
            request.app.state.udemy_clients.pop(token, None)
        raise HTTPException(status_code=401, detail="Session expired")

    return session


def get_current_user_id(session: UserSession = Depends(get_session)) -> int:
    """Resolve the logged-in user ID."""
    return session.user_id


async def get_udemy_client(
    request: Request, session: UserSession = Depends(get_session)
) -> UdemyClient:
    """Return the authenticated UdemyClient for this session."""
    token = session.token
    clients = getattr(request.app.state, "udemy_clients", {})
    client = clients.get(token)

    # Check if client exists and is valid + has current methods (defensive against hot-reloads)
    if client and client.is_authenticated and hasattr(client, "set_proxy"):
        return client

    user = session.user
    cookies = decrypt_cookies(user.udemy_cookies) if user and user.udemy_cookies else None
    if not user or not isinstance(cookies, dict):
        raise HTTPException(
            status_code=401, detail="Udemy session missing. Please log in again."
        )

    # We need at least some form of authentication (Token or Session ID)
    access_token = cookies.get("access_token")
    client_id = cookies.get("client_id")
    dj_session_id = cookies.get("dj_session_id")

    if not (access_token and client_id) and not dj_session_id:
        logger.warning(
            f"Session restoration failed for user {user.id}: Missing credentials in cookies"
        )
        raise HTTPException(
            status_code=401, detail="Udemy credentials invalid. Please log in again."
        )

    restored_client = UdemyClient(
        proxy=user.settings.proxy_url if user.settings else None
    )

    # Restore ALL cookies found in the database
    restored_client.cookie_dict = cookies.copy()
    restored_client.http.client.cookies.update(restored_client.cookie_dict)

    # If we have a stored display name, set it tentatively
    restored_client.display_name = user.udemy_display_name or "User"

    try:
        await restored_client.get_session_info()
    except Exception as exc:
        logger.warning(
            f"Failed to restore Udemy session for user {session.user_id}: {exc}"
        )
        raise HTTPException(
            status_code=401, detail="Udemy session expired. Please log in again."
        )

    if not hasattr(request.app.state, "udemy_clients"):
        request.app.state.udemy_clients = {}
    request.app.state.udemy_clients[token] = restored_client
    
    # Also store in session cache if available
    cache = getattr(request.app.state, "session_cache", None)
    if cache:
        cache.set(token, restored_client)

    return restored_client
