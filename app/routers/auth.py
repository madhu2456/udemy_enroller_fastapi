"""Authentication router for Udemy login."""

import secrets
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from loguru import logger

from app.models.database import get_db, User, UserSettings, UserSession, _utcnow_naive
from app.rate_limit_config import maybe_limit
from app.schemas.schemas import LoginRequest, CookieLoginRequest, LoginResponse
from app.services.udemy_client import UdemyClient, LoginException
from app.security import hash_password
from app.sentry_config import capture_exception
from config.settings import get_settings

settings = get_settings()
router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _create_session(user: User, client: UdemyClient, request: Request, db: Session) -> str:
    """Create a DB session record and register the client in app state.
    Returns the session token to set as cookie.
    """
    token = secrets.token_hex(32)

    # Persist session in DB (survives server restarts)
    db.add(UserSession(token=token, user_id=user.id))
    db.commit()

    # Store authenticated client in memory keyed by token
    if not hasattr(request.app.state, "udemy_clients"):
        request.app.state.udemy_clients = {}
    request.app.state.udemy_clients[token] = client

    return token


def _login_response(client: UdemyClient, token: str) -> JSONResponse:
    response = JSONResponse(content={
        "success": True,
        "status": "success",
        "message": f"Logged in as {client.display_name}",
        "display_name": client.display_name,
        "currency": client.currency,
    })
    response.set_cookie(
        "session_id",
        token,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
    )
    return response


@router.post("/login", response_model=LoginResponse)
@maybe_limit(settings.RATE_LIMIT_AUTH)
async def login_with_credentials(
    login_req: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Login with Udemy email and password."""
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
                udemy_cookies=client.cookie_dict,
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
            user.udemy_cookies = client.cookie_dict
            user.currency = client.currency
            user.password_hash = hash_password(login_req.password)
            db.commit()
            logger.info(f"User updated: {login_req.email}")

        token = _create_session(user, client, request, db)
        logger.info(f"Login successful: {login_req.email}")
        return _login_response(client, token)

    except LoginException as e:
        logger.warning(f"Login rejected: {e}")
        capture_exception(e, level="warning")
        return LoginResponse(success=False, status="error", message=str(e))
    except Exception as e:
        logger.exception(f"Unexpected login error for {login_req.email}: {e}")
        capture_exception(e, level="error")
        return LoginResponse(success=False, status="error", message="Authentication failed")


@router.post("/login/cookies", response_model=LoginResponse)
@maybe_limit(settings.RATE_LIMIT_AUTH)
async def login_with_cookies(
    cookie_req: CookieLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Login using browser cookies (access_token, client_id, csrf_token)."""
    client = UdemyClient()
    try:
        client.cookie_login(
            cookie_req.access_token,
            cookie_req.client_id,
            cookie_req.csrf_token,
        )
        await client.get_session_info()

        user = db.query(User).filter(User.udemy_display_name == client.display_name).first()
        if not user:
            user = User(
                email=f"{client.display_name.replace(' ', '_').lower()}@udemy.local",
                udemy_display_name=client.display_name,
                udemy_cookies=client.cookie_dict,
                currency=client.currency,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            db.add(UserSettings(user_id=user.id))
            db.commit()
            logger.info(f"New user via cookie: {client.display_name}")
        else:
            user.udemy_cookies = client.cookie_dict
            user.currency = client.currency
            db.commit()
            logger.info(f"User cookies updated: {client.display_name}")

        token = _create_session(user, client, request, db)
        logger.info(f"Cookie login successful: {client.display_name}")
        return _login_response(client, token)

    except LoginException as e:
        logger.warning(f"Cookie login rejected: {e}")
        capture_exception(e, level="warning")
        return LoginResponse(success=False, status="error", message=str(e))
    except Exception as e:
        logger.exception(f"Unexpected cookie login error: {e}")
        capture_exception(e, level="error")
        return LoginResponse(success=False, status="error", message="Cookie authentication failed")


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
        if hasattr(request.app.state, "udemy_clients"):
            request.app.state.udemy_clients.pop(token, None)
        return {"authenticated": False}

    # Check in-memory client
    clients = getattr(request.app.state, "udemy_clients", {})
    client = clients.get(token)
    
    if not client or not client.is_authenticated:
        # Reconstruct client from db cookies
        user = session.user
        if user.udemy_cookies:
            client = UdemyClient()
            client.cookie_dict = user.udemy_cookies
            client.http.client.cookies.update(user.udemy_cookies)
            client.display_name = user.udemy_display_name
            client.currency = user.currency
            client.is_authenticated = True
            
            if not hasattr(request.app.state, "udemy_clients"):
                request.app.state.udemy_clients = {}
            request.app.state.udemy_clients[token] = client
            logger.info(f"Reconstructed session for {client.display_name}")
        else:
            return {"authenticated": False}

    return {
        "authenticated": True,
        "display_name": client.display_name,
        "currency": client.currency,
        "enrolled_courses_count": len(client.enrolled_courses) if client.enrolled_courses else 0,
        "needs_reauth": False,
    }


@router.post("/logout")
@maybe_limit(settings.RATE_LIMIT_API)
async def logout(request: Request, db: Session = Depends(get_db)):
    """Logout — delete DB session and clear cookie."""
    token = request.cookies.get("session_id")
    if token:
        db.query(UserSession).filter(UserSession.token == token).delete()
        db.commit()
        if hasattr(request.app.state, "udemy_clients"):
            request.app.state.udemy_clients.pop(token, None)

    response = JSONResponse(content={"success": True, "message": "Logged out"})
    response.delete_cookie("session_id")
    return response
