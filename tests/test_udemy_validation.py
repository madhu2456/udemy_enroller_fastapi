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
