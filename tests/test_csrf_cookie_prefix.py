"""F228 & CRITIC-ENROLLER-01: __Host- cookie prefixes when COOKIE_SECURE is true.

Secure deployments must set double-submit CSRF and session cookies as
__Host-csrf_token and __Host-session_id (Secure + Path=/ + no Domain) so sibling subdomains
cannot inject them; local dev over plain http keeps legacy names because
browsers reject __Host- cookies without Secure. All set/delete/read sites
must cover both names.
"""

import secrets
from unittest.mock import MagicMock

from fastapi import Request
from fastapi.testclient import TestClient

from app.routers import auth
from app.security import (
    CSRF_COOKIE_PLAIN,
    CSRF_COOKIE_PREFIXED,
    SESSION_COOKIE_PLAIN,
    SESSION_COOKIE_PREFIXED,
    csrf_cookie_name,
    csrf_cookie_names,
    generate_csrf_token,
    session_cookie_name,
    session_cookie_names,
    verify_csrf_token,
    verify_login_csrf,
)
from main import app


def _set_cookie_entries(response) -> list[tuple[str, str]]:
    """Every Set-Cookie header as (name, full_header) — Starlette or httpx."""
    try:
        items = [(k, v) for k, v in response.raw_headers]
    except AttributeError:
        items = [
            (k.encode("ascii"), v.encode("ascii"))
            for k, v in response.headers.multi_items()
        ]
    entries = []
    for key, value in items:
        if key.decode("ascii").lower() == "set-cookie":
            header = value.decode("ascii")
            entries.append((header.split("=", 1)[0], header))
    return entries


def _set_cookie_names(response) -> list[str]:
    """Names of every Set-Cookie header (sets AND deletions)."""
    return [name for name, _ in _set_cookie_entries(response)]


def _active_set_cookie_names(response) -> list[str]:
    """Names of cookies being SET; deletion cookies (Max-Age=0) excluded."""
    return [
        name
        for name, header in _set_cookie_entries(response)
        if "Max-Age=0" not in header
    ]


class TestSessionCookieName:
    def test_prefixed_when_secure(self):
        assert session_cookie_name(True) == SESSION_COOKIE_PREFIXED
        assert session_cookie_name(True) == "__Host-session_id"

    def test_plain_when_not_secure(self):
        assert session_cookie_name(False) == SESSION_COOKIE_PLAIN
        assert session_cookie_name(False) == "session_id"

    def test_defaults_to_live_settings(self, monkeypatch):
        monkeypatch.setattr(
            "config.settings.get_settings",
            lambda: MagicMock(COOKIE_SECURE=True),
        )
        assert session_cookie_name() == SESSION_COOKIE_PREFIXED
        monkeypatch.setattr(
            "config.settings.get_settings",
            lambda: MagicMock(COOKIE_SECURE=False),
        )
        assert session_cookie_name() == SESSION_COOKIE_PLAIN

    def test_names_tuple_contains_both(self):
        names = session_cookie_names()
        assert names == (SESSION_COOKIE_PREFIXED, SESSION_COOKIE_PLAIN)


class TestCsrfCookieName:
    def test_prefixed_when_secure(self):
        assert csrf_cookie_name(True) == CSRF_COOKIE_PREFIXED
        assert csrf_cookie_name(True) == "__Host-csrf_token"

    def test_plain_when_not_secure(self):
        assert csrf_cookie_name(False) == CSRF_COOKIE_PLAIN
        assert csrf_cookie_name(False) == "csrf_token"

    def test_defaults_to_live_settings(self, monkeypatch):
        monkeypatch.setattr(
            "config.settings.get_settings",
            lambda: MagicMock(COOKIE_SECURE=True),
        )
        assert csrf_cookie_name() == CSRF_COOKIE_PREFIXED
        monkeypatch.setattr(
            "config.settings.get_settings",
            lambda: MagicMock(COOKIE_SECURE=False),
        )
        assert csrf_cookie_name() == CSRF_COOKIE_PLAIN

    def test_names_tuple_contains_both(self):
        names = csrf_cookie_names()
        assert names == (CSRF_COOKIE_PREFIXED, CSRF_COOKIE_PLAIN)


class TestLoginResponseCookieName:
    """_login_response must set prefixed session & CSRF cookies only when secure."""

    def _login_response(self, monkeypatch, secure):
        monkeypatch.setattr(auth.settings, "COOKIE_SECURE", secure)
        client = MagicMock(
            display_name="F228 Test",
            currency="USD",
            cookie_dict={"access_token": "x"},
        )
        token = secrets.token_hex(32)
        return auth._login_response(client, token)

    def test_secure_sets_host_prefixed_cookies(self, monkeypatch):
        response = self._login_response(monkeypatch, secure=True)
        names = _set_cookie_names(response)
        assert CSRF_COOKIE_PREFIXED in names
        assert CSRF_COOKIE_PLAIN not in names
        assert SESSION_COOKIE_PREFIXED in names
        assert SESSION_COOKIE_PLAIN not in names

    def test_secure_prefixed_cookies_have_secure_and_path(self, monkeypatch):
        response = self._login_response(monkeypatch, secure=True)
        set_cookies = " ".join(
            v.decode("ascii")
            for k, v in response.raw_headers
            if k.decode("ascii").lower() == "set-cookie"
        )
        assert "__Host-csrf_token=" in set_cookies
        assert "__Host-session_id=" in set_cookies
        assert "; Secure" in set_cookies
        assert "Path=/" in set_cookies
        assert "SameSite=strict" in set_cookies
        assert "HttpOnly" in set_cookies
        # __Host- prefix forbids a Domain attribute (browser requirement).
        assert "; Domain" not in set_cookies

    def test_insecure_keeps_plain_name(self, monkeypatch):
        response = self._login_response(monkeypatch, secure=False)
        names = _set_cookie_names(response)
        assert CSRF_COOKIE_PLAIN in names
        assert CSRF_COOKIE_PREFIXED not in names
        assert SESSION_COOKIE_PLAIN in names
        assert SESSION_COOKIE_PREFIXED not in names


class TestLoginPageAnonymousCookie:
    """GET / must set the anonymous double-submit cookie under the active name."""

    def _get_home(self, monkeypatch, secure):
        class _Settings:
            COOKIE_SECURE = secure

        monkeypatch.setattr("config.settings.get_settings", lambda: _Settings())
        client = TestClient(app)
        try:
            return client.get("/", follow_redirects=False)
        finally:
            client.close()

    def test_secure_sets_prefixed_anonymous_cookie(self, monkeypatch):
        response = self._get_home(monkeypatch, secure=True)
        assert response.status_code == 200
        active = _active_set_cookie_names(response)
        assert CSRF_COOKIE_PREFIXED in active
        assert CSRF_COOKIE_PLAIN not in active
        # The legacy plain cookie is cleared with a deletion cookie.
        assert CSRF_COOKIE_PLAIN in _set_cookie_names(response)

    def test_insecure_sets_plain_anonymous_cookie(self, monkeypatch):
        response = self._get_home(monkeypatch, secure=False)
        assert response.status_code == 200
        active = _active_set_cookie_names(response)
        assert CSRF_COOKIE_PLAIN in active
        assert CSRF_COOKIE_PREFIXED not in active


class TestVerifyLoginCsrfReadsBothNames:
    def test_prefixed_cookie_accepted(self):
        req = MagicMock(spec=Request)
        req.cookies = {CSRF_COOKIE_PREFIXED: "tok-abc"}
        req.headers = {"x-csrf-token": "tok-abc"}
        verify_login_csrf(req)  # must not raise

    def test_plain_cookie_accepted(self):
        req = MagicMock(spec=Request)
        req.cookies = {CSRF_COOKIE_PLAIN: "tok-abc"}
        req.headers = {"x-csrf-token": "tok-abc"}
        verify_login_csrf(req)  # must not raise

    def test_prefixed_cookie_works_for_session_csrf(self):
        token = "session-abc"
        req = MagicMock(spec=Request)
        req.cookies = {"session_id": token}
        req.headers = {"x-csrf-token": generate_csrf_token(token)}
        verify_csrf_token(req)  # must not raise

    def test_prefixed_session_cookie_works_for_session_csrf(self):
        token = "session-abc"
        req = MagicMock(spec=Request)
        req.cookies = {SESSION_COOKIE_PREFIXED: token}
        req.headers = {"x-csrf-token": generate_csrf_token(token)}
        verify_csrf_token(req)  # must not raise


class TestLogoutDeletesBothNames:
    """Logout must clear both session cookie names and BOTH CSRF cookie names."""

    def _seed_session(self):
        from app.models.database import User, UserSession
        from app.models.database import SessionLocal

        db = SessionLocal()
        user = User(email=f"f228-{secrets.token_hex(6)}@example.com", password_hash="x")
        db.add(user)
        db.commit()
        db.refresh(user)
        token = secrets.token_hex(32)
        db.add(UserSession(token=token, user_id=user.id))
        db.commit()
        db.close()
        return token

    def test_logout_clears_both_cookie_names(self, monkeypatch):
        token = self._seed_session()
        monkeypatch.setattr(auth.settings, "COOKIE_SECURE", True)
        client = TestClient(app)
        try:
            client.cookies.set("session_id", token)
            client.cookies.set(CSRF_COOKIE_PREFIXED, generate_csrf_token(token))
            response = client.post(
                "/api/auth/logout", headers={"X-CSRF-Token": generate_csrf_token(token)}
            )
            assert response.status_code == 200
            names = _set_cookie_names(response)
            # Deletion cookies for both session names + both CSRF names.
            assert SESSION_COOKIE_PREFIXED in names
            assert SESSION_COOKIE_PLAIN in names
            assert CSRF_COOKIE_PREFIXED in names
            assert CSRF_COOKIE_PLAIN in names
        finally:
            client.close()

    def test_logout_clears_both_names_insecure(self, monkeypatch):
        token = self._seed_session()
        monkeypatch.setattr(auth.settings, "COOKIE_SECURE", False)
        client = TestClient(app)
        try:
            client.cookies.set("session_id", token)
            response = client.post(
                "/api/auth/logout", headers={"X-CSRF-Token": generate_csrf_token(token)}
            )
            assert response.status_code == 200
            names = _set_cookie_names(response)
            assert SESSION_COOKIE_PREFIXED in names
            assert SESSION_COOKIE_PLAIN in names
            assert CSRF_COOKIE_PREFIXED in names
            assert CSRF_COOKIE_PLAIN in names
        finally:
            client.close()
