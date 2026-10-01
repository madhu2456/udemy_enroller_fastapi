"""Unit tests for deterministic cookie conflict resolution and coupon checkout resilience."""

import http.cookiejar
import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from requests.cookies import CookieConflictError, RequestsCookieJar

from app.services.course import Course
from app.services.http_client import extract_cookie_dict
from app.services.udemy_client import UdemyClient


def _make_cookie(
    name: str,
    value: str,
    domain: str = ".udemy.com",
    path: str = "/",
    expires: float | None = None,
) -> http.cookiejar.Cookie:
    """Helper to instantiate an RFC-compliant http.cookiejar.Cookie."""
    return http.cookiejar.Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=domain,
        domain_specified=bool(domain),
        domain_initial_dot=domain.startswith("."),
        path=path,
        path_specified=bool(path),
        secure=False,
        expires=expires,
        discard=False,
        comment=None,
        comment_url=None,
        rest={},
        rfc2109=False,
    )


class _MockJarWrapper:
    """Helper duck-typed wrapper holding cookies in a .jar attribute."""

    def __init__(self, cookies: list[http.cookiejar.Cookie]) -> None:
        self.jar = cookies


def test_extract_cookie_dict_none_and_empty():
    """Verifies None, empty dict, and empty objects return empty dict."""
    assert extract_cookie_dict(None) == {}
    assert extract_cookie_dict({}) == {}

    empty_jar = http.cookiejar.CookieJar()
    assert extract_cookie_dict(empty_jar) == {}

    wrapper = _MockJarWrapper([])
    assert extract_cookie_dict(wrapper) == {}


def test_extract_cookie_dict_plain_dict_and_mock():
    """Verifies dictionary mocks pass through untouched with string conversion."""
    plain = {"csrftoken": "tok123", "client_id": "cid456"}
    res = extract_cookie_dict(plain)
    assert res == {"csrftoken": "tok123", "client_id": "cid456"}

    with_types = {"num": 123, "none_val": None, "bool_val": True}
    res_types = extract_cookie_dict(with_types)
    assert res_types == {"num": "123", "none_val": "", "bool_val": "True"}


def test_extract_cookie_dict_httpx_cookies_conflict():
    """Populates httpx.Cookies with duplicate csrftoken across domains.

    Proves dict(cookies) raises httpx.CookieConflict while extract_cookie_dict
    succeeds deterministically selecting .udemy.com.
    """
    cookies = httpx.Cookies()
    cookies.jar.set_cookie(_make_cookie("csrftoken", "domainless_token", domain=""))
    cookies.jar.set_cookie(_make_cookie("csrftoken", "udemy_token", domain=".udemy.com"))

    with pytest.raises(httpx.CookieConflict):
        dict(cookies)

    extracted = extract_cookie_dict(cookies)
    assert extracted["csrftoken"] == "udemy_token"


def test_extract_cookie_dict_requests_cookiejar_conflict():
    """Populates RequestsCookieJar with duplicate csrftoken on .udemy.com and sub.udemy.com.

    Proves jar.get('csrftoken') raises CookieConflictError while extract_cookie_dict
    succeeds deterministically selecting .udemy.com.
    """
    jar = RequestsCookieJar()
    jar.set_cookie(_make_cookie("csrftoken", "subdomain_token", domain="sub.udemy.com"))
    jar.set_cookie(_make_cookie("csrftoken", "root_token", domain=".udemy.com"))

    with pytest.raises(CookieConflictError):
        jar.get("csrftoken")

    extracted = extract_cookie_dict(jar)
    assert extracted["csrftoken"] == "root_token"


def test_extract_cookie_dict_expired_cookie_prevention():
    """Proves an active cookie with T_future supersedes an expired cookie with T_past.

    Verified regardless of cookie arrival/iteration order.
    """
    now = time.time()
    active = _make_cookie("session", "active_val", domain=".udemy.com", expires=now + 3600)
    expired = _make_cookie("session", "expired_val", domain=".udemy.com", expires=now - 3600)

    # Active first, expired second
    res1 = extract_cookie_dict(_MockJarWrapper([active, expired]))
    assert res1["session"] == "active_val"

    # Expired first, active second
    res2 = extract_cookie_dict(_MockJarWrapper([expired, active]))
    assert res2["session"] == "active_val"


def test_extract_cookie_dict_empty_zombie_cookie_prevention():
    """Proves a populated cookie value supersedes an empty cleared zombie cookie value."""
    populated = _make_cookie("csrftoken", "populated_token", domain=".udemy.com")
    empty = _make_cookie("csrftoken", "", domain=".udemy.com")

    res1 = extract_cookie_dict(_MockJarWrapper([populated, empty]))
    assert res1["csrftoken"] == "populated_token"

    res2 = extract_cookie_dict(_MockJarWrapper([empty, populated]))
    assert res2["csrftoken"] == "populated_token"


def test_extract_cookie_dict_path_specificity():
    """Proves path /payment/checkout/ supersedes root path /."""
    root = _make_cookie("csrftoken", "root_path_csrf", domain=".udemy.com", path="/")
    specific = _make_cookie("csrftoken", "specific_path_csrf", domain=".udemy.com", path="/payment/checkout/")

    res1 = extract_cookie_dict(_MockJarWrapper([root, specific]))
    assert res1["csrftoken"] == "specific_path_csrf"

    res2 = extract_cookie_dict(_MockJarWrapper([specific, root]))
    assert res2["csrftoken"] == "specific_path_csrf"


def test_extract_cookie_dict_response_wrapper():
    """Proves duck-typed response objects with .cookies are automatically unwrapped."""
    class DuckResponse:
        def __init__(self, cookies):
            self.cookies = cookies

    resp = DuckResponse({"sessionid": "sess_abc", "csrftoken": "csrf_xyz"})
    assert extract_cookie_dict(resp) == {"sessionid": "sess_abc", "csrftoken": "csrf_xyz"}

    resp_empty = DuckResponse(None)
    assert extract_cookie_dict(resp_empty) == {}


@pytest.mark.asyncio
async def test_du_checkout_survives_conflicted_client_cookies():
    """Sets conflicted cookies directly on client.http.client.cookies and executes _du_checkout.

    Verifies checkout completes without raising CookieConflict or CookieConflictError.
    """
    client = UdemyClient()
    client.cookie_dict["csrftoken"] = "valid_csrf"

    # Create conflicted httpx cookies that raise CookieConflict on dict()
    hx_cookies = httpx.Cookies()
    hx_cookies.jar.set_cookie(_make_cookie("csrftoken", "domainless_csrf", domain=""))
    hx_cookies.jar.set_cookie(_make_cookie("csrftoken", "udemy_csrf", domain=".udemy.com"))

    with pytest.raises(httpx.CookieConflict):
        dict(hx_cookies)

    client.http = MagicMock()
    client.http.client = MagicMock()
    client.http.client.cookies = hx_cookies

    # Mock preflight and checkout responses carrying conflicted cookies
    r_pre = MagicMock(status_code=302, cookies=hx_cookies)
    client.http.get = AsyncMock(return_value=r_pre)

    resp = MagicMock(
        status_code=200,
        headers={"content-type": "application/json"},
        cookies=hx_cookies,
    )
    resp.json = MagicMock(return_value={"status": "succeeded"})
    client.http.post = AsyncMock(return_value=resp)

    course = Course(title="Free Resilient Course", url="https://www.udemy.com/course/free-resilient-course/")
    course.course_id = "88888"
    course.price = 0.0

    await client._du_checkout(course)

    assert course.status is True
    assert client.http.post.await_count == 1
    # Check that cookie_dict was updated with the authoritative .udemy.com token
    assert client.cookie_dict.get("csrftoken") == "udemy_csrf"
