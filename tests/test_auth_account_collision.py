"""Security test suite: Cross-account isolation and identity collision prevention.

Verifies fixes for CWE-287 / CWE-384 / CWE-639 / CWE-22:
- Elimination of non-unique display name fallback queries
- Atomic provisioning with concurrent first-login race guards
- Strict input validation on raw Udemy IDs
- Path traversal containment on cache paths
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from app.models.database import SessionLocal, User, UserSession, UserSettings
from app.routers import auth
from app.schemas.schemas import CookieLoginRequest
from app.security import encrypt_cookies_salted, generate_cookie_salt
from app.services.udemy_client import UdemyClient


def _make_request(path: str = "/api/auth/login/cookies") -> Request:
    fake_app = SimpleNamespace(state=SimpleNamespace(session_cache=None, udemy_clients={}))
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "app": fake_app,
        }
    )


@pytest.fixture(autouse=True)
def isolate_auth_env(monkeypatch):
    monkeypatch.setattr(auth.settings, "DEPLOYMENT_ENV", "local")
    monkeypatch.setattr(
        auth.login_rate_limiter, "is_allowed_redis", AsyncMock(return_value=True)
    )


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        session.query(UserSession).delete()
        session.query(UserSettings).delete()
        session.query(User).delete()
        session.commit()
        yield session
    finally:
        session.rollback()
        session.query(UserSession).delete()
        session.query(UserSettings).delete()
        session.query(User).delete()
        session.commit()
        session.close()


@pytest.mark.asyncio
async def test_cookie_login_preserves_registered_user_with_same_display_name(db):
    # Setup: User 1 exists in DB with email="madhu.kumar245@gmail.com", udemy_display_name="Madhu Dadi"
    salt1 = generate_cookie_salt()
    cookies1 = encrypt_cookies_salted({"access_token": "token1"}, salt1)
    user1 = User(
        email="madhu.kumar245@gmail.com",
        udemy_display_name="Madhu Dadi",
        currency="usd",
        is_active=True,
        cookies_salt=salt1,
        udemy_cookies=cookies1,
    )
    db.add(user1)
    db.commit()
    db.refresh(user1)
    db.add(UserSettings(user_id=user1.id))
    db.commit()

    # Action: Call cookie login flow with udemy_user_id="40960386" and display_name="Madhu Dadi"
    mock_client = MagicMock()
    mock_client.cookie_login = MagicMock()
    mock_client.get_session_info = AsyncMock()
    mock_client.close = AsyncMock()
    mock_client.display_name = "Madhu Dadi"
    mock_client.udemy_user_id = "40960386"
    mock_client.currency = "usd"
    mock_client.cookie_dict = {"access_token": "token2", "client_id": "client2"}

    req = _make_request()
    cookie_req = CookieLoginRequest(
        access_token="token2",
        client_id="client2",
        csrf_token="csrf2",
    )

    with patch("app.routers.auth.UdemyClient", return_value=mock_client):
        response = await auth.login_with_cookies(cookie_req, req, db)

    assert response.status_code == 200

    # Assert: User 1 record is untouched (email, cookies, salt unchanged)
    u1 = db.query(User).filter(User.id == user1.id).first()
    assert u1 is not None
    assert u1.email == "madhu.kumar245@gmail.com"
    assert u1.udemy_display_name == "Madhu Dadi"
    assert u1.cookies_salt == salt1
    assert u1.udemy_cookies == cookies1

    # Assert: User 2 is created with email="udemy_40960386@udemy.local"
    user2 = db.query(User).filter(User.email == "udemy_40960386@udemy.local").first()
    assert user2 is not None
    assert user2.id != user1.id
    assert user2.udemy_display_name == "Madhu Dadi"
    assert user2.email == "udemy_40960386@udemy.local"

    # Assert: Session returned corresponds to User 2 (user_id == user2.id)
    user2_session = db.query(UserSession).filter(UserSession.user_id == user2.id).first()
    assert user2_session is not None
    # No session created for User 1
    user1_sessions = db.query(UserSession).filter(UserSession.user_id == user1.id).all()
    assert len(user1_sessions) == 0


@pytest.mark.asyncio
async def test_two_cookie_logins_with_same_display_name_create_isolated_accounts(db):
    req_a = _make_request()
    cookie_req_a = CookieLoginRequest(
        access_token="token_a", client_id="client_a", csrf_token="csrf_a"
    )
    mock_client_a = MagicMock()
    mock_client_a.cookie_login = MagicMock()
    mock_client_a.get_session_info = AsyncMock()
    mock_client_a.close = AsyncMock()
    mock_client_a.display_name = "Madhu Dadi"
    mock_client_a.udemy_user_id = "111111"
    mock_client_a.currency = "usd"
    mock_client_a.cookie_dict = {"access_token": "token_a"}

    with patch("app.routers.auth.UdemyClient", return_value=mock_client_a):
        resp_a = await auth.login_with_cookies(cookie_req_a, req_a, db)
    assert resp_a.status_code == 200

    req_b = _make_request()
    cookie_req_b = CookieLoginRequest(
        access_token="token_b", client_id="client_b", csrf_token="csrf_b"
    )
    mock_client_b = MagicMock()
    mock_client_b.cookie_login = MagicMock()
    mock_client_b.get_session_info = AsyncMock()
    mock_client_b.close = AsyncMock()
    mock_client_b.display_name = "Madhu Dadi"
    mock_client_b.udemy_user_id = "222222"
    mock_client_b.currency = "inr"
    mock_client_b.cookie_dict = {"access_token": "token_b"}

    with patch("app.routers.auth.UdemyClient", return_value=mock_client_b):
        resp_b = await auth.login_with_cookies(cookie_req_b, req_b, db)
    assert resp_b.status_code == 200

    # Assert: DB contains 2 distinct users, 2 distinct UserSettings records, and 2 distinct UserSession records
    all_users = db.query(User).order_by(User.id).all()
    assert len(all_users) == 2
    user_a, user_b = all_users[0], all_users[1]
    assert user_a.id != user_b.id
    assert user_a.email == "udemy_111111@udemy.local"
    assert user_b.email == "udemy_222222@udemy.local"
    assert user_a.udemy_display_name == "Madhu Dadi"
    assert user_b.udemy_display_name == "Madhu Dadi"

    all_settings = db.query(UserSettings).order_by(UserSettings.user_id).all()
    assert len(all_settings) == 2
    assert all_settings[0].user_id == user_a.id
    assert all_settings[1].user_id == user_b.id

    all_sessions = db.query(UserSession).order_by(UserSession.user_id).all()
    assert len(all_sessions) == 2
    assert all_sessions[0].user_id == user_a.id
    assert all_sessions[1].user_id == user_b.id
    assert all_sessions[0].token != all_sessions[1].token


@pytest.mark.asyncio
async def test_concurrent_first_login_race_condition_handled_gracefully(db):
    req = _make_request()
    cookie_req = CookieLoginRequest(
        access_token="token_race", client_id="client_race", csrf_token="csrf_race"
    )
    mock_client = MagicMock()
    mock_client.cookie_login = MagicMock()
    mock_client.get_session_info = AsyncMock()
    mock_client.close = AsyncMock()
    mock_client.display_name = "Race User Updated"
    mock_client.udemy_user_id = "555555"
    mock_client.currency = "usd"
    mock_client.cookie_dict = {"access_token": "token_race"}

    flush_calls = 0
    real_flush = db.flush

    def flush_side_effect(*args, **kwargs):
        nonlocal flush_calls
        flush_calls += 1
        if flush_calls == 1:
            competing_db = SessionLocal()
            salt = generate_cookie_salt()
            competing_user = User(
                email="udemy_555555@udemy.local",
                udemy_display_name="Race User Original",
                currency="eur",
                is_active=True,
                cookies_salt=salt,
                udemy_cookies=encrypt_cookies_salted({"access_token": "old"}, salt),
            )
            competing_db.add(competing_user)
            competing_db.commit()
            competing_db.close()
            raise IntegrityError("INSERT INTO users ...", {}, Exception("UNIQUE constraint failed: users.email"))
        return real_flush(*args, **kwargs)

    with patch.object(db, "flush", side_effect=flush_side_effect):
        with patch("app.routers.auth.UdemyClient", return_value=mock_client):
            response = await auth.login_with_cookies(cookie_req, req, db)

    assert response.status_code == 200

    # Verify existing user was found, cookies updated, and no duplicate was inserted
    users = db.query(User).filter(User.email == "udemy_555555@udemy.local").all()
    assert len(users) == 1
    race_user = users[0]
    assert race_user.udemy_display_name == "Race User Updated"
    assert race_user.currency == "usd"

    # UserSession should exist for this user
    session = db.query(UserSession).filter(UserSession.user_id == race_user.id).first()
    assert session is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_id,expected_fallback",
    [
        (True, True),
        (False, True),
        (0, True),
        ("0", True),
        ("-10", True),
        ("9" * 35, True),
        ("invalid", True),
        (40960386, False),
        ("40960386", False),
    ],
)
async def test_udemy_user_id_raw_id_validation_edge_cases(raw_id, expected_fallback):
    client = UdemyClient()
    client.cookie_dict = {"client_id": "test_client_id"}
    client.http = AsyncMock()
    mock_resp = MagicMock(status_code=200, text="{}")
    client.http.get = AsyncMock(return_value=mock_resp)
    client.http.safe_json = AsyncMock(
        return_value={
            "header": {
                "isLoggedIn": True,
                "user": {
                    "id": raw_id,
                    "display_name": "Test User",
                },
            }
        }
    )

    await client.get_session_info()

    if expected_fallback:
        assert client.udemy_user_id.startswith("fallback_")
        assert len(client.udemy_user_id) == len("fallback_") + 12
    else:
        assert client.udemy_user_id == "40960386"


def test_udemy_user_id_path_traversal_rejection():
    client = UdemyClient()
    traversal_inputs = [
        "../../etc/passwd",
        r"..\exploit",
        "user/123",
        "",
        "a" * 65,
    ]
    for bad_id in traversal_inputs:
        client.udemy_user_id = bad_id
        assert client._get_cache_path() is None, f"Expected None for invalid id: {bad_id!r}"

    client.udemy_user_id = "40960386"
    valid_path = client._get_cache_path()
    assert valid_path is not None
    assert valid_path.name == "enrolled_courses_40960386.json"
    cache_dir = client._get_cache_dir().resolve()
    assert valid_path.is_relative_to(cache_dir)
