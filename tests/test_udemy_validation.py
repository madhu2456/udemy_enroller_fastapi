"""F-ENRL-C07: Udemy host validation — hostile-host matrix.

Guards the exact-netloc allowlist in ``app.services.udemy_validation`` and the
Location-header redirect gates in the scrapers. Every production
"is this Udemy?" decision must reject lookalike hosts
(``udemy.com.evil.com``, ``eviludemy.com``, userinfo, ports, trailing dots,
IP literals, percent-encoded hosts) — only the exact set
{udemy.com, www.udemy.com, trk.udemy.com} may pass.
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.udemy_validation import (
    is_udemy_course_url,
    is_udemy_netloc,
    is_udemy_url,
    is_trk_udemy_url,
)

# ---------------------------------------------------------------------------
# Hostile netloc matrix — none may be accepted.
# ---------------------------------------------------------------------------

HOSTILE_NETLOCS = [
    "udemy.com.evil.com",  # suffix spoof
    "eviludemy.com",  # prefix spoof
    "udemy.com.attacker.io",
    "www.udemy.com.evil.com",
    "trk.udemy.com.evil.com",
    "user@udemy.com",  # userinfo smuggled into netloc
    "udemy.com.",  # trailing dot (different DNS namespace)
    "www.udemy.com.",
    "udemy.com:8443",  # port (different origin)
    "www.udemy.com:443",
    "192.168.1.1",  # IP literal
    "10.0.0.1",
    "[::1]",  # IPv6 literal
    "udemy%2Ecom",  # percent-encoded dot
    "udemy.com%2eevil.com",
    "udemy.com/evil",  # path remnant
    "udemy.com\\evil",  # backslash confusion
    "udemy.com:80",
    "UDEMY.COM.EVIL.COM",
]

LEGIT_NETLOCS = [
    "udemy.com",
    "www.udemy.com",
    "trk.udemy.com",
    "UDEMY.COM",  # DNS case-insensitivity is fine
    "  www.udemy.com  ",  # whitespace tolerance
]


@pytest.mark.parametrize("host", HOSTILE_NETLOCS)
def test_is_udemy_netloc_rejects_hostile(host):
    assert is_udemy_netloc(host) is False, f"hostile netloc accepted: {host}"


@pytest.mark.parametrize("host", LEGIT_NETLOCS)
def test_is_udemy_netloc_accepts_legit(host):
    assert is_udemy_netloc(host) is True, f"legit netloc rejected: {host}"


@pytest.mark.parametrize("host", [None, 42, b"udemy.com", "", "   "])
def test_is_udemy_netloc_rejects_non_strings(host):
    assert is_udemy_netloc(host) is False


# ---------------------------------------------------------------------------
# Hostile URL matrix — the same hosts as full URLs (Location-header values).
# ---------------------------------------------------------------------------

HOSTILE_URLS = [
    "https://udemy.com.evil.com/course/x/",
    "https://eviludemy.com/course/x/",
    "http://udemy.com.attacker.io/",
    "https://user@udemy.com/course/x/",  # userinfo
    "https://udemy.com./course/x/",  # trailing dot
    "https://udemy.com:8443/course/x/",  # port
    "https://www.udemy.com:8443/course/x/",
    "https://192.168.1.1/course/x/",  # IP literal
    "http://[::1]/course/x/",
    "https://udemy%2Ecom/course/x/",  # percent-encoded host
    "https://udemy.com.evil.com/",
    "ftp://udemy.com/course/x/",  # non-http scheme
    "udemy.com/course/x/",  # scheme-less
    "javascript:udemy.com",
    "https://",
    "",
]

LEGIT_URLS = [
    "https://www.udemy.com/course/python-masterclass/",
    "https://www.udemy.com/course/python/?couponCode=FREE",
    "https://udemy.com/course/x/",
    "http://udemy.com/course/x/",
    "https://trk.udemy.com/abc123",
    "https://trk.udemy.com/?u=https%3A%2F%2Fwww.udemy.com%2Fcourse%2Ftest%2F",
]


@pytest.mark.parametrize("url", HOSTILE_URLS)
def test_is_udemy_url_rejects_hostile(url):
    assert is_udemy_url(url) is False, f"hostile URL accepted: {url}"


@pytest.mark.parametrize("url", LEGIT_URLS)
def test_is_udemy_url_accepts_legit(url):
    assert is_udemy_url(url) is True, f"legit URL rejected: {url}"


# ---------------------------------------------------------------------------
# is_udemy_course_url — path checks.
# ---------------------------------------------------------------------------

COURSE_URL_TRUE = [
    "https://www.udemy.com/course/python/",
    "https://www.udemy.com/course/python/?couponCode=FREE",
    "https://udemy.com/course/python-masterclass/",
    "http://www.udemy.com/course/x/",
    "https://www.udemy.com/course/",  # empty slug still starts with /course/ (host trust is the boundary)
]

COURSE_URL_FALSE = [
    "https://www.udemy.com/",  # bare home
    "https://www.udemy.com/courses/",  # plural path ≠ /course/
    "https://www.udemy.com/courseevil/",  # prefix collision
    "https://www.udemy.com/collections/abc/",
    "https://trk.udemy.com/abc123",  # trk redirector, not a course page
    "https://www.udemy.com.evil.com/course/x/",
]


@pytest.mark.parametrize("url", COURSE_URL_TRUE)
def test_is_udemy_course_url_accepts(url):
    assert is_udemy_course_url(url) is True, f"course URL rejected: {url}"


@pytest.mark.parametrize("url", COURSE_URL_FALSE)
def test_is_udemy_course_url_rejects(url):
    assert is_udemy_course_url(url) is False, f"non-course URL accepted: {url}"


# ---------------------------------------------------------------------------
# is_trk_udemy_url.
# ---------------------------------------------------------------------------

TRK_TRUE = [
    "https://trk.udemy.com/abc123",
    "https://trk.udemy.com/?u=https%3A%2F%2Fwww.udemy.com%2Fcourse%2Fx%2F",
    "http://trk.udemy.com/short",
]

TRK_FALSE = [
    "https://www.udemy.com/course/x/",
    "https://trk.udemy.com.evil.com/abc",
    "https://trk.udemy.com:8443/abc",
    "https://udemy.com/abc",
]


@pytest.mark.parametrize("url", TRK_TRUE)
def test_is_trk_udemy_url_accepts(url):
    assert is_trk_udemy_url(url) is True, f"trk URL rejected: {url}"


@pytest.mark.parametrize("url", TRK_FALSE)
def test_is_trk_udemy_url_rejects(url):
    assert is_trk_udemy_url(url) is False, f"non-trk URL accepted: {url}"


# ---------------------------------------------------------------------------
# Scraper Location-header redirect gates (integration).
# ---------------------------------------------------------------------------


def _redirect_response(location: str, status: int = 302) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.headers = {"location": location}
    resp.content = b""
    resp.url = "https://www.udemyfreebies.com/out/slug-1"
    return resp


@pytest.fixture
def freebies_scraper():
    from app.services.scraper import UdemyFreebiesScraper

    http = MagicMock()
    http.get = AsyncMock()
    scraper = UdemyFreebiesScraper(http)
    return http, scraper


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hostile_location",
    [
        "https://udemy.com.evil.com/course/x/?couponCode=FREE",
        "https://eviludemy.com/course/x/",
        "https://user@udemy.com/course/x/",
        "https://udemy.com./course/x/",
        "https://udemy.com:8443/course/x/",
        "https://192.168.1.1/course/x/",
        "https://udemy%2Ecom/course/x/",
        "//attacker.example/path",
    ],
)
async def test_udemyfreebies_rejects_hostile_location(freebies_scraper, hostile_location):
    """UdemyFreebies /out/ Location headers must never yield a course."""
    http, scraper = freebies_scraper

    def mock_get(url, *args, **kwargs):
        if "/out/" in url:
            return _redirect_response(hostile_location)
        resp = MagicMock()
        resp.status_code = 200
        resp.content = (
            '<div class="coupon-name"><a href="/free-udemy-course/slug-1">'
            "Hostile Course</a></div>"
        ).encode()
        resp.url = url
        return resp

    http.get.side_effect = mock_get
    await scraper.scrape(asyncio.Semaphore(1))
    assert scraper.data == [], (
        f"hostile Location accepted by UdemyFreebies: {hostile_location}"
    )

    out_calls = [c for c in http.get.call_args_list if c.args and "/out/" in c.args[0]]
    assert out_calls
    for call in out_calls:
        assert call.kwargs.get("use_cloudscraper") is True
        assert call.kwargs.get("allow_redirects") is False
        assert call.kwargs.get("follow_redirects") is False
        assert call.kwargs.get("raise_for_status") is False
        assert call.kwargs.get("attempts") == 1


@pytest.mark.asyncio
async def test_udemyfreebies_accepts_legit_location(freebies_scraper):
    http, scraper = freebies_scraper
    legit = "https://www.udemy.com/course/real-course/?couponCode=FREE"

    def mock_get(url, *args, **kwargs):
        if "/out/" in url:
            return _redirect_response(legit)
        resp = MagicMock()
        resp.status_code = 200
        resp.content = (
            '<div class="coupon-name"><a href="/free-udemy-course/slug-1">'
            "Real Course</a></div>"
        ).encode()
        resp.url = url
        return resp

    http.get.side_effect = mock_get
    await scraper.scrape(asyncio.Semaphore(1))
    assert len(scraper.data) == 1
    assert scraper.data[0].url == legit

    out_calls = [c for c in http.get.call_args_list if c.args and "/out/" in c.args[0]]
    assert out_calls
    for call in out_calls:
        assert call.kwargs.get("use_cloudscraper") is True
        assert call.kwargs.get("allow_redirects") is False
        assert call.kwargs.get("follow_redirects") is False
        assert call.kwargs.get("raise_for_status") is False
        assert call.kwargs.get("attempts") == 1


UF_SLUG = "ace-every-job-interview-master-blueprint-and-get-your-dream-job"
UF_COUPON = "AUG2026FREE01"
UF_SINGLE_SEGMENT = f"https://www.udemy.com/{UF_SLUG}/?couponCode={UF_COUPON}"
UF_REWRITTEN = f"https://www.udemy.com/course/{UF_SLUG}/?couponCode={UF_COUPON}"


@pytest.mark.asyncio
async def test_udemyfreebies_rewrites_single_segment_location(freebies_scraper):
    http, scraper = freebies_scraper

    def mock_get(url, *args, **kwargs):
        if "/out/" in url:
            return _redirect_response(UF_SINGLE_SEGMENT)
        resp = MagicMock()
        resp.status_code = 200
        resp.content = (
            '<div class="coupon-name"><a href="/free-udemy-course/slug-1">'
            "Ace Every Job Interview</a></div>"
        ).encode()
        resp.url = url
        return resp

    http.get.side_effect = mock_get
    await scraper.scrape(asyncio.Semaphore(1))
    assert len(scraper.data) == 1
    assert scraper.data[0].url == UF_REWRITTEN

    out_calls = [c for c in http.get.call_args_list if c.args and "/out/" in c.args[0]]
    assert out_calls
    for call in out_calls:
        assert call.kwargs.get("use_cloudscraper") is True
        assert call.kwargs.get("allow_redirects") is False
        assert call.kwargs.get("follow_redirects") is False
        assert call.kwargs.get("raise_for_status") is False
        assert call.kwargs.get("attempts") == 1
        assert call.kwargs.get("timeout") == 15


@pytest.mark.asyncio
async def test_udemyfreebies_trk_location_uses_resolve_trk_not_course_rewrite(
    freebies_scraper,
):
    http, scraper = freebies_scraper
    trk_id = "trk-id-123"
    trk_location = f"https://trk.udemy.com/{trk_id}?couponCode={UF_COUPON}"
    resolved = "https://www.udemy.com/course/real-trk-course/?couponCode=FREE"
    scraper._resolve_trk_redirect = AsyncMock(return_value=resolved)

    def mock_get(url, *args, **kwargs):
        if "/out/" in url:
            return _redirect_response(trk_location)
        resp = MagicMock()
        resp.status_code = 200
        resp.content = (
            '<div class="coupon-name"><a href="/free-udemy-course/slug-1">'
            "Trk Course</a></div>"
        ).encode()
        resp.url = url
        return resp

    http.get.side_effect = mock_get
    await scraper.scrape(asyncio.Semaphore(1))
    assert len(scraper.data) == 1
    assert scraper.data[0].url == resolved
    assert f"/course/{trk_id}" not in scraper.data[0].url
    scraper._resolve_trk_redirect.assert_awaited()
    assert scraper._resolve_trk_redirect.await_args.args[0] == trk_location


@pytest.mark.asyncio
async def test_udemyfreebies_single_segment_without_coupon_yields_empty(
    freebies_scraper,
):
    http, scraper = freebies_scraper
    location = f"https://www.udemy.com/{UF_SLUG}/"

    def mock_get(url, *args, **kwargs):
        if "/out/" in url:
            return _redirect_response(location)
        resp = MagicMock()
        resp.status_code = 200
        resp.content = (
            '<div class="coupon-name"><a href="/free-udemy-course/slug-1">'
            "No Coupon Course</a></div>"
        ).encode()
        resp.url = url
        return resp

    http.get.side_effect = mock_get
    await scraper.scrape(asyncio.Semaphore(1))
    assert scraper.data == []


@pytest.mark.asyncio
async def test_idownloadcoupon_rejects_hostile_location():
    """iDownloadCoupon /udemy/{id}/ Location headers must never yield a course."""
    from app.services.scraper import IDownloadCouponScraper

    http = MagicMock()
    http.get = AsyncMock()
    scraper = IDownloadCouponScraper(http)

    hostile = "https://eviludemy.com/course/x/?couponCode=FREE"

    def mock_get(url, *args, **kwargs):
        if "/udemy/" in url and "page/" not in url:
            resp = MagicMock()
            resp.status_code = 302
            resp.headers = {"location": hostile}
            resp.content = b""
            return resp
        resp = MagicMock()
        resp.status_code = 200
        resp.content = (
            '<a href="/udemy/12345/evil-course/">Evil Course</a>'
        ).encode()
        resp.url = url
        return resp

    http.get.side_effect = mock_get
    await scraper.scrape(asyncio.Semaphore(1))
    assert scraper.data == [], "hostile Location accepted by iDownloadCoupon"


@pytest.mark.asyncio
async def test_idownloadcoupon_accepts_legit_trk_location():
    """Legit trk.udemy.com Location resolves through _resolve_trk_redirect."""
    from app.services.scraper import IDownloadCouponScraper

    http = MagicMock()
    http.get = AsyncMock()
    scraper = IDownloadCouponScraper(http)

    location = (
        "https://trk.udemy.com/?u=https%3A%2F%2Fwww.udemy.com%2Fcourse%2F"
        "real-course%2F%3FcouponCode%3DFREE"
    )

    def mock_get(url, *args, **kwargs):
        if "/udemy/" in url and "page/" not in url:
            resp = MagicMock()
            resp.status_code = 302
            resp.headers = {"location": location}
            resp.content = b""
            return resp
        resp = MagicMock()
        resp.status_code = 200
        resp.content = (
            '<a href="/udemy/12345/real-course/">Real Course</a>'
        ).encode()
        resp.url = url
        return resp

    http.get.side_effect = mock_get
    await scraper.scrape(asyncio.Semaphore(1))
    assert len(scraper.data) == 1
    assert (
        scraper.data[0].url
        == "https://www.udemy.com/course/real-course/?couponCode=FREE"
    )

    redeem_calls = [
        c
        for c in http.get.call_args_list
        if c.args
        and "/udemy/" in c.args[0]
        and "page/" not in c.args[0]
        and c.args[0].rstrip("/").split("/")[-1].isdigit()
    ]
    assert redeem_calls
    for call in redeem_calls:
        assert call.kwargs.get("use_cloudscraper") is True
        assert call.kwargs.get("allow_redirects") is False
        assert call.kwargs.get("follow_redirects") is False
        assert call.kwargs.get("raise_for_status") is False
        assert call.kwargs.get("attempts") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hostile_location",
    [
        "/course/stolen/?couponCode=FREE",
        "../course/stolen/?couponCode=FREE",
        "//evil.example/course/x/?couponCode=FREE",
        "https://evil.example/?u=https://www.udemy.com/course/stolen/?couponCode=FREE",
        "https://eviludemy.com/course/x/?couponCode=FREE",
    ],
)
async def test_idownloadcoupon_relative_hostile_location_does_not_append(
    hostile_location,
):
    """Relative or hostile Location must not be unwrapped into a course URL."""
    from app.services.scraper import IDownloadCouponScraper

    http = MagicMock()
    http.get = AsyncMock()
    scraper = IDownloadCouponScraper(http)

    def mock_get(url, *args, **kwargs):
        if "/udemy/" in url and "page/" not in url:
            resp = MagicMock()
            resp.status_code = 302
            resp.headers = {"location": hostile_location}
            resp.content = b""
            return resp
        resp = MagicMock()
        resp.status_code = 200
        resp.content = (
            '<a href="/udemy/12345/stolen-course/">Stolen Course</a>'
        ).encode()
        resp.url = url
        return resp

    http.get.side_effect = mock_get
    await scraper.scrape(asyncio.Semaphore(1))
    assert scraper.data == [], (
        f"relative/hostile Location appended by iDownloadCoupon: {hostile_location}"
    )

    requested = [c.args[0] for c in http.get.call_args_list if c.args]
    assert all("evil.example" not in u for u in requested)
    assert all("eviludemy.com" not in u for u in requested)
    redeem_calls = [
        c
        for c in http.get.call_args_list
        if c.args
        and "/udemy/" in c.args[0]
        and "page/" not in c.args[0]
        and c.args[0].rstrip("/").split("/")[-1].isdigit()
    ]
    assert redeem_calls
    for call in redeem_calls:
        assert call.kwargs.get("allow_redirects") is False
        assert call.kwargs.get("follow_redirects") is False
        assert call.kwargs.get("attempts") == 1
