"""Shared FastAPI dependencies."""

import logging
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.models.database import get_db, UserSession
from app.services.udemy_client import UdemyClient

logger = logging.getLogger(__name__)


def get_current_user_id(request: Request, db: Session = Depends(get_db)) -> int:
    """Resolve the logged-in user from the session cookie.

    Looks up the session token in the DB so user identity survives server
    restarts and is properly isolated per user.
    """
    token = request.cookies.get("session_id")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = db.query(UserSession).filter(UserSession.token == token).first()
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    return session.user_id


async def get_udemy_client(request: Request, db: Session = Depends(get_db)) -> UdemyClient:
    """Return the authenticated UdemyClient for this session.

    The client is stored in app.state keyed by the session token so each
    user has their own isolated client instance.
    """
    token = request.cookies.get("session_id")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = db.query(UserSession).filter(UserSession.token == token).first()
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    clients = getattr(request.app.state, "udemy_clients", {})
    client = clients.get(token)
    if client and client.is_authenticated:
        return client

    user = session.user
    cookies = user.udemy_cookies if user else None
    if not user or not isinstance(cookies, dict):
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")

    access_token = cookies.get("access_token")
    client_id = cookies.get("client_id")
    csrf_token = cookies.get("csrf_token") or cookies.get("csrftoken") or ""
    if not access_token or not client_id:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")

    restored_client = UdemyClient(proxy=user.settings.proxy_url if user.settings else None)
    restored_client.cookie_login(access_token, client_id, csrf_token)
    try:
        await restored_client.get_session_info()
    except Exception as exc:
        logger.warning("Failed to restore Udemy session for user %s: %s", session.user_id, exc)
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")

    if not hasattr(request.app.state, "udemy_clients"):
        request.app.state.udemy_clients = {}
    request.app.state.udemy_clients[token] = restored_client

    return restored_client
