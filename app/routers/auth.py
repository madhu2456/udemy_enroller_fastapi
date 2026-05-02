"""Authentication router for Udemy login."""

import secrets
import asyncio
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from loguru import logger

from app.models.database import get_db, User, UserSettings, UserSession, _utcnow_naive
from app.schemas.schemas import LoginRequest, CookieLoginRequest, LoginResponse
from app.services.udemy_client import UdemyClient, LoginException
from app.security import (
    hash_password,
    encrypt_cookies,
    decrypt_cookies,
    login_rate_limiter,
    _client_key,
    generate_csrf_token,
    verify_csrf_token,
)
from config.settings import get_settings

settings = get_settings()
router = APIRouter(prefix="/api/auth", tags=["Authentication"], redirect_slashes=False)


def _create_session(
    user: User, client: UdemyClient, request: Request, db: Session
) -> str:
    """Create a DB session record and register the client in session cache.
    Returns the session token to set as cookie.
    """
    token = secrets.token_hex(32)

    # Persist session in DB (survives server restarts)
    db.add(UserSession(token=token, user_id=user.id))
    db.commit()

    # Store authenticated client in bounded LRU cache
    cache = getattr(request.app.state, "session_cache", None)
    if cache is None:
        # Fallback if cache not initialized yet (e.g., in tests without lifespan)
        if not hasattr(request.app.state, "udemy_clients"):
            request.app.state.udemy_clients = {}
        request.app.state.udemy_clients[token] = client
    else:
        cache.set(token, client)

    return token


def _login_response(client: UdemyClient, token: str) -> JSONResponse:
    csrf_token = generate_csrf_token(token)
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
    )
    # CSRF cookie is NOT httponly so frontend JS can read it and send back in header
    response.set_cookie(
        "csrf_token",
        csrf_token,
        httponly=False,
        samesite="strict",
        secure=settings.COOKIE_SECURE,
    )
    return response


@router.post("/login", response_model=LoginResponse)
async def login_with_credentials(
    login_req: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Login with Udemy email and password."""
    login_rate_limiter.raise_if_limited(_client_key(request))
    client = UdemyClient()
    try:
        await client.manual_login(login_req.email, login_req.password)
        await client.get_session_info()

        user = db.query(User).filter(User.email == login_req.email).first()
        if not user:
            user = User(
                email=login_req.email,
                password_hash=hash_password(login_req.password),
                udemy_display_name=client.display_name,
                udemy_cookies=encrypt_cookies(client.cookie_dict),
                currency=client.currency,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            db.add(UserSettings(user_id=user.id))
            db.commit()
            logger.info(f"New user registered: {login_req.email}")
        else:
            user.udemy_display_name = client.display_name
            user.udemy_cookies = encrypt_cookies(client.cookie_dict)
            user.currency = client.currency
            user.password_hash = hash_password(login_req.password)
            db.commit()
            logger.info(f"User updated: {login_req.email}")

        token = _create_session(user, client, request, db)
        logger.info(f"Login successful: {login_req.email}")
        return _login_response(client, token)

    except LoginException as e:
        logger.warning(f"Login rejected: {e}")
        return LoginResponse(success=False, status="error", message=str(e))
    except Exception as e:
        logger.exception(f"Unexpected login error for {login_req.email}: {e}")
        return LoginResponse(
            success=False, status="error", message="Authentication failed"
        )


@router.post("/login/cookies", response_model=LoginResponse)
async def login_with_cookies(
    cookie_req: CookieLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Login using browser cookies (access_token, client_id, csrf_token)."""
    login_rate_limiter.raise_if_limited(_client_key(request))
    client = UdemyClient()
    try:
        client.cookie_login(
            cookie_req.access_token,
            cookie_req.client_id,
            cookie_req.csrf_token,
        )
        await client.get_session_info()

        user = (
            db.query(User)
            .filter(User.udemy_display_name == client.display_name)
            .first()
        )
        if not user:
            user = User(
                email=f"{client.display_name.replace(' ', '_').lower()}@udemy.local",
                udemy_display_name=client.display_name,
                udemy_cookies=encrypt_cookies(client.cookie_dict),
                currency=client.currency,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            db.add(UserSettings(user_id=user.id))
            db.commit()
            logger.info(f"New user via cookie: {client.display_name}")
        else:
            user.udemy_cookies = encrypt_cookies(client.cookie_dict)
            user.currency = client.currency
            db.commit()
            logger.info(f"User cookies updated: {client.display_name}")

        token = _create_session(user, client, request, db)
        logger.info(f"Cookie login successful: {client.display_name}")
        return _login_response(client, token)

    except LoginException as e:
        logger.warning(f"Cookie login rejected: {e}")
        return LoginResponse(success=False, status="error", message=str(e))
    except Exception as e:
        logger.exception(f"Unexpected cookie login error: {e}")
        return LoginResponse(
            success=False, status="error", message="Cookie authentication failed"
        )


@router.get("/status")
async def auth_status(request: Request, db: Session = Depends(get_db)):
    """Check if user is authenticated."""
    token = request.cookies.get("session_id")
    if not token:
        return {"authenticated": False}

    # Check session exists in DB
    session = db.query(UserSession).filter(UserSession.token == token).first()
    if not session:
        return {"authenticated": False}

    # Check session expiration
    if session.expires_at and session.expires_at < _utcnow_naive():
        db.delete(session)
        db.commit()
        cache = getattr(request.app.state, "session_cache", None)
        if cache:
            cache.pop(token)
        elif hasattr(request.app.state, "udemy_clients"):
            request.app.state.udemy_clients.pop(token, None)
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

    return {
        "authenticated": True,
        "display_name": client.display_name,
        "currency": client.currency,
        "enrolled_courses_count": len(client.enrolled_courses)
        if client.enrolled_courses
        else 0,
        "needs_reauth": False,
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
                    task = EnrollmentManager.active_tasks.get(active_run.id)
                    if task:
                        task.cancel()
                        logger.info(
                            f"Cancelled active enrollment for user {user_id} due to logout."
                        )

            # Delete session from DB
            db.query(UserSession).filter(UserSession.token == token).delete()
            db.commit()

            # Close in-memory client
            cache = getattr(request.app.state, "session_cache", None)
            client = cache.pop(token) if cache else None
            
            # Fallback to legacy dict
            if client is None and hasattr(request.app.state, "udemy_clients"):
                client = request.app.state.udemy_clients.pop(token, None)
                if client:
                    try:
                        close_res = client.close()
                        if asyncio.iscoroutine(close_res):
                            await close_res
                    except Exception as e:
                        logger.error(f"Error closing client {token} during logout: {e}")

                    log_user_id = user_id if user_id is not None else "unknown"
                    logger.info(
                        f"Closed Udemy client session for user {log_user_id} due to logout."
                    )
    except Exception as e:
        logger.error(f"Error during logout: {e}")

    # Create response with explicit cache-control headers
    response = JSONResponse(
        content={"success": True, "message": "Logged out successfully"}
    )

    # Delete session cookie with explicit settings
    response.delete_cookie("session_id", path="/", domain=None)

    # Prevent browser caching of authenticated pages
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response
