"""Regression tests for authentication-client ownership and cleanup."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request

from app.routers import auth
from app.schemas.schemas import CookieLoginRequest, LoginRequest
from app.services.udemy_client import LoginException


def _request(path: str) -> Request:
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
        }
    )


def _mock_client() -> MagicMock:
    client = MagicMock()
    client.manual_login = AsyncMock(return_value=None)
    client.cookie_login = MagicMock(return_value=None)
    client.get_session_info = AsyncMock(return_value=None)
    client.close = AsyncMock(return_value=None)
    client.display_name = "Synthetic User"
    client.currency = "USD"
    client.cookie_dict = {"synthetic": "cookie"}
    return client


def _existing_user_db():
    user = SimpleNamespace(
        id=314,
        email="synthetic@example.test",
        udemy_display_name="Previous Name",
        udemy_cookies="previous-encrypted-value",
        currency="USD",
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    return db, user


@pytest.fixture(autouse=True)
def isolate_login_edges(monkeypatch):
    monkeypatch.setattr(auth.settings, "DEPLOYMENT_ENV", "local")
    monkeypatch.setattr(auth.login_rate_limiter, "raise_if_limited", lambda _key: None)


@pytest.mark.asyncio
async def test_rejected_credential_login_closes_owned_client(monkeypatch):
    client = _mock_client()
    client.manual_login.side_effect = LoginException("Synthetic rejection")
    monkeypatch.setattr(auth, "UdemyClient", lambda: client)

    result = await auth.login_with_credentials(
        LoginRequest(email="synthetic@example.test", password="SyntheticPassword123!"),
        _request("/api/auth/login"),
        MagicMock(),
    )

    assert result.success is False
    assert result.message == "Synthetic rejection"
    client.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_rejected_cookie_login_closes_owned_client(monkeypatch):
    client = _mock_client()
    client.cookie_login.side_effect = LoginException("Synthetic rejection")
    monkeypatch.setattr(auth, "UdemyClient", lambda: client)

    result = await auth.login_with_cookies(
        CookieLoginRequest(
            access_token="synthetic-access",
            client_id="synthetic-client",
            csrf_token="synthetic-csrf",
        ),
        _request("/api/auth/login/cookies"),
        MagicMock(),
    )

    assert result.success is False
    assert result.message == "Synthetic rejection"
    client.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_session_handoff_failure_closes_owned_client(monkeypatch):
    client = _mock_client()
    db, _user = _existing_user_db()
    monkeypatch.setattr(auth, "UdemyClient", lambda: client)
    monkeypatch.setattr(auth, "encrypt_cookies", lambda _cookies: "encrypted")
    monkeypatch.setattr(
        auth,
        "_create_session",
        MagicMock(side_effect=RuntimeError("Synthetic handoff failure")),
    )

    result = await auth.login_with_credentials(
        LoginRequest(email="synthetic@example.test", password="SyntheticPassword123!"),
        _request("/api/auth/login"),
        db,
    )

    assert result.success is False
    assert result.message == "Authentication failed"
    client.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_unexpected_credential_login_error_redacts_sensitive_log_details(
    monkeypatch,
):
    email = "PRIVATE_EMAIL@example.test"
    password = "PRIVATE_PASSWORD_VALUE"
    internal_detail = "PRIVATE_INTERNAL_CREDENTIAL_DETAIL"
    client = _mock_client()
    db, _user = _existing_user_db()
    error = MagicMock()
    exception = MagicMock()
    monkeypatch.setattr(auth, "UdemyClient", lambda: client)
    monkeypatch.setattr(auth, "encrypt_cookies", lambda _cookies: "encrypted")
    monkeypatch.setattr(
        auth,
        "_create_session",
        MagicMock(side_effect=RuntimeError(internal_detail)),
    )
    monkeypatch.setattr(auth.logger, "error", error)
    monkeypatch.setattr(auth.logger, "exception", exception)

    result = await auth.login_with_credentials(
        LoginRequest(email=email, password=password),
        _request("/api/auth/login"),
        db,
    )

    messages = "\n".join(str(call.args[0]) for call in error.call_args_list)
    assert result.success is False
    assert result.message == "Authentication failed"
    assert "Unexpected credential-login error" in messages
    assert "RuntimeError" in messages
    assert email not in messages
    assert password not in messages
    assert internal_detail not in messages
    exception.assert_not_called()
    client.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_unexpected_cookie_login_error_redacts_sensitive_log_details(
    monkeypatch,
):
    access_token = "PRIVATE_ACCESS_TOKEN"
    client_id = "PRIVATE_CLIENT_ID"
    csrf_token = "PRIVATE_CSRF_TOKEN"
    internal_detail = "PRIVATE_INTERNAL_COOKIE_DETAIL"
    client = _mock_client()
    client.udemy_user_id = 2718
    db, _user = _existing_user_db()
    error = MagicMock()
    exception = MagicMock()
    monkeypatch.setattr(auth, "UdemyClient", lambda: client)
    monkeypatch.setattr(auth, "encrypt_cookies", lambda _cookies: "encrypted")
    monkeypatch.setattr(
        auth,
        "_create_session",
        MagicMock(side_effect=RuntimeError(internal_detail)),
    )
    monkeypatch.setattr(auth.logger, "error", error)
    monkeypatch.setattr(auth.logger, "exception", exception)

    result = await auth.login_with_cookies(
        CookieLoginRequest(
            access_token=access_token,
            client_id=client_id,
            csrf_token=csrf_token,
        ),
        _request("/api/auth/login/cookies"),
        db,
    )

    messages = "\n".join(str(call.args[0]) for call in error.call_args_list)
    assert result.success is False
    assert result.message == "Cookie authentication failed"
    assert "Unexpected cookie-login error" in messages
    assert "RuntimeError" in messages
    assert access_token not in messages
    assert client_id not in messages
    assert csrf_token not in messages
    assert internal_detail not in messages
    exception.assert_not_called()
    client.close.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_successful_session_handoff_keeps_client_open(monkeypatch):
    client = _mock_client()
    db, user = _existing_user_db()
    create_session = MagicMock(return_value="synthetic-session-token")
    monkeypatch.setattr(auth, "UdemyClient", lambda: client)
    monkeypatch.setattr(auth, "encrypt_cookies", lambda _cookies: "encrypted")
    monkeypatch.setattr(auth, "_create_session", create_session)
    request = _request("/api/auth/login")

    result = await auth.login_with_credentials(
        LoginRequest(email="synthetic@example.test", password="SyntheticPassword123!"),
        request,
        db,
    )

    assert result.status_code == 200
    create_session.assert_called_once_with(user, client, request, db)
    client.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_successful_cookie_session_handoff_keeps_client_open(monkeypatch):
    client = _mock_client()
    client.udemy_user_id = 2718
    db, user = _existing_user_db()
    create_session = MagicMock(return_value="synthetic-session-token")
    monkeypatch.setattr(auth, "UdemyClient", lambda: client)
    monkeypatch.setattr(auth, "encrypt_cookies", lambda _cookies: "encrypted")
    monkeypatch.setattr(auth, "_create_session", create_session)
    request = _request("/api/auth/login/cookies")

    result = await auth.login_with_cookies(
        CookieLoginRequest(
            access_token="synthetic-access",
            client_id="synthetic-client",
            csrf_token="synthetic-csrf",
        ),
        request,
        db,
    )

    assert result.status_code == 200
    create_session.assert_called_once_with(user, client, request, db)
    client.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_failure_preserves_authentication_result_and_redacts_details(
    monkeypatch,
):
    client = _mock_client()
    client.manual_login.side_effect = LoginException("Synthetic rejection")
    client.close.side_effect = RuntimeError("SYNTHETIC_CLOSE_DETAILS")
    warning = MagicMock()
    monkeypatch.setattr(auth, "UdemyClient", lambda: client)
    monkeypatch.setattr(auth.logger, "warning", warning)

    result = await auth.login_with_credentials(
        LoginRequest(email="synthetic@example.test", password="SyntheticPassword123!"),
        _request("/api/auth/login"),
        MagicMock(),
    )

    assert result.success is False
    assert result.message == "Synthetic rejection"
    client.close.assert_awaited_once_with()
    warning_messages = [str(call.args[0]) for call in warning.call_args_list]
    assert any("RuntimeError" in message for message in warning_messages)
    assert all("SYNTHETIC_CLOSE_DETAILS" not in message for message in warning_messages)
