"""T6-1 RED: truncated-token loop (mocks only, no network/Tk mainloop)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.gui.bridge import AsyncioBridge
from app.services.browser_cookies import UdemyBrowserCookies
from app.services.udemy_client import LoginException

FULL = "eyFULL_" + "A" * 40
CID = "cidFULL_" + "B" * 40
CSRF = "csrfFULL_" + "C" * 40


def _full_cookies(**kw):
    d = dict(access_token=FULL, client_id=CID, csrf_token=CSRF, browser_name="firefox",
             profile_name="Default", is_valid=True)
    d.update(kw)
    return UdemyBrowserCookies(**d)


def _ok_client():
    m = MagicMock()
    m.cookie_login = MagicMock()
    m.get_session_info = AsyncMock(return_value=True)
    m.get_enrolled_courses = AsyncMock(return_value={})
    m.close = AsyncMock()
    m.is_authenticated = True
    m.display_name = "T6 User"
    m.udemy_user_id = "u1"
    m.currency = "USD"
    m.enrolled_courses = {}
    return m


def _by(evts, name):
    return [e for e in evts if e.get("event") == name]


def test_auto_extract_emits_display_truncated_auth_full():
    b = AsyncioBridge()
    with patch("app.gui.bridge.get_udemy_cookies", return_value=_full_cookies()):
        asyncio.run(b._handle_auto_extract_cookies({"browser": "firefox"}))
    ext = _by(b.poll_events(), "COOKIES_EXTRACTED")
    assert ext, "expected COOKIES_EXTRACTED event"
    p = ext[0]["data"]
    assert p.get("access_token", "").endswith("...") and len(p["access_token"]) <= 11
    auth = p.get("auth", {})
    assert isinstance(auth, dict) and auth.get("access_token") == FULL, "missing auth full token"
    assert p.get("from_extract") is True


def test_test_login_flagged_truncated_reextracts_full():
    b = AsyncioBridge()
    mc = _ok_client()
    with patch("app.gui.bridge.get_udemy_cookies", return_value=_full_cookies()) as mg, \
         patch("app.gui.bridge.UdemyClient", return_value=mc), \
         patch("app.gui.bridge.save_persistent_session"):
        asyncio.run(b._handle_test_login({"access_token": "abcd1234...", "client_id": "cid...",
                                          "csrf_token": "csrf...", "browser": "auto", "from_extract": True}))
    assert mc.cookie_login.called, "cookie_login not called"
    got = mc.cookie_login.call_args.kwargs.get("access_token", mc.cookie_login.call_args[0][0] if mc.cookie_login.call_args[0] else "")
    assert got == FULL, f"expected FULL re-extract, got truncated {got!r}"


def test_log_events_never_contain_full_token():
    b = AsyncioBridge()
    mc = _ok_client()
    with patch("app.gui.bridge.get_udemy_cookies", return_value=_full_cookies()), \
         patch("app.gui.bridge.UdemyClient", return_value=mc), \
         patch("app.gui.bridge.save_persistent_session"):
        asyncio.run(b._handle_auto_extract_cookies({"browser": "firefox"}))
        asyncio.run(b._handle_test_login({"access_token": FULL, "client_id": CID, "csrf_token": CSRF}))
    logs = _by(b.poll_events(), "LOG")
    assert logs, "expected LOG events"
    for e in logs:
        assert FULL not in str(e.get("data", {}).get("message", "")), f"full token leaked: {e}"


def test_status_details_discriminates():
    b1 = AsyncioBridge()
    with patch("app.gui.bridge.get_udemy_cookies",
               return_value=UdemyBrowserCookies(browser_name="chrome", is_valid=False, error="locked", notes="v20 App-Bound encryption")):
        asyncio.run(b1._handle_auto_extract_cookies({"browser": "chrome"}))
    e1 = _by(b1.poll_events(), "COOKIES_EXTRACTED_FAILED")
    assert e1, "v20 notes must emit COOKIES_EXTRACTED_FAILED"
    b2 = AsyncioBridge()
    m2 = _ok_client()
    m2.get_session_info = AsyncMock(side_effect=LoginException("Session invalid."))
    with patch("app.gui.bridge.UdemyClient", return_value=m2), patch("app.gui.bridge.save_persistent_session"):
        asyncio.run(b2._handle_test_login({"access_token": FULL, "client_id": CID, "csrf_token": CSRF}))
    e2 = _by(b2.poll_events(), "AUTH_FAILED")
    assert e2 and "Session invalid" in str(e2[0]["data"].get("error", ""))
    b3 = AsyncioBridge()
    m3 = _ok_client()
    m3.get_session_info = AsyncMock(side_effect=OSError("Network unreachable"))
    with patch("app.gui.bridge.UdemyClient", return_value=m3), patch("app.gui.bridge.save_persistent_session"):
        asyncio.run(b3._handle_test_login({"access_token": FULL, "client_id": CID, "csrf_token": CSRF}))
    e3 = _by(b3.poll_events(), "AUTH_FAILED")
    assert e3 and "Could not connect" in str(e3[0]["data"].get("error", "")), f"got {e3}"
    assert len({e1[0]["event"], e2[0]["data"].get("error"), e3[0]["data"].get("error")}) == 3
