"""Authentication router for Udemy login."""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.models.database import get_db, User, UserSettings
from app.schemas.schemas import LoginRequest, CookieLoginRequest, LoginResponse
from app.services.udemy_client import UdemyClient, LoginException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def get_udemy_client(request: Request) -> UdemyClient:
    """Get or create UdemyClient from session."""
    if not hasattr(request.app.state, "udemy_clients"):
        request.app.state.udemy_clients = {}
    # For simplicity, using a single-user approach via session
    session_id = request.cookies.get("session_id", "default")
    if session_id not in request.app.state.udemy_clients:
        request.app.state.udemy_clients[session_id] = UdemyClient()
    return request.app.state.udemy_clients[session_id]


@router.post("/login", response_model=LoginResponse)
async def login_with_credentials(
    login_req: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Login with Udemy email and password."""
    client = get_udemy_client(request)
    try:
        client.manual_login(login_req.email, login_req.password)
        client.get_session_info()

        # Create or update user in DB
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

            # Create default settings
            settings = UserSettings(user_id=user.id)
            db.add(settings)
            db.commit()
        else:
            user.udemy_display_name = client.display_name
            user.currency = client.currency
            db.commit()

        # Store user_id in app state for this session
        request.app.state.udemy_clients["default_user_id"] = user.id

        response = JSONResponse(content={
            "success": True,
            "message": f"Logged in as {client.display_name}",
            "display_name": client.display_name,
            "currency": client.currency,
        })
        response.set_cookie("user_id", str(user.id), httponly=True, samesite="lax")
        return response
    except LoginException as e:
        logger.warning(f"Login rejected: {e}")
        return LoginResponse(success=False, message=str(e))
    except Exception as e:
        logger.exception("Unexpected login error")
        # Return a clean 200 with success=False so the UI can show the message
        return LoginResponse(success=False, message=f"Unexpected error: {e}")


@router.post("/login/cookies", response_model=LoginResponse)
async def login_with_cookies(
    cookie_req: CookieLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Login using browser cookies (access_token, client_id, csrf_token)."""
    client = get_udemy_client(request)
    try:
        client.cookie_login(
            cookie_req.access_token,
            cookie_req.client_id,
            cookie_req.csrf_token,
        )
        client.get_session_info()

        # Create/update user
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
            settings = UserSettings(user_id=user.id)
            db.add(settings)
            db.commit()
        else:
            user.currency = client.currency
            db.commit()

        request.app.state.udemy_clients["default_user_id"] = user.id

        response = JSONResponse(content={
            "success": True,
            "message": f"Logged in as {client.display_name}",
            "display_name": client.display_name,
            "currency": client.currency,
        })
        response.set_cookie("user_id", str(user.id), httponly=True, samesite="lax")
        return response
    except LoginException as e:
        logger.warning(f"Cookie login rejected: {e}")
        return LoginResponse(success=False, message=str(e))
    except Exception as e:
        logger.exception("Unexpected cookie login error")
        return LoginResponse(success=False, message=f"Unexpected error: {e}")


@router.get("/status")
async def auth_status(request: Request):
    """Check if user is authenticated."""
    client = get_udemy_client(request)
    return {
        "authenticated": client.is_authenticated,
        "display_name": client.display_name if client.is_authenticated else None,
        "currency": client.currency if client.is_authenticated else None,
        "enrolled_courses_count": len(client.enrolled_courses) if client.enrolled_courses else 0,
    }


@router.post("/logout")
async def logout(request: Request):
    """Logout and clear session."""
    session_id = request.cookies.get("session_id", "default")
    if hasattr(request.app.state, "udemy_clients"):
        request.app.state.udemy_clients.pop(session_id, None)
    return {"success": True, "message": "Logged out"}
