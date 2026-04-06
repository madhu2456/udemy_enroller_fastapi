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


def get_udemy_client(request: Request) -> UdemyClient:
    """Return the authenticated UdemyClient for this session.

    The client is stored in app.state keyed by the session token so each
    user has their own isolated client instance.
    """
    token = request.cookies.get("session_id")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    clients = getattr(request.app.state, "udemy_clients", {})
    client = clients.get(token)
    if not client or not client.is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return client
