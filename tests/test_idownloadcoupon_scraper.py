import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.services.http_client import AsyncHTTPClient
from app.services.scraper import IDownloadCouponScraper


@pytest.fixture
def http_client():
    client = MagicMock(spec=AsyncHTTPClient)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "<html></html>"
    mock_resp.content = b"<html></html>"
    mock_resp.headers = {}
    client.get = AsyncMock(return_value=mock_resp)
    client.safe_json = AsyncMock()
    return client


@pytest.fixture
def scraper(http_client):
    return IDownloadCouponScraper(http_client)


def test_class_attributes():
    assert IDownloadCouponScraper.MAX_COURSES == 500
    assert IDownloadCouponScraper.PER_PAGE == 100
    assert IDownloadCouponScraper.MAX_PAGES == 15
    assert IDownloadCouponScraper.LISTING_CONCURRENCY == 5
    assert IDownloadCouponScraper.BASE_URL == "https://idownloadcoupon.com"
    assert (
        IDownloadCouponScraper.STORE_API_ENDPOINT
        == "https://idownloadcoupon.com/wp-json/wc/store/v1/products"
    )


@pytest.mark.asyncio
async def test_store_api_successful_extraction(scraper):
    products = [
        {"id": 101, "name": "Python &amp; Flask Mastery"},
    ]

    async def mock_safe_json(resp, context=""):
        if resp.status_code == 200 and "wc/store" in getattr(resp, "url", ""):
            return products
        return None

    def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.url = str(url)
        if "/udemy/101/" in str(url):
            resp.status_code = 302
            resp.headers = {
                "Location": "https://www.udemy.com/course/python-flask/?couponCode=FREE"
            }
            return resp
        if "wc/store/v1/products" in str(url):
            resp.status_code = 200
            resp.headers = {"X-WP-TotalPages": "1"}
            return resp
        resp.status_code = 404
        return resp

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.http.safe_json = AsyncMock(side_effect=mock_safe_json)

    await scraper.scrape(asyncio.Semaphore(5))

    assert len(scraper.data) == 1
    assert scraper.data[0].title == "Python & Flask Mastery"
    assert (
        scraper.data[0].url
        == "https://www.udemy.com/course/python-flask/?couponCode=FREE"
    )


@pytest.mark.asyncio
async def test_store_api_eof_400_rest_post_invalid_page_number(scraper):
    p1 = [{"id": 101, "name": "Course 1"}]

    async def mock_safe_json(resp, context=""):
        if resp.status_code == 200:
            return p1
        return {"code": "rest_post_invalid_page_number", "message": "The page number supplied was too large."}

    def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.url = str(url)
        if "/udemy/101/" in str(url):
            resp.status_code = 302
            resp.headers = {
                "Location": "https://www.udemy.com/course/course-1/?couponCode=FREE"
            }
            return resp
        if "page=1" in str(url):
            resp.status_code = 200
            resp.headers = {"X-WP-TotalPages": "2"}
            return resp
        if "page=2" in str(url):
            resp.status_code = 400
            resp.headers = {}
            return resp
        resp.status_code = 404
        return resp

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.http.safe_json = AsyncMock(side_effect=mock_safe_json)

    await scraper.scrape(asyncio.Semaphore(5))

    assert len(scraper.data) == 1
    assert scraper.data[0].title == "Course 1"


@pytest.mark.asyncio
async def test_store_api_empty_list_eof(scraper):
    p1 = [{"id": 101, "name": "Course 1"}]

    async def mock_safe_json(resp, context=""):
        if "page=1" in getattr(resp, "url", ""):
            return p1
        return []

    def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.url = str(url)
        if "/udemy/101/" in str(url):
            resp.status_code = 302
            resp.headers = {
                "Location": "https://www.udemy.com/course/course-1/?couponCode=FREE"
            }
            return resp
        if "page=1" in str(url):
            resp.status_code = 200
            resp.headers = {"X-WP-TotalPages": "2"}
            return resp
        if "page=2" in str(url):
            resp.status_code = 200
            resp.headers = {"X-WP-TotalPages": "2"}
            return resp
        resp.status_code = 404
        return resp

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.http.safe_json = AsyncMock(side_effect=mock_safe_json)

    await scraper.scrape(asyncio.Semaphore(5))

    assert len(scraper.data) == 1
    assert scraper.data[0].title == "Course 1"


@pytest.mark.asyncio
async def test_store_api_failure_fallback_to_html(scraper):
    html_listing = """
    <html>
        <a href="https://idownloadcoupon.com/udemy/202/fastapi-course/">FastAPI Course</a>
    </html>
    """.encode()

    def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.url = str(url)
        if "wc/store/v1/products" in str(url):
            resp.status_code = 500
            resp.content = b"Internal Server Error"
            return resp
        if "/udemy/202/" in str(url):
            resp.status_code = 302
            resp.headers = {
                "Location": "https://www.udemy.com/course/fastapi-course/?couponCode=FREE"
            }
            return resp
        if "/page/" in str(url):
            resp.status_code = 200
            resp.content = html_listing
            resp.text = html_listing.decode()
            return resp
        resp.status_code = 404
        return resp

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.http.safe_json = AsyncMock(return_value=None)
    scraper.MAX_COURSES = 500

    await scraper.scrape(asyncio.Semaphore(5))

    assert len(scraper.data) == 1
    assert scraper.data[0].title == "FastAPI Course"
    assert (
        scraper.data[0].url
        == "https://www.udemy.com/course/fastapi-course/?couponCode=FREE"
    )


@pytest.mark.asyncio
async def test_html_listing_extraction_and_regex(scraper):
    html_listing = """
    <html>
        <a href="/udemy/301/valid-course/">Valid HTML Course</a>
        <a href="/udemy/302/redeem-link/">Redeem Offer</a>
        <a href="/udemy/303/udemy-link/">UDEMY</a>
        <a href="/udemy/304/sale-link/">Sale!</a>
        <a href="/udemy/305/short/">AB</a>
        <a href="/not-udemy/306/wrong/">Wrong Link</a>
        <a href="/udemy/non-numeric/slug/">Non numeric ID</a>
    </html>
    """.encode()

    def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.url = str(url)
        if "wc/store/v1/products" in str(url):
            resp.status_code = 500
            return resp
        if "/udemy/301/" in str(url):
            resp.status_code = 302
            resp.headers = {
                "Location": "https://www.udemy.com/course/valid-course/?couponCode=FREE"
            }
            return resp
        if "/page/" in str(url):
            resp.status_code = 200
            resp.content = html_listing
            resp.text = html_listing.decode()
            return resp
        resp.status_code = 404
        return resp

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.http.safe_json = AsyncMock(return_value=None)
    scraper.MAX_COURSES = 500

    await scraper.scrape(asyncio.Semaphore(5))

    assert len(scraper.data) == 1
    assert scraper.data[0].title == "Valid HTML Course"


@pytest.mark.asyncio
async def test_redeem_redirect_trk_resolved(scraper):
    products = [
        {"id": 401, "name": "Rust Fundamentals"},
    ]

    async def mock_safe_json(resp, context=""):
        if "wc/store" in getattr(resp, "url", ""):
            return products
        return None

    def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.url = str(url)
        if "/udemy/401/" in str(url):
            resp.status_code = 302
            resp.headers = {
                "Location": "https://trk.udemy.com/trk-rust?couponCode=FREE"
            }
            return resp
        if "wc/store/v1/products" in str(url):
            resp.status_code = 200
            resp.headers = {"X-WP-TotalPages": "1"}
            return resp
        resp.status_code = 404
        return resp

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.http.safe_json = AsyncMock(side_effect=mock_safe_json)
    scraper._resolve_trk_redirect = AsyncMock(
        return_value="https://www.udemy.com/course/rust-fundamentals/?couponCode=FREE"
    )

    await scraper.scrape(asyncio.Semaphore(5))

    scraper._resolve_trk_redirect.assert_awaited_once_with(
        "https://trk.udemy.com/trk-rust?couponCode=FREE"
    )
    assert len(scraper.data) == 1
    assert (
        scraper.data[0].url
        == "https://www.udemy.com/course/rust-fundamentals/?couponCode=FREE"
    )


@pytest.mark.asyncio
async def test_redeem_redirect_hostile_rejected(scraper):
    products = [
        {"id": 501, "name": "Hostile Course"},
    ]

    async def mock_safe_json(resp, context=""):
        if "wc/store" in getattr(resp, "url", ""):
            return products
        return None

    def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.url = str(url)
        if "/udemy/501/" in str(url):
            resp.status_code = 302
            resp.headers = {
                "Location": "https://evil.com/course/stolen/?couponCode=FREE"
            }
            return resp
        if "wc/store/v1/products" in str(url):
            resp.status_code = 200
            resp.headers = {"X-WP-TotalPages": "1"}
            return resp
        resp.status_code = 404
        return resp

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.http.safe_json = AsyncMock(side_effect=mock_safe_json)

    await scraper.scrape(asyncio.Semaphore(5))

    assert len(scraper.data) == 0


@pytest.mark.asyncio
async def test_deduplication_and_max_courses_cap(scraper):
    products = [
        {"id": 601, "name": "Course 1"},
        {"id": 602, "name": "Course 2"},
        {"id": 601, "name": "Course 1 Duplicate"},
    ]

    async def mock_safe_json(resp, context=""):
        if "wc/store" in getattr(resp, "url", ""):
            return products
        return None

    def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.url = str(url)
        if "/udemy/601/" in str(url):
            resp.status_code = 302
            resp.headers = {
                "Location": "https://www.udemy.com/course/c1/?couponCode=FREE"
            }
            return resp
        if "/udemy/602/" in str(url):
            resp.status_code = 302
            resp.headers = {
                "Location": "https://www.udemy.com/course/c2/?couponCode=FREE"
            }
            return resp
        if "wc/store/v1/products" in str(url):
            resp.status_code = 200
            resp.headers = {"X-WP-TotalPages": "1"}
            return resp
        resp.status_code = 404
        return resp

    scraper.http.get = AsyncMock(side_effect=mock_get)
    scraper.http.safe_json = AsyncMock(side_effect=mock_safe_json)
    scraper.MAX_COURSES = 1

    await scraper.scrape(asyncio.Semaphore(5))

    assert len(scraper.data) == 1
