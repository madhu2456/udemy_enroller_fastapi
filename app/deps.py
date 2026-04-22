"""Shared FastAPI dependencies."""

import logging
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.models.database import get_db, UserSession, _utcnow_naive
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
        if hasattr(request.app.state, "udemy_clients"):
            request.app.state.udemy_clients.pop(token, None)
        raise HTTPException(status_code=401, detail="Session expired")

    return session


def get_current_user_id(session: UserSession = Depends(get_session)) -> int:
    """Resolve the logged-in user ID."""
    return session.user_id


async def get_udemy_client(request: Request, session: UserSession = Depends(get_session)) -> UdemyClient:
    """Return the authenticated UdemyClient for this session."""
    token = session.token
    clients = getattr(request.app.state, "udemy_clients", {})
    client = clients.get(token)
    
    if client and client.is_authenticated:
        return client

    user = session.user
    cookies = user.udemy_cookies if user else None
    if not user or not isinstance(cookies, dict):
        raise HTTPException(status_code=401, detail="Udemy session missing. Please log in again.")

    access_token = cookies.get("access_token")
    client_id = cookies.get("client_id")
    csrf_token = cookies.get("csrf_token") or cookies.get("csrftoken") or ""
    
    if not access_token or not client_id:
        raise HTTPException(status_code=401, detail="Udemy credentials invalid. Please log in again.")

    restored_client = UdemyClient(
        proxy=user.settings.proxy_url if user.settings else None,
        firecrawl_api_key=user.settings.firecrawl_api_key if user.settings else None
    )
    restored_client.cookie_login(access_token, client_id, csrf_token)
    
    try:
        await restored_client.get_session_info()
    except Exception as exc:
        logger.warning(f"Failed to restore Udemy session for user {session.user_id}: {exc}")
        raise HTTPException(status_code=401, detail="Udemy session expired. Please log in again.")

    if not hasattr(request.app.state, "udemy_clients"):
        request.app.state.udemy_clients = {}
    request.app.state.udemy_clients[token] = restored_client

    return restored_client
