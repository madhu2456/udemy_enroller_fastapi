"""Authentication router for Udemy login."""

import asyncio
import secrets

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy.orm import Session

from datetime import timedelta

from app.models.database import User, UserSession, UserSettings, _utcnow_naive, get_db
from app.schemas.schemas import CookieLoginRequest, LoginRequest, LoginResponse
from app.security import (
    _client_key,
    auth_status_rate_limiter,
    decrypt_cookies,
    encrypt_cookies,
    generate_csrf_token,
    login_rate_limiter,
    verify_csrf_token,
)
from app.services.udemy_client import LoginException, UdemyClient
from app.session_lifecycle import cleanup_expired_session, enforce_session_limit
from config.settings import get_settings

settings = get_settings()
router = APIRouter(prefix="/api/auth", tags=["Authentication"], redirect_slashes=False)

# Hosted demo: short-lived app sessions (reduces multi-tenant cookie exposure window).
# Local/self-host: longer convenience TTL.
_SESSION_TTL_SERVER_SECONDS = 24 * 60 * 60  # 24 hours
_SESSION_TTL_LOCAL_SECONDS = 30 * 24 * 60 * 60  # 30 days


def _session_ttl_seconds() -> int:
    if settings.DEPLOYMENT_ENV == "server":
        return _SESSION_TTL_SERVER_SECONDS
    return _SESSION_TTL_LOCAL_SECONDS


def _create_session(
    user: User, client: UdemyClient, request: Request, db: Session
) -> str:
    """Create a DB session record and register the client in session cache.
    Returns the session token to set as cookie.

    Enforces ``MAX_SESSIONS_PER_USER`` by revoking the oldest sessions first.
    """
    token = secrets.token_hex(32)
    ttl = _session_ttl_seconds()
    expires_at = _utcnow_naive() + timedelta(seconds=ttl)

    # Persist session in DB (survives server restarts until expires_at)
    db.add(UserSession(token=token, user_id=user.id, expires_at=expires_at))
    db.commit()

    # Cap concurrent sessions (stolen cookie / multi-device control)
    max_sessions = int(getattr(settings, "MAX_SESSIONS_PER_USER", 3) or 0)
    if max_sessions > 0:
        enforce_session_limit(
            db,
            user.id,
            max_sessions=max_sessions,
            app_state=getattr(request.app, "state", None),
            keep_token=token,
        )

    # Store authenticated client in bounded LRU cache
    cache = getattr(request.app.state, "session_cache", None)
    if cache is None:
        # Fallback if cache not initialized yet (e.g., in tests without lifespan)
        if not hasattr(request.app.state, "udemy_clients"):
            request.app.state.udemy_clients = {}
        request.app.state.udemy_clients[token] = client
    else:
        cache.set(token, client, ttl=ttl)

    return token


def _login_response(client: UdemyClient, token: str) -> JSONResponse:
    csrf_token = generate_csrf_token(token)
    max_age = _session_ttl_seconds()
    response = JSONResponse(
        content={
            "success": True,
            "status": "success",
            "message": f"Logged in as {client.display_name}",
            "display_name": client.display_name,
            "currency": client.currency,
            "csrf_token": csrf_token,
        }
    )
    response.set_cookie(
        "session_id",
        token,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        max_age=max_age,
        path="/",
    )
    # CSRF cookie is NOT httponly so frontend JS can read it and send back in header
    response.set_cookie(
        "csrf_token",
        csrf_token,
        httponly=False,
        samesite="strict",
        secure=settings.COOKIE_SECURE,
        max_age=max_age,
        path="/",
    )
    return response


async def _close_failed_login_client(client: UdemyClient, login_method: str) -> None:
    """Close a request-owned client without replacing the login result."""
    try:
        await client.close()
    except Exception as exc:
        logger.warning(
            f"Failed to close {login_method} client after unsuccessful "
            f"authentication: {type(exc).__name__}"
        )


@router.post("/login", response_model=LoginResponse)
async def login_with_credentials(
    login_req: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Login with Udemy email and password."""
    if settings.DEPLOYMENT_ENV == "server":
        return LoginResponse(
            success=False,
            status="error",
            message=(
                "Email login is disabled on the hosted demo. "
                "Use Cookie Login with session tokens from your browser."
            ),
        )

    login_rate_limiter.raise_if_limited(_client_key(request))
    client = UdemyClient()
    client_handed_off = False
    try:
        await client.manual_login(login_req.email, login_req.password)
        await client.get_session_info()

        user = db.query(User).filter(User.email == login_req.email).first()
        if not user:
            user = User(
                email=login_req.email,
                udemy_display_name=client.display_name,
                udemy_cookies=encrypt_cookies(client.cookie_dict),
                currency=client.currency,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            db.add(UserSettings(user_id=user.id))
            db.commit()
            logger.info(f"New user registered (ID: {user.id})")
        else:
            user.udemy_display_name = client.display_name
            user.udemy_cookies = encrypt_cookies(client.cookie_dict)
            user.currency = client.currency
            db.commit()
            logger.info(f"User updated (ID: {user.id})")

        token = _create_session(user, client, request, db)
        client_handed_off = True
        logger.info(f"Login successful (ID: {user.id})")
        return _login_response(client, token)

    except LoginException as e:
        logger.warning(f"Login rejected: {e}")
        return LoginResponse(success=False, status="error", message=str(e))
    except Exception as exc:
        logger.error(f"Unexpected credential-login error ({type(exc).__name__})")
        return LoginResponse(
            success=False, status="error", message="Authentication failed"
        )
    finally:
        if not client_handed_off:
            await _close_failed_login_client(client, "credential-login")


@router.post("/login/cookies", response_model=LoginResponse)
async def login_with_cookies(
    cookie_req: CookieLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Login using browser cookies (access_token, client_id, csrf_token)."""
    login_rate_limiter.raise_if_limited(_client_key(request))
    client = UdemyClient()
    client_handed_off = False
    try:
        client.cookie_login(
            cookie_req.access_token,
            cookie_req.client_id,
            cookie_req.csrf_token,
        )
        await client.get_session_info()

        udemy_email = f"udemy_{client.udemy_user_id}@udemy.local"
        user = db.query(User).filter(User.email == udemy_email).first()
        if not user:
            # Backwards compatibility: fallback to display name check for legacy records
            user = (
                db.query(User)
                .filter(User.udemy_display_name == client.display_name)
                .first()
            )
            if user:
                logger.warning(
                    f"Migrating user display name '{client.display_name}' to stable ID email: {udemy_email}"
                )
                user.email = udemy_email
                db.commit()

        if not user:
            user = User(
                email=udemy_email,
                udemy_display_name=client.display_name,
                udemy_cookies=encrypt_cookies(client.cookie_dict),
                currency=client.currency,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            db.add(UserSettings(user_id=user.id))
            db.commit()
            logger.info(
                f"New user via cookie (ID: {user.id})"
            )
        else:
            user.udemy_cookies = encrypt_cookies(client.cookie_dict)
            user.currency = client.currency
            user.udemy_display_name = client.display_name  # Keep display name in sync
            db.commit()
            logger.info(
                f"User cookies updated (ID: {user.id})"
            )

        token = _create_session(user, client, request, db)
        client_handed_off = True
        logger.info(f"Cookie login successful (ID: {user.id}, currency: {client.currency})")
        return _login_response(client, token)

    except LoginException as e:
        logger.warning(f"Cookie login rejected: {e}")
        return LoginResponse(success=False, status="error", message=str(e))
    except Exception as exc:
        logger.error(f"Unexpected cookie-login error ({type(exc).__name__})")
        return LoginResponse(
            success=False, status="error", message="Cookie authentication failed"
        )
    finally:
        if not client_handed_off:
            await _close_failed_login_client(client, "cookie-login")


@router.get("/status")
async def auth_status(request: Request, db: Session = Depends(get_db)):
    """Check if user is authenticated."""
    auth_status_rate_limiter.raise_if_limited(_client_key(request))
    token = request.cookies.get("session_id")
    if not token:
        return {"authenticated": False}

    # Check session exists in DB
    session = db.query(UserSession).filter(UserSession.token == token).first()
    if not session:
        return {"authenticated": False}

    # Check session expiration
    if session.expires_at and session.expires_at < _utcnow_naive():
        client = cleanup_expired_session(
            db, session, getattr(request.app, "state", None)
        )
        if client is not None:
            try:
                close_res = client.close()
                if asyncio.iscoroutine(close_res):
                    await close_res
            except Exception as e:
                logger.error(f"Error closing client after session expiry: {e}")
        return {"authenticated": False}

    # Check in-memory client from cache
    cache = getattr(request.app.state, "session_cache", None)
    client = cache.get(token) if cache else None

    # Fallback to legacy dict
    if client is None:
        clients = getattr(request.app.state, "udemy_clients", {})
        client = clients.get(token)

    if not client or not client.is_authenticated:
        # Reconstruct client from db cookies
        user = session.user
        cookies = decrypt_cookies(user.udemy_cookies) if user.udemy_cookies else None
        if cookies:
            client = UdemyClient(
                proxy=user.settings.proxy_url if user.settings else None
            )
            client.cookie_dict = cookies
            client.http.client.cookies.update(cookies)
            client.display_name = user.udemy_display_name
            client.currency = user.currency
            client.is_authenticated = True

            if not hasattr(request.app.state, "udemy_clients"):
                request.app.state.udemy_clients = {}
            request.app.state.udemy_clients[token] = client
            cache = getattr(request.app.state, "session_cache", None)
            if cache:
                cache.set(token, client)
            logger.info(f"Reconstructed session for {client.display_name}")
        else:
            return {"authenticated": False}

    # Session lifetime metadata for UI (no secrets)
    expires_at = session.expires_at
    session_expires_at = None
    session_seconds_remaining = None
    if expires_at is not None:
        # Stored as naive UTC
        session_expires_at = expires_at.replace(microsecond=0).isoformat() + "Z"
        remaining = int((expires_at - _utcnow_naive()).total_seconds())
        session_seconds_remaining = max(0, remaining)

    return {
        "authenticated": True,
        "display_name": client.display_name,
        "currency": client.currency,
        "enrolled_courses_count": len(client.enrolled_courses)
        if client.enrolled_courses
        else 0,
        "needs_reauth": False,
        "deployment_env": settings.DEPLOYMENT_ENV,
        "session_expires_at": session_expires_at,
        "session_seconds_remaining": session_seconds_remaining,
        "session_ttl_seconds": _session_ttl_seconds(),
    }


@router.post("/logout")
async def logout(
    request: Request,
    db: Session = Depends(get_db),
    _csrf: None = Depends(verify_csrf_token),
):
    """Logout — delete DB session and clear all cookies."""
    token = request.cookies.get("session_id")
    user_id = None
    task_to_cancel = None

    try:
        if token:
            # Find session to get user_id before deleting
            session = db.query(UserSession).filter(UserSession.token == token).first()
            if session:
                user_id = session.user_id
                # Stop active enrollment for this user if any
                from app.services.enrollment_manager import EnrollmentManager

                active_run = EnrollmentManager.get_active_run(db, user_id)
                if active_run:
                    task_to_cancel = EnrollmentManager.active_tasks.get(active_run.id)

            # Delete session from DB
            db.query(UserSession).filter(UserSession.token == token).delete()

            # Wipe stored Udemy session cookies on logout (short retention policy)
            if user_id is not None:
                user = db.query(User).filter(User.id == user_id).first()
                if user is not None:
                    user.udemy_cookies = None
            db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception as rollback_exc:
            logger.error(f"Logout rollback failed ({type(rollback_exc).__name__})")
        logger.error(f"Logout session revocation failed ({type(exc).__name__})")

        response = JSONResponse(
            status_code=500,
            content={"success": False, "message": "Logout failed. Please try again."},
        )
        response.headers["Cache-Control"] = (
            "no-cache, no-store, must-revalidate, max-age=0"
        )
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    if token:
        # Only stop work and release memory after durable session revocation.
        if task_to_cancel is not None:
            try:
                task_to_cancel.cancel()
                logger.info(
                    f"Cancelled active enrollment for user {user_id} due to logout."
                )
            except Exception as exc:
                logger.error(
                    "Session revoked but enrollment cleanup failed "
                    f"({type(exc).__name__})"
                )

        try:
            # Close in-memory client (session_cache may be aliased as udemy_clients)
            cache = getattr(request.app.state, "session_cache", None)
            client = None
            if cache is not None:
                client = cache.pop(token, None)

            if client is None and hasattr(request.app.state, "udemy_clients"):
                clients = request.app.state.udemy_clients
                # Avoid double-pop when udemy_clients is the same SessionCache object
                if clients is not cache and clients is not None:
                    if hasattr(clients, "pop"):
                        client = clients.pop(token, None)

            if client is not None:
                try:
                    close_res = client.close()
                    if asyncio.iscoroutine(close_res):
                        await close_res
                except Exception as exc:
                    logger.error(
                        "Session revoked but client cleanup failed "
                        f"({type(exc).__name__})"
                    )
                else:
                    log_user_id = user_id if user_id is not None else "unknown"
                    logger.info(
                        f"Closed Udemy client session for user {log_user_id} due to logout."
                    )
        except Exception as exc:
            logger.error(
                "Session revoked but client-cache cleanup failed "
                f"({type(exc).__name__})"
            )

    # Create response with explicit cache-control headers
    response = JSONResponse(
        content={"success": True, "message": "Logged out successfully"}
    )

    # Delete session and CSRF cookies with explicit settings
    response.delete_cookie("session_id", path="/", domain=None)
    response.delete_cookie("csrf_token", path="/", domain=None)

    # Prevent browser caching of authenticated pages
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response
