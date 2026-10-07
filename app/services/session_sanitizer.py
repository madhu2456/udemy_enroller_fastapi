"""Sanitizer for stale or corrupted fallback sessions."""
from typing import Optional
from fastapi import Request
from loguru import logger
from sqlalchemy.orm import Session
from app.models.database import User, UserSession
from app.security import decrypt_cookies
from app.services.udemy_client import UdemyClient


def evict_stale_fallback_sessions_for_client(
    db: Session, client: UdemyClient, request: Optional[Request] = None
) -> int:
    """Evict legacy udemy_fallback_% sessions that hold the same access token as the incoming client."""
    incoming_token = (client.cookie_dict.get("access_token") or "").strip()
    if not incoming_token:
        return 0

    evicted_count = 0
    try:
        fallback_users = (
            db.query(User)
            .filter(
                User.email.like("udemy_fallback_%"),
                User.is_active.is_(True),
                User.udemy_cookies.isnot(None),
            )
            .all()
        )
        for u in fallback_users:
            try:
                decrypted = decrypt_cookies(u.udemy_cookies, u.cookies_salt) if u.cookies_salt else None
                if decrypted and (decrypted.get("access_token") or "").strip() == incoming_token:
                    logger.warning(
                        f"Evicting stale fallback user #{u.id} ({u.email}) matching active account {client.udemy_user_id}"
                    )
                    active_sessions = db.query(UserSession).filter(UserSession.user_id == u.id).all()
                    for s in active_sessions:
                        if request and hasattr(request.app, "state"):
                            cache = getattr(request.app.state, "session_cache", None)
                            if cache:
                                if hasattr(cache, "delete"):
                                    cache.delete(s.token)
                                elif hasattr(cache, "pop"):
                                    cache.pop(s.token, None)
                            clients = getattr(request.app.state, "udemy_clients", {})
                            if hasattr(clients, "delete"):
                                clients.delete(s.token)
                            elif hasattr(clients, "pop"):
                                clients.pop(s.token, None)
                        db.delete(s)

                    u.udemy_cookies = None
                    u.is_active = False
                    evicted_count += 1
            except Exception as exc:
                logger.debug(f"Error checking fallback user #{u.id}: {exc}")

        if evicted_count > 0:
            db.commit()
    except Exception as exc:
        logger.error(f"Error during fallback session eviction: {exc}")
        db.rollback()

    return evicted_count


def sanitize_legacy_fallback_records(db: Session) -> dict:
    """Startup check to identify legacy fallback records."""
    total_fallback = (
        db.query(User).filter(User.email.like("udemy_fallback_%")).count()
    )
    return {"total_fallback": total_fallback}
