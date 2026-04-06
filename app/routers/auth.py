"""Authentication router for Udemy login."""

import logging
import secrets
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.models.database import get_db, User, UserSettings, UserSession
from app.deps import get_current_user_id, get_udemy_client
from app.schemas.schemas import LoginRequest, CookieLoginRequest, LoginResponse
from app.services.udemy_client import UdemyClient, LoginException

logger = logging.getLogger(__name__)

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
        "message": f"Logged in as {client.display_name}",
        "display_name": client.display_name,
        "currency": client.currency,
    })
    response.set_cookie("session_id", token, httponly=True, samesite="lax")
    return response


@router.post("/login", response_model=LoginResponse)
async def login_with_credentials(
    login_req: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Login with Udemy email and password."""
    client = UdemyClient()
    try:
        client.manual_login(login_req.email, login_req.password)
        client.get_session_info()

        user = db.query(User).filter(User.email == login_req.email).first()
        if not user:
            user = User(
                email=login_req.email,
                udemy_display_name=client.display_name,
                currency=client.currency,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            db.add(UserSettings(user_id=user.id))
            db.commit()
        else:
            user.udemy_display_name = client.display_name
            user.currency = client.currency
            db.commit()

        token = _create_session(user, client, request, db)
        return _login_response(client, token)

    except LoginException as e:
        logger.warning(f"Login rejected: {e}")
        return LoginResponse(success=False, message=str(e))
    except Exception as e:
        logger.exception("Unexpected login error")
        return LoginResponse(success=False, message=f"Unexpected error: {e}")


@router.post("/login/cookies", response_model=LoginResponse)
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
        client.get_session_info()

        user = db.query(User).filter(User.udemy_display_name == client.display_name).first()
        if not user:
            user = User(
                email=f"{client.display_name.replace(' ', '_').lower()}@udemy.local",
                udemy_display_name=client.display_name,
                currency=client.currency,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            db.add(UserSettings(user_id=user.id))
            db.commit()
        else:
            user.currency = client.currency
            db.commit()

        token = _create_session(user, client, request, db)
        return _login_response(client, token)

    except LoginException as e:
        logger.warning(f"Cookie login rejected: {e}")
        return LoginResponse(success=False, message=str(e))
    except Exception as e:
        logger.exception("Unexpected cookie login error")
        return LoginResponse(success=False, message=f"Unexpected error: {e}")


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

    # Check in-memory client
    clients = getattr(request.app.state, "udemy_clients", {})
    client = clients.get(token)
    if not client or not client.is_authenticated:
        # Session exists in DB but client not in memory (server restarted)
        return {
            "authenticated": True,  # DB session valid, just needs re-auth for active enrollment
            "display_name": session.user.udemy_display_name,
            "currency": session.user.currency,
            "enrolled_courses_count": 0,
            "needs_reauth": True,
        }

    return {
        "authenticated": True,
        "display_name": client.display_name,
        "currency": client.currency,
        "enrolled_courses_count": len(client.enrolled_courses) if client.enrolled_courses else 0,
        "needs_reauth": False,
    }


@router.post("/logout")
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
